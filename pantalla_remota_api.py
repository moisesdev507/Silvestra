"""REST/SSE del HUD; la identidad y ejecución se delegan al puente seguro."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
import json

from ecosistema_contratos import Scope, serializar_seguro
from pantalla_remota_datos import recolectar_estado_completo

ACCIONES_PERMITIDAS = {
    "tablet_modo_privado", "tablet_modo_normal", "crear_respaldo",
    "ocultar_tarjeta", "toggle_solo_dueno", "reforzar_mi_voz",
    "reforzar_voz", "activar_modo",
}
_SENSIBLES = {"crear_respaldo", "toggle_solo_dueno", "reforzar_mi_voz",
              "reforzar_voz", "activar_modo"}
_POOL = ThreadPoolExecutor(2)
_POOL_SLOTS = BoundedSemaphore(16)


def _respuesta(h, code, body, cookie=None):
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


def _identidad(h, scope=None):
    p = h.server.gestor.puente; manager = h.server.gestor.ecosistema_gestor
    if not _origen(h, True, bool(h.headers.get("Cookie"))): return None
    cookie = manager.cookie_value(h.headers.get("Cookie"))
    identity = p.autenticar(h.headers, cookie)
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
    _respuesta(h, 200, {"ok": True, "device_id": identity["device_id"],
                        "tipo_dispositivo": identity["tipo_dispositivo"]})


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
    if "?" in h.path: return _respuesta(h, 400, {"error": "query_credentials_forbidden"})
    p = gestor.puente; manager = gestor.ecosistema_gestor
    ip = h.client_address[0]
    if path == "/api/emparejar":
        if not _origen(h, True): return _respuesta(h, 403, {"error": "origin_rejected"})
        if not h.server.bus_sse.permitir_peticion("pair:" + ip): return _respuesta(h, 429, {"error": "rate_limited"})
        body = _body(h); result = manager.canjear_codigo(body.get("codigo") if body else None)
        if not result: return _respuesta(h, 403, {"error": "pairing_rejected"})
        cookie = manager.cookie_header(result["cookie"], secure=h.server.tls)
        return _respuesta(h, 200, {"ok": True, "device_id": result["device_id"],
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
    body = _body(h) if path == "/api/panel/accion" else None
    if path == "/api/panel/accion":
        name = str((body or {}).get("accion", ""))
        if name not in ACCIONES_PERMITIDAS: return _respuesta(h, 400, {"error": "action_not_allowed"})
        if name in {"tablet_modo_privado", "tablet_modo_normal", "ocultar_tarjeta"}:
            identity = _identidad(h, Scope.UI_CONTROL)
            if not identity: return _respuesta(h, 403, {"error": "ui_scope_required"})
            if name == "ocultar_tarjeta": gestor.ocultar_tarjeta()
            else: manager.set_privado(name == "tablet_modo_privado")
            return _respuesta(h, 200, {"ok": True, "accion": name})
    identity = _identidad(h, Scope.OPERATION_REQUEST)
    if not identity: return _respuesta(h, 403, {"error": "unauthorized_or_scope_missing"})
    body = body if body is not None else _body(h)
    if path == "/api/panel/comando":
        text = str((body or {}).get("texto", "")).strip()
        if not text or len(text) > 500: return _respuesta(h, 400, {"error": "invalid_text"})
        command = p.command(identity, "conversacion_tablet", {"texto": text})
        import ecosistema_eventos
        if not ecosistema_eventos.encolar_turno(p, app, identity, text, command):
            return _respuesta(h, 429, {"error": "turn_in_progress_or_queue_full"})
        gestor.registrar_evento("Consulta recibida de dispositivo " + identity["device_id"][:8])
        return _respuesta(h, 202, {"ok": True, "message_id": command.message_id})
    if path == "/api/panel/accion":
        name = str((body or {}).get("accion", ""))
        cmd = p.command(identity, name, {"parametros": {}}, name in _SENSIBLES)
        if cmd.payload["sensible"]:
            pending = p.guardar_pendiente(identity, cmd)
            p.bus.publicar({"device_id": identity["device_id"], "message_id": pending}, "approval_required")
            return _respuesta(h, 202, {"ok": True, "estado": "pendiente_autorizacion", "message_id": pending})
        if not _lanzar(h, identity, cmd): return _respuesta(h, 429, {"error": "execution_queue_full"})
        return _respuesta(h, 202, {"ok": True, "estado": "en_validacion_central", "message_id": cmd.message_id})
    return _respuesta(h, 404, {"error": "not_found"})
