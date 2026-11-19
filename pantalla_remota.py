"""Servidor local HTTP y SSE para mostrar la cara de Silvestra en una tablet."""
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse

import acciones
import casa_web
import estado
from pantalla_remota_panel import GestorPanelRemoto, VentanaQR
from pantalla_remota_web import PAGINA_HTML

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


class PantallaRemotaHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP que valida token, sirve la página web y emite eventos SSE."""

    def log_message(self, format, *args):
        # Desactivar logs por defecto de BaseHTTPRequestHandler en consola
        pass

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        if casa_web.manejar_get(self, url_parsed):
            return

        query = urllib.parse.parse_qs(url_parsed.query)
        token_cliente = query.get("token", [""])[0]

        if token_cliente != self.server.token_autorizado:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Acceso denegado: token inválido o no suministrado.".encode("utf-8"))
            log(f"Intento de acceso rechazado desde {self.client_address[0]}")
            return

        if url_parsed.path in ("/", "/index.html"):
            contenido = PAGINA_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(contenido)
            log(f"Página servida a cliente en {self.client_address[0]}")
            return

        if url_parsed.path == "/eventos":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            log(f"Conexión de eventos SSE establecida desde {self.client_address[0]}")
            ultimo_panel = 0.0
            try:
                while not self.server.detener_event.is_set():
                    ahora_t = time.time()
                    datos = self.server.gestor.obtener_estado_dict()
                    if ahora_t - ultimo_panel >= 10.0 or ultimo_panel == 0.0:
                        if hasattr(self.server.gestor, "panel") and self.server.gestor.panel:
                            datos["panel"] = self.server.gestor.panel.obtener_datos()
                        ultimo_panel = ahora_t

                    payload = json.dumps(datos, ensure_ascii=False)
                    msg = f"data: {payload}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                log(f"Fin de flujo SSE con {self.client_address[0]}: {e}")
            finally:
                log(f"Conexión SSE cerrada desde {self.client_address[0]}")
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        url_parsed = urllib.parse.urlparse(self.path)
        if casa_web.manejar_post(self, url_parsed):
            return
        self.send_response(404)
        self.end_headers()


class GestorPantallaRemota:
    """Orquesta el ciclo de vida del servidor HTTP local y la publicación de estado."""

    def __init__(self, app):
        self.app = app
        self._servidor = None
        self._hilo = None
        self._detener_event = threading.Event()
        self.ventana_qr = None
        self.panel = GestorPanelRemoto(app)
        casa_web.obtener_gestor_casa(app)

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

    def obtener_url_completa(self):
        """Devuelve la URL accesible desde la red local para la tablet."""
        ip = obtener_ip_local()
        return f"http://{ip}:{self.puerto}/?token={self.token}"

    def obtener_estado_dict(self):
        """Lee el estado en vivo de Silvestra sin bloquear ni invocar métodos Qt."""
        with _lock:
            descansando = getattr(self.app, "descansando", False)
            escuchando = getattr(self.app, "escuchando", False)
            pensando = getattr(self.app.cara, "pensando", False)
            hablando = False
            voz = getattr(self.app, "voz", None)
            if voz and hasattr(voz, "ocupada"):
                try:
                    hablando = voz.ocupada()
                except Exception:
                    hablando = False

            if descansando:
                est = "dormida"
            elif hablando:
                est = "hablando"
            elif pensando:
                est = "pensando"
            elif escuchando:
                est = "escuchando"
            else:
                est = "reposo"

            emocion = getattr(self.app.cara, "emocion_objetivo", "neutral") or "neutral"
            vol = float(getattr(voz, "nivel_volumen", 0.0) if voz else 0.0)
            subtitulo = getattr(self.app, "ultimo_dicho", "") if hablando else ""
            cara_activa = False
            pres = getattr(self.app, "presencia", None)
            if pres and getattr(pres, "activa", False) and getattr(pres, "ausente", False):
                cara_activa = True

            return {
                "estado": est,
                "emocion": emocion,
                "volumen": vol,
                "subtitulo": subtitulo,
                "cara_activa": cara_activa,
                "t": time.time(),
            }

    def iniciar_servidor(self):
        """Inicia el servidor HTTP en un hilo secundario daemon."""
        if self._servidor is not None:
            return True

        self._detener_event.clear()
        try:
            servidor = http.server.ThreadingHTTPServer(("0.0.0.0", self.puerto), PantallaRemotaHandler)
            servidor.token_autorizado = self.token
            servidor.detener_event = self._detener_event
            servidor.gestor = self
            self._servidor = servidor

            def _correr():
                log(f"Servidor iniciado en http://0.0.0.0:{self.puerto}")
                try:
                    servidor.serve_forever()
                except Exception as ex:
                    log(f"Servidor finalizado: {ex}")

            self._hilo = threading.Thread(target=_correr, daemon=True, name="ServidorPantallaRemota")
            self._hilo.start()
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

    def accion_mostrar_en_tablet(self):
        """Inicia la pantalla remota, copia la URL y abre la ventana con el código QR."""
        ok = self.iniciar_servidor()
        d = estado.cargar()
        d["remota_activa"] = True
        estado.guardar(d)

        url = self.obtener_url_completa()

        self.app.cola.put(("copiar_portapapeles", url))
        msg_voz = "Pantalla remota lista en tu red local. Ya copié la dirección al portapapeles."
        burbuja = f"📱 PANTALLA REMOTA:\n{url}\n\n(Enlace copiado al portapapeles)"
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

        # Programar la apertura de la ventana de forma segura en el hilo de Qt
        if hasattr(self.app.cara, "root") and hasattr(self.app.cara.root, "after"):
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
        """Activa el modo privado en la tablet ocultando los recordatorios."""
        if hasattr(self, "panel") and self.panel:
            self.panel.fijar_modo_privado(True)
        self.app.cola.put(("hablar", "Modo privado de la tablet activado. Oculté los recordatorios."))

    def accion_modo_normal(self):
        """Activa el modo normal en la tablet mostrando los recordatorios."""
        if hasattr(self, "panel") and self.panel:
            self.panel.fijar_modo_privado(False)
        self.app.cola.put(("hablar", "Modo normal de la tablet activado. Mostrando recordatorios."))

    def accion_mostrar_casa_tablet(self):
        """Inicia servidor si hace falta y copia la URL de la casa virtual."""
        self.iniciar_servidor()
        ip = obtener_ip_local()
        url = f"http://{ip}:{self.puerto}/casa"
        self.app.cola.put(("copiar_portapapeles", url))
        msg = "Casa virtual lista en tu tablet o navegador. Ya copié el enlace al portapapeles."
        burbuja = f"🏠 CASA VIRTUAL:\n{url}\n\n(Enlace copiado al portapapeles)"
        self.app.cola.put(("hablar_registro", (msg, burbuja)))


def instalar(app):
    """Instala el módulo de pantalla remota y registra sus acciones en Silvestra."""
    gestor = GestorPantallaRemota(app)
    app.pantalla_remota = gestor

    acciones.registrar(
        "mostrar_en_tablet",
        lambda: gestor.accion_mostrar_en_tablet(),
        "muestra la cara de Silvestra en una tablet o pantalla remota de la red local con un código QR y enlace.",
    )
    acciones.registrar(
        "ocultar_en_tablet",
        lambda: gestor.accion_ocultar_en_tablet(),
        "apaga el servidor de pantalla remota para tablet.",
    )
    acciones.registrar(
        "tablet_modo_privado",
        lambda: gestor.accion_modo_privado(),
        "activa el modo privado en la tablet para ocultar los recordatorios del panel de reloj.",
    )
    acciones.registrar(
        "tablet_modo_normal",
        lambda: gestor.accion_modo_normal(),
        "activa el modo normal en la tablet para mostrar los recordatorios en el panel de reloj.",
    )
    acciones.registrar(
        "mostrar_casa_tablet",
        lambda: gestor.accion_mostrar_casa_tablet(),
        "muestra el plano 2D interactivo de la casa virtual para tablet en el navegador web local.",
    )

    log("Módulo de pantalla remota instalado.")
    return gestor
