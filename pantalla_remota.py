"""Servidor local HTTP y SSE para mostrar la interfaz Jarvis de Silvestra en una tablet."""
import http.server
import json
import secrets
import socket
import sys
import threading
import time
import urllib.parse

import acciones
import estado
import pantalla_remota_api as _api
from pantalla_remota_datos import recolectar_estado_completo
from pantalla_remota_qr import VentanaQR
from pantalla_remota_ui import PAGINA_JARVIS_HTML

PUERTO_DEFECTO = 8765
_lock = threading.Lock()


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [pantalla_remota]."""
    print(f"[pantalla_remota] {mensaje}", flush=True)


def obtener_ip_local():
    """Obtiene la dirección IP de la laptop en la red local WiFi o Ethernet."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


class ServidorPantallaRemota(http.server.ThreadingHTTPServer):
    """Servidor HTTP multihilo con supresión de trazas por desconexión normal de sockets."""

    def handle_error(self, request, client_address):
        """Silencia desconexiones habituales de clientes al cerrar pestañas o suspender la tablet."""
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        if isinstance(exc_val, (OSError, socket.error)):
            winerror = getattr(exc_val, "winerror", None) or getattr(exc_val, "errno", None)
            if winerror in (10053, 10054, 10058, 32):
                return
        # Para otros errores reales no controlados, llamar al manejador por defecto
        try:
            super().handle_error(request, client_address)
        except Exception:
            pass


class PantallaRemotaHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP que valida token, sirve el HUD Jarvis y emite eventos en tiempo real."""

    def log_message(self, format, *args):
        # Desactivar logs por defecto en consola para mantener el terminal limpio
        pass

    def _validar_token(self, query):
        token_cliente = query.get("token", [""])[0]
        return bool(token_cliente and token_cliente == self.server.token_autorizado)

    def _notificar_conexion_tablet(self):
        """Actualiza el registro de operaciones al conectarse una tablet real."""
        gestor = getattr(self.server, "gestor", None)
        if gestor and not getattr(gestor, "tablet_conectada", False):
            gestor.tablet_conectada = True
            with _lock:
                gestor.ultimos_eventos = [
                    e for e in gestor.ultimos_eventos
                    if "Esperando conexión" not in e.get("texto", "")
                ]
            gestor.registrar_evento(f"Tablet conectada ({self.client_address[0]})")

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url_parsed.query)

        if not self._validar_token(query):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Acceso denegado: token inválido o no suministrado.".encode("utf-8"))
            log(f"Intento de acceso rechazado desde {self.client_address[0]}")
            return

        self._notificar_conexion_tablet()

        # Ruta 1: Interfaz principal Jarvis
        if url_parsed.path in ("/", "/index.html"):
            contenido = PAGINA_JARVIS_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            try:
                self.wfile.write(contenido)
                log(f"Página Jarvis servida a cliente en {self.client_address[0]}")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            return

        # Ruta 2: Endpoint API JSON para estado completo y telemetría
        if url_parsed.path == "/api/panel/estado":
            datos = recolectar_estado_completo(self.server.app, self.server.gestor)
            contenido = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(contenido)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            return

        # Ruta 3: Flujo SSE en vivo
        if url_parsed.path == "/eventos":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            log(f"Conexión SSE establecida desde {self.client_address[0]}")
            try:
                while not self.server.detener_event.is_set():
                    datos = recolectar_estado_completo(self.server.app, self.server.gestor)
                    payload = json.dumps(datos, ensure_ascii=False)
                    msg = f"data: {payload}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            except Exception as e:
                log(f"Fin de flujo SSE con {self.client_address[0]}: {e}")
            finally:
                log(f"Conexión SSE cerrada desde {self.client_address[0]}")
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        """Responde preflight CORS para POST desde la tablet."""
        url_parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url_parsed.query)
        if url_parsed.path.startswith("/api/panel/"):
            _api.manejar_options(self)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Maneja endpoints POST seguros: /api/panel/comando y /api/panel/accion."""
        url_parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url_parsed.query)

        # Clientes remotos deben autenticarse; localhost se permite sin token
        ip = self.client_address[0]
        es_local = ip in ("127.0.0.1", "::1")
        if not es_local and not self._validar_token(query):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Acceso denegado: token inválido.".encode("utf-8"))
            return

        gestor = getattr(self.server, "gestor", None)
        app = getattr(self.server, "app", None)

        if url_parsed.path == "/api/panel/comando":
            _api.manejar_comando(self, app, gestor)
        elif url_parsed.path == "/api/panel/accion":
            _api.manejar_accion(self, app, gestor)
        else:
            self.send_response(404)
            self.end_headers()


