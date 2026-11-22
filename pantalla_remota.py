"""Servidor local HTTP y SSE para mostrar la interfaz Jarvis de Silvestra en una tablet."""
import http.server
import json
import os
import socket
import ssl
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
from ecosistema_almacen import AlmacenEcosistema
from ecosistema_contratos import Scope, TipoDispositivo
from ecosistema_gestor import GestorEcosistema
from ecosistema_puente import EcosistemaPuente
from ecosistema_sse import BusSSE

PUERTO_DEFECTO = 8765
_lock = threading.Lock()


log = _api.log
obtener_ip_local = _api.obtener_ip_local
ServidorPantallaRemota = _api.ServidorPantallaRemota


class PantallaRemotaHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP que valida token, sirve el HUD Jarvis y emite eventos en tiempo real."""

    def log_message(self, format, *args):
        # Desactivar logs por defecto en consola para mantener el terminal limpio
        pass

    def _identidad(self, scope, mutacion=False):
        try:
            manager = self.server.gestor.ecosistema_gestor
            cookie_val = manager.cookie_value(self.headers.get("Cookie"))
            identity = self.server.puente.autenticar(self.headers, cookie_val)
            origin = self.headers.get("Origin", "")
            if not self.server.puente.validar_origen(
                    origin, self.headers.get("Host", ""), self.server.tls,
                    mutacion, bool(self.headers.get("Cookie"))):
                return None
            if not identity and _api._es_lan_cliente(self.client_address[0]):
                pair = manager.emparejar_lan(TipoDispositivo.TABLET_HUD,
                                             (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST))
                if pair:
                    identity = pair
                    self._lan_cookie = manager.cookie_header(pair["cookie"], secure=self.server.tls)
            if not identity: return None
            if not manager.autorizar(identity, scope): return None
            if not self.server.bus_sse.permitir_peticion(identity["device_id"]): return None
            self._notificar_conexion_tablet()
            return identity
        except Exception:
            return None

    def _denegar(self, code=403):
        self.send_response(code); self.send_header("Cache-Control", "no-store"); self.end_headers()

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
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.query: return self._denegar(400)
        path = parsed.path
        if path in ("/", "/index.html"):
            contenido = PAGINA_JARVIS_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(contenido)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            return
        if path == "/api/sesion":
            identity = self._identidad(Scope.STATE_READ)
            return _api.responder_sesion(self, identity)
        identity = self._identidad(Scope.STATE_READ)
        if not identity: return self._denegar()
        if path == "/api/panel/estado":
            return _api.responder_estado(self, self.server.app, self.server.gestor)
        if path == "/eventos":
            return _api.manejar_sse(self, identity, self.server.detener_event)
        self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        _api.manejar_options(self)

    def do_POST(self):
        _api.manejar_post(self, getattr(self.server, "app", None), self.server.gestor)


class GestorPantallaRemota:
    """Orquesta el servidor HTTP local, el estado Jarvis y las acciones de la tablet."""

    def __init__(self, app):
        self.app = app
        self._servidor = None
        self._hilo = None
        self._publisher = None
        self._detener_event = threading.Event()
        self._host = "127.0.0.1"
        self._tls = False
        self.ecosistema_gestor = GestorEcosistema(AlmacenEcosistema())
        if self.ecosistema_gestor.identidad_nucleo() is None:
            self.ecosistema_gestor.registrar_local(TipoDispositivo.PC_NUCLEO,
                (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST, Scope.OPERATION_APPROVE))
        self.bus_sse = BusSSE()
        self.puente = EcosistemaPuente(self.ecosistema_gestor, self.bus_sse)
        self._ultimo_estado = {}
        self.ventana_qr = None
        self.tarjeta_principal = "LYRIS VIRTUAL INTERFACE // SISTEMA OPERATIVO"
        self.tablet_conectada = False
        self.ultimos_eventos = [
            {"hora": time.strftime("%H:%M"), "texto": "Servidor HUD Lyris inicializado"},
            {"hora": time.strftime("%H:%M"), "texto": "Esperando conexión de tablet"},
        ]

        d = estado.cargar()
        self.puerto = d.get("remota_puerto", PUERTO_DEFECTO)
        self.activa = d.get("remota_activa", False)

        if self.activa:
            if os.path.exists("hud_cert.pem") and os.path.exists("hud_key.pem"):
                self.activar_red_tls("hud_cert.pem", "hud_key.pem", "0.0.0.0")
            else:
                self.iniciar_servidor()

    def registrar_evento(self, texto):
        """Registra un evento visible en el terminal del panel Jarvis."""
        with _lock:
            self.ultimos_eventos.append({"hora": time.strftime("%H:%M"), "texto": texto})
            if len(self.ultimos_eventos) > 8:
                self.ultimos_eventos.pop(0)

    def obtener_url_completa(self):
        """Devuelve el origen del HUD; no incluye credenciales en la URL."""
        host = self._host
        if host in ("0.0.0.0", "", "127.0.0.1"):
            host = obtener_ip_local() if self._tls else "127.0.0.1"
        scheme = "https" if self._tls else "http"
        return f"{scheme}://{host}:{self.puerto}/"

    def iniciar_servidor(self, host=None, contexto_tls=None):
        """Inicia en loopback; una interfaz externa requiere TLS explícito."""
        if self._servidor is not None:
            return True
        host = host or self._host
        externo = host not in ("127.0.0.1", "::1", "localhost")
        if externo and contexto_tls is None: return False
        self._detener_event.clear()
        try:
            servidor = ServidorPantallaRemota((host, self.puerto), PantallaRemotaHandler)
            if contexto_tls: servidor.socket = contexto_tls.wrap_socket(servidor.socket, server_side=True)
            servidor.tls = bool(contexto_tls)
            servidor.detener_event = self._detener_event
            servidor.gestor = self
            servidor.app = self.app
            servidor.bus_sse = self.bus_sse
            scheme = "https" if contexto_tls else "http"
            ip_loc = obtener_ip_local()
            origins = [
                f"{scheme}://{host}:{self.puerto}",
                f"{scheme}://{ip_loc}:{self.puerto}",
                f"{scheme}://127.0.0.1:{self.puerto}",
                f"{scheme}://localhost:{self.puerto}",
            ]
            self.puente.origenes = frozenset(origins)
            self._servidor = servidor
            self._host, self._tls = host, bool(contexto_tls)

            def _correr():
                try:
                    servidor.serve_forever()
                except Exception:
                    pass

            self._hilo = threading.Thread(target=_correr, daemon=True, name="ServidorPantallaRemota")
            self._hilo.start()
            self._publisher = threading.Thread(target=self._publicar_estado,
                daemon=True, name="EcosistemaSSEPublisher")
            self._publisher.start()
            self.registrar_evento("Servidor HTTP online")
            return True
        except Exception:
            self._servidor = None
            return False

    def activar_red_tls(self, certificado, clave, host=None):
        """Expone la interfaz indicada y solo si el certificado TLS es válido."""
        host = host or obtener_ip_local()
        if host in ("127.0.0.1", "::1", "localhost"): return False
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(certificado, clave)
        except (OSError, ssl.SSLError, ValueError): return False
        self.detener_servidor()
        if self.iniciar_servidor(host, ctx): return self.obtener_url_completa()
        self._host, self._tls = "127.0.0.1", False
        self.iniciar_servidor()
        return ""

    def _publicar_estado(self):
        anterior = None; siguiente_scan = 0.0
        while not self._detener_event.wait(.5):
            try:
                if time.monotonic() >= siguiente_scan:
                    offline = self.ecosistema_gestor.marcar_desconectados()
                    if offline: self.bus_sse.publicar({"desconectados": len(offline)}, "device_status")
                    siguiente_scan = time.monotonic() + 30
                datos = recolectar_estado_completo(self.app, self)
                datos = self.puente.filtrar_estado(datos, self.ecosistema_gestor.modo_privado())
                self._ultimo_estado = datos
                serial = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if serial != anterior:
                    self.bus_sse.publicar(datos, "state"); anterior = serial
            except Exception:
                continue

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
            hilo = self._hilo
            self._servidor = None
            self._hilo = None
            if hilo and hilo is not threading.current_thread(): hilo.join(timeout=.5)
            if self._publisher and self._publisher is not threading.current_thread():
                self._publisher.join(timeout=.5)
            self._publisher = None
            log("Servidor detenido correctamente.")

    def accion_mostrar_en_tablet(self, arg=None):
        """Inicia la pantalla remota, copia la URL y abre la ventana con el código QR."""
        if arg and str(arg).strip():
            self.tarjeta_principal = str(arg).strip()
            self.registrar_evento(f"Proyección: {self.tarjeta_principal[:22]}")

        self.iniciar_servidor()

        url = self.obtener_url_completa()
        scopes = (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST, Scope.SENSOR_SUBMIT)

        self.app.cola.put(("copiar_portapapeles", url))
        msg_voz = "Panel Jarvis listo en tu tablet. Ya copié la dirección al portapapeles."
        burbuja = f"📱 PANEL JARVIS TABLET:\n{url}\n\n(Enlace copiado al portapapeles)"
        self.app.cola.put(("hablar_registro", (msg_voz, burbuja)))

        def emitir():
            try:
                code = self.ecosistema_gestor.emitir_codigo(TipoDispositivo.TABLET_HUD, scopes)
                self.app.cola.put(("ecosistema_mostrar_qr", (url, code)))
            except Exception:
                self.app.cola.put(("hablar", "No pude generar el código de emparejamiento."))
        threading.Thread(target=emitir, daemon=True, name="EcosistemaPairCode").start()

    def emitir_codigo_aprobador(self):
        return self.ecosistema_gestor.emitir_codigo(TipoDispositivo.TELEFONO_MOVIL,
            (Scope.STATE_READ, Scope.OPERATION_APPROVE))

    def mostrar_ventana_qr(self, url, code):
        if self.ventana_qr is not None: self.ventana_qr.close()
        self.ventana_qr = VentanaQR(url, code, self.emitir_codigo_aprobador, self.activar_red_tls)
        self.ventana_qr.show(); self.ventana_qr.raise_(); self.ventana_qr.activateWindow()

    def accion_ocultar_en_tablet(self):
        """Detiene el servidor y su publicación de eventos."""
        self.detener_servidor()
        if self.ventana_qr is not None:
            try:
                self.ventana_qr.close()
                self.ventana_qr = None
            except Exception:
                pass
        self.app.cola.put(("hablar", "Pantalla remota desactivada."))

    def accion_modo_privado(self):
        """Activa el filtro privado del ecosistema sin alterar estado.json."""
        self.ecosistema_gestor.set_privado(True)
        self.registrar_evento("Modo privado activado")
        self.app.cola.put(("hablar", "Modo privado de la tablet activado. Datos confidenciales ocultos."))

    def ocultar_tarjeta(self):
        with _lock: self.tarjeta_principal = "LYRIS VIRTUAL INTERFACE // SISTEMA OPERATIVO"

    def accion_modo_normal(self):
        """Desactiva el filtro privado del ecosistema."""
        self.ecosistema_gestor.set_privado(False)
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
    import pantalla_remota_accion as pra
    pra.registrar_acciones_hud(app, gestor)
    log("Módulo de pantalla remota instalado.")
    return gestor
