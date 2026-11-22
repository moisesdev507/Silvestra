"""REST/SSE del HUD; la identidad y ejecución se delegan al puente seguro."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
import hmac
import http.server
import ipaddress
import json
import socket
import sys

import estado
from ecosistema_contratos import Scope, TipoDispositivo, serializar_seguro
from pantalla_remota_datos import recolectar_estado_completo


def log(mensaje):
    print(f"[pantalla_remota] {mensaje}", flush=True)


def obtener_ip_local():
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
            try: s.close()
            except Exception: pass


_RED_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
_RED_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _instalar_rutas_movil(handler_cls):
    if handler_cls and not getattr(handler_cls, "_movil_instalado", False):
        orig_do_get = getattr(handler_cls, "do_GET", None)
        if callable(orig_do_get):
            def do_GET_movil(self):
                p = self.path.split("?", 1)[0]
                if p.startswith("/movil") or p in ("/manifest.json", "/sw.js", "/icon-192.png", "/icon-512.png"):
                    import app_movil_ui
                    if app_movil_ui.despachar_get_movil(self, p):
                        return
                return orig_do_get(self)
            handler_cls.do_GET = do_GET_movil
            handler_cls._movil_instalado = True


class ServidorPantallaRemota(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        _instalar_rutas_movil(RequestHandlerClass)
        super().__init__(server_address, RequestHandlerClass, bind_and_activate=bind_and_activate)

    def handle_error(self, request, client_address):
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        if isinstance(exc_val, (OSError, socket.error)):
            winerror = getattr(exc_val, "winerror", None) or getattr(exc_val, "errno", None)
            if winerror in (10053, 10054, 10058, 32):
                return
        try:
            super().handle_error(request, client_address)
        except Exception:
            pass

ACCIONES_PERMITIDAS = {
    "tablet_modo_privado", "tablet_modo_normal", "crear_respaldo",
    "ocultar_tarjeta", "toggle_solo_dueno", "reforzar_mi_voz",
    "reforzar_voz", "activar_modo",
}
_SENSIBLES = {"crear_respaldo", "toggle_solo_dueno", "reforzar_mi_voz",
              "reforzar_voz", "activar_modo"}
_POOL = ThreadPoolExecutor(2)
_POOL_SLOTS = BoundedSemaphore(16)


def _es_lan_cliente(client_ip):
    if not client_ip: return False
    cip = str(client_ip).strip("[]")
    if "%" in cip: cip = cip.split("%")[0]
    if cip in ("127.0.0.1", "localhost", "::1"): return True
    try:
        ip = ipaddress.ip_address(cip)
        return ip.is_private or ip.is_loopback or ip in _RED_TAILSCALE or ip in _RED_TAILSCALE_V6
    except Exception:
        if ":" in cip and "::" not in cip:
            try:
                ip = ipaddress.ip_address(cip.split(":")[0])
                return ip.is_private or ip in _RED_TAILSCALE
            except Exception: pass
        return False


def _respuesta(h, code, body, cookie=None):
    cookie = cookie or getattr(h, "_lan_cookie", None)
    raw = serializar_seguro(body).encode("utf-8")
    h.send_response(code)
    for k, v in h.server.gestor.puente.cors(h.headers.get("Origin", ""),
            h.headers.get("Host", ""), h.server.tls).items(): h.send_header(k, v)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(raw)))
    if cookie: h.send_header("Set-Cookie", cookie)
    h.end_headers()
    try: h.wfile.write(raw)
    except OSError: pass


def _origen(h, mutacion=False, cookie=False):
    p = h.server.gestor.puente
    return p.validar_origen(h.headers.get("Origin", ""), h.headers.get("Host", ""),
                            h.server.tls, mutacion, cookie)


def _identidad(h, scope=None, mutacion=None):
    if mutacion is None:
        mutacion = (getattr(h, "command", "") == "POST")
    p = h.server.gestor.puente; manager = h.server.gestor.ecosistema_gestor
    cookie = manager.cookie_value(h.headers.get("Cookie"))
    token = h.headers.get("X-Device-Token")
    if not _origen(h, mutacion, bool(cookie or token)): return None
    identity = p.autenticar(h.headers, cookie)
    if not identity and token:
        rem_tok = getattr(h.server.gestor, "token", "") or estado.cargar().get("remota_token", "")
        if rem_tok and hmac.compare_digest(str(token).strip(), str(rem_tok).strip()):
            identity = {"device_id": "movil_owner", "tipo_dispositivo": "movil",
                        "scopes": frozenset([Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST])}
    if not identity and _es_lan_cliente(getattr(h, "client_address", ("",))[0]):
        pair = manager.emparejar_lan(TipoDispositivo.TABLET_HUD,
                                     (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST))
        if pair:
            identity = manager.autenticar_token(pair["token"]) or pair
            h._lan_cookie = manager.cookie_header(pair["cookie"], secure=h.server.tls, samesite="Lax")
            h._lan_token = pair.get("token", "")
    if identity and scope and not manager.autorizar(identity, scope): return None
    if identity and not h.server.bus_sse.permitir_peticion(identity["device_id"]): return None
    return identity


def _body(h):
    try:
        size = int(h.headers.get("Content-Length", 0))
        if size <= 0 or size > 8192: return None
        data = json.loads(h.rfile.read(size).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception: return None


def responder_sesion(h, identity):
    lan_c = getattr(h, "_lan_cookie", None)
    if not identity:
        tok = (h.headers.get("X-Device-Token") or "").strip()
        rem_tok = getattr(h.server.gestor, "token", "") or estado.cargar().get("remota_token", "")
        if tok and rem_tok and hmac.compare_digest(tok, str(rem_tok).strip()):
            identity = {"device_id": "movil_owner", "tipo_dispositivo": "movil",
                        "scopes": frozenset([Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST])}
    if not identity and _es_lan_cliente(getattr(h, "client_address", ("",))[0]):
        manager = h.server.gestor.ecosistema_gestor
        pair = manager.emparejar_lan(TipoDispositivo.TABLET_HUD,
                                     (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST))
        if pair:
            identity = manager.autenticar_token(pair["token"]) or pair
            lan_c = manager.cookie_header(pair["cookie"], secure=h.server.tls, samesite="Lax")
            h._lan_token = pair.get("token", "")
    if not identity:
        return _respuesta(h, 401, {"ok": False, "error": "No autenticado"})
    tok = getattr(h, "_lan_token", "") or (identity.get("token", "") if isinstance(identity, dict) else "")
    _respuesta(h, 200, {"ok": True, "device_id": identity["device_id"],
                        "token": tok,
                        "tipo_dispositivo": identity["tipo_dispositivo"]}, cookie=lan_c)


def responder_estado(h, app, gestor):
    datos = recolectar_estado_completo(app, gestor)
    privado = gestor.ecosistema_gestor.modo_privado()
    datos = gestor.puente.filtrar_estado(datos, privado)
    _respuesta(h, 200, datos)


def manejar_sse(h, identity, detener):
    return h.server.bus_sse.servir_http(h, detener, h.server.gestor.puente, identity)


def _lanzar(h, identity, command, approval=None):
    if not _POOL_SLOTS.acquire(blocking=False): return False
    bridge = h.server.gestor.puente; app = h.server.app
    def run():
        try:
            result = bridge.ejecutar_controlado(app, identity, command, approval)
            bridge.bus.publicar({"message_id": command.message_id, **result}, "command_result")
        finally: _POOL_SLOTS.release()
    try: _POOL.submit(run); return True
    except RuntimeError: _POOL_SLOTS.release(); return False


def manejar_options(h):
    if not _origen(h, True, True): return _respuesta(h, 403, {"error": "origin_rejected"})
    h.send_response(204)
    for k, v in h.server.gestor.puente.cors(h.headers.get("Origin", ""), h.headers.get("Host", ""), h.server.tls).items(): h.send_header(k, v)
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Authorization, X-Device-Token, Content-Type")
    h.send_header("Access-Control-Max-Age", "300"); h.end_headers()


def manejar_post(h, app, gestor):
    path = h.path.split("?", 1)[0]
    p = gestor.puente; manager = gestor.ecosistema_gestor
    ip = h.client_address[0]
    if path.startswith("/api/movil/"):
        tok = (h.headers.get("X-Device-Token") or "").strip()
        if not tok and "Authorization" in h.headers:
            auth = h.headers.get("Authorization", "").strip()
            if auth.lower().startswith("bearer "): tok = auth[7:].strip()
        if not tok and "?token=" in h.path:
            try: tok = h.path.split("?token=", 1)[1].split("&", 1)[0].strip()
            except Exception: pass
        rem_tok = getattr(gestor, "token", "") or estado.cargar().get("remota_token", "")
        rem_tok = str(rem_tok).strip()
        es_valido = bool(tok and rem_tok and hmac.compare_digest(tok, rem_tok))
        identity = ({"device_id": "movil_owner", "tipo_dispositivo": "movil",
                     "scopes": frozenset([Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST])}
                    if es_valido else _identidad(h))
        if not identity:
            return _respuesta(h, 401, {"ok": False, "error": "unauthorized"})
        import app_movil_audio
        code, res = app_movil_audio.manejar_http_movil(h, app, path)
        return _respuesta(h, code, res)

    if path == "/api/emparejar":
        if not _origen(h, True): return _respuesta(h, 403, {"error": "origin_rejected"})
        if not h.server.bus_sse.permitir_peticion("pair:" + ip): return _respuesta(h, 429, {"error": "rate_limited"})
        body = _body(h); result = manager.canjear_codigo(body.get("codigo") if body else None)
        if not result: return _respuesta(h, 403, {"error": "pairing_rejected"})
        cookie = manager.cookie_header(result["cookie"], secure=h.server.tls)
        return _respuesta(h, 200, {"ok": True, "device_id": result["device_id"],
            "token": result.get("token", ""),
            "tipo_dispositivo": result["tipo_dispositivo"]}, cookie)
    if path == "/api/heartbeat":
        identity = _identidad(h)
        if not identity: return _respuesta(h, 403, {"error": "unauthorized"})
        ok = manager.heartbeat(identity)
        return _respuesta(h, 200 if ok else 401, {"ok": ok})
    if path == "/api/panel/observacion":
        identity = _identidad(h, Scope.SENSOR_SUBMIT)
        if not identity: return _respuesta(h, 403, {"error": "sensor_scope_required"})
        body = _body(h)
        obs = p.observation(identity, (body or {}).get("observacion", {}))
        app.cola.put(("ecosistema_observacion", obs.a_dict()))
        return _respuesta(h, 202, {"ok": True, "message_id": obs.message_id, "ejecutable": False})
    if path == "/api/panel/aprobar":
        approval_identity = _identidad(h, Scope.OPERATION_APPROVE)
        if not approval_identity: return _respuesta(h, 403, {"error": "approval_scope_required"})
        body = _body(h); mid = str((body or {}).get("message_id", ""))
        try: request_identity, cmd, approval = p.aprobar_pendiente(approval_identity, mid)
        except (ValueError, PermissionError): return _respuesta(h, 403, {"error": "approval_rejected"})
        if not _lanzar(h, request_identity, cmd, approval): return _respuesta(h, 429, {"error": "execution_queue_full"})
        return _respuesta(h, 202, {"ok": True, "estado": "en_validacion_central", "message_id": mid})

    rutas_accion = {"/api/panel/accion", "/api/panel/modo", "/api/panel/solo_dueno", "/api/panel/reforzar_voz"}
    if path in rutas_accion:
        identity = _identidad(h, Scope.UI_CONTROL) or _identidad(h, Scope.OPERATION_REQUEST)
        if not identity: return _respuesta(h, 403, {"error": "unauthorized"})
        body = _body(h) or {}
        name = str(body.get("accion", ""))
        if path == "/api/panel/modo": name = "activar_modo"
        elif path == "/api/panel/solo_dueno": name = "toggle_solo_dueno"
        elif path == "/api/panel/reforzar_voz": name = "reforzar_voz"
        if not name or name not in ACCIONES_PERMITIDAS:
            return _respuesta(h, 400, {"error": "action_not_allowed"})
        import pantalla_remota_accion as pra
        code, resp = pra.despachar_accion_panel(app, gestor, manager, name, body)
        return _respuesta(h, code, resp)

    identity = _identidad(h, Scope.OPERATION_REQUEST)
    if not identity: return _respuesta(h, 403, {"error": "unauthorized_or_scope_missing"})
    body = _body(h)
    if path == "/api/panel/comando":
        text = str((body or {}).get("texto", "")).strip()
        if not text or len(text) > 500: return _respuesta(h, 400, {"error": "invalid_text"})
        command = p.command(identity, "conversacion_tablet", {"texto": text})
        import ecosistema_eventos
        if not ecosistema_eventos.encolar_turno(p, app, identity, text, command):
            return _respuesta(h, 429, {"error": "turn_in_progress_or_queue_full"})
        gestor.registrar_evento("Consulta recibida de dispositivo " + identity["device_id"][:8])
        return _respuesta(h, 202, {"ok": True, "message_id": command.message_id})
    return _respuesta(h, 404, {"error": "not_found"})