class GestorPantallaRemota:
    """Orquesta el servidor HTTP local, el estado Jarvis y las acciones de la tablet."""

    def __init__(self, app):
        self.app = app
        self._servidor = None
        self._hilo = None
        self._detener_event = threading.Event()
        self.ventana_qr = None
        self.tarjeta_principal = "SILVESTRA VIRTUAL INTERFACE // SISTEMA OPERATIVO"
        self.tablet_conectada = False
        self.ultimos_eventos = [
            {"hora": time.strftime("%H:%M"), "texto": "Servidor HUD inicializado"},
            {"hora": time.strftime("%H:%M"), "texto": "Esperando conexión de tablet"},
        ]

        d = estado.cargar()
        self.token = d.get("remota_token")
        if not self.token:
            self.token = secrets.token_urlsafe(24)
            d["remota_token"] = self.token
            estado.guardar(d)

        self.puerto = d.get("remota_puerto", PUERTO_DEFECTO)
        self.activa = d.get("remota_activa", False)

        if self.activa:
            self.iniciar_servidor()

    def registrar_evento(self, texto):
        """Registra un evento visible en el terminal del panel Jarvis."""
        with _lock:
            self.ultimos_eventos.append({"hora": time.strftime("%H:%M"), "texto": texto})
            if len(self.ultimos_eventos) > 8:
                self.ultimos_eventos.pop(0)

    def obtener_url_completa(self):
        """Devuelve la URL accesible desde la red local para la tablet."""
        ip = obtener_ip_local()
        return f"http://{ip}:{self.puerto}/?token={self.token}"

    def iniciar_servidor(self):
        """Inicia el servidor HTTP en un hilo secundario daemon."""
        if self._servidor is not None:
            return True

        self._detener_event.clear()
        try:
            servidor = ServidorPantallaRemota(("0.0.0.0", self.puerto), PantallaRemotaHandler)
            servidor.token_autorizado = self.token
            servidor.detener_event = self._detener_event
            servidor.gestor = self
            servidor.app = self.app
            self._servidor = servidor

            def _correr():
                log(f"Servidor iniciado en http://0.0.0.0:{self.puerto}")
                try:
                    servidor.serve_forever()
                except Exception as ex:
                    log(f"Servidor finalizado: {ex}")

            self._hilo = threading.Thread(target=_correr, daemon=True, name="ServidorPantallaRemota")
            self._hilo.start()
            self.registrar_evento("Servidor HTTP online")
            return True
        except Exception as e:
            log(f"Error al iniciar servidor en puerto {self.puerto}: {e}")
            self._servidor = None
            return False

    def detener_servidor(self):
        """Detiene el servidor HTTP y cierra los sockets activos."""
        if self._servidor is None:
            return

        self._detener_event.set()
        try:
            self._servidor.shutdown()
            self._servidor.server_close()
        except Exception as e:
            log(f"Error deteniendo servidor: {e}")
        finally:
            self._servidor = None
            self._hilo = None
            log("Servidor detenido correctamente.")

    def accion_mostrar_en_tablet(self, arg=None):
        """Inicia la pantalla remota, copia la URL y abre la ventana con el código QR."""
        if arg and str(arg).strip():
            self.tarjeta_principal = str(arg).strip()
            self.registrar_evento(f"Proyección: {self.tarjeta_principal[:22]}")

        ok = self.iniciar_servidor()
        d = estado.cargar()
        d["remota_activa"] = True
        estado.guardar(d)

        url = self.obtener_url_completa()

        self.app.cola.put(("copiar_portapapeles", url))
        msg_voz = "Panel Jarvis listo en tu tablet. Ya copié la dirección al portapapeles."
        burbuja = f"📱 PANEL JARVIS TABLET:\n{url}\n\n(Enlace copiado al portapapeles)"
        self.app.cola.put(("hablar_registro", (msg_voz, burbuja)))

        def _mostrar_dialogo():
            try:
                if self.ventana_qr is not None:
                    self.ventana_qr.close()
                self.ventana_qr = VentanaQR(url)
                self.ventana_qr.show()
                self.ventana_qr.raise_()
                self.ventana_qr.activateWindow()
            except Exception as e:
                log(f"Error abriendo ventana QR: {e}")

        if hasattr(self.app, "cara") and hasattr(self.app.cara, "root") and hasattr(self.app.cara.root, "after"):
            self.app.cara.root.after(100, _mostrar_dialogo)

    def accion_ocultar_en_tablet(self):
        """Detiene el servidor y actualiza estado.json."""
        self.detener_servidor()
        d = estado.cargar()
        d["remota_activa"] = False
        estado.guardar(d)
        if self.ventana_qr is not None:
            try:
                self.ventana_qr.close()
                self.ventana_qr = None
            except Exception:
                pass
        self.app.cola.put(("hablar", "Pantalla remota desactivada."))

    def accion_modo_privado(self):
        """Activa el modo privado en la tablet ocultando recordatorios y notas."""
        d = estado.cargar()
        d["tablet_modo_privado"] = True
        estado.guardar(d)
        self.registrar_evento("Modo privado activado")
        self.app.cola.put(("hablar", "Modo privado de la tablet activado. Datos confidenciales ocultos."))

    def accion_modo_normal(self):
        """Activa el modo normal en la tablet mostrando recordatorios y notas."""
        d = estado.cargar()
        d["tablet_modo_privado"] = False
        estado.guardar(d)
        self.registrar_evento("Modo normal activado")
        self.app.cola.put(("hablar", "Modo normal de la tablet activado. Mostrando datos."))


def instalar(app):
    """Instala el módulo de pantalla remota y registra sus acciones en Silvestra."""
    gestor = GestorPantallaRemota(app)
    app.pantalla_remota = gestor
    reg = acciones.registrar
    reg("mostrar_en_tablet", gestor.accion_mostrar_en_tablet, "muestra la interfaz Jarvis en tablet con QR y enlace.", con_texto=True)
    reg("ocultar_en_tablet", gestor.accion_ocultar_en_tablet, "apaga el servidor de pantalla remota para tablet.")
    reg("tablet_modo_privado", gestor.accion_modo_privado, "oculta datos sensibles en la tablet.")
    reg("tablet_modo_normal", gestor.accion_modo_normal, "muestra datos normales en la tablet.")
    log("Módulo de pantalla remota instalado.")
    return gestor
