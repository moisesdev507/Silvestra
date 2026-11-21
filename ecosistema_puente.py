from datetime import datetime, timezone
from uuid import uuid4
from threading import RLock
from urllib.parse import urlsplit

from ecosistema_contratos import ApprovalRequest, CommandRequest, Observation, Scope, serializar_seguro


class EcosistemaPuente:
    def __init__(self, gestor, bus, origenes=()):
        self.gestor, self.bus = gestor, bus
        self.origenes = frozenset(str(x).rstrip("/") for x in origenes if x)
        self._lock = RLock()
        self._aprobaciones = {}
        self._pendientes = {}
        self._turno_remoto = None

    def reservar_turno(self, identity, cerrar=False):
        key = (identity.get("device_id"), identity.get("session_id"))
        with self._lock:
            if cerrar:
                found = self._turno_remoto == key
                if found: self._turno_remoto = None
                return found
            if self._turno_remoto: return False
            self._turno_remoto = key; return True

    def autenticar(self, headers, cookie=""):
        token = str(headers.get("X-Device-Token", ""))
        auth = str(headers.get("Authorization", ""))
        if auth.lower().startswith("bearer "): token = auth[7:].strip()
        identity = self.gestor.autenticar_token(token) if token else None
        return identity or (self.gestor.autenticar_cookie(cookie) if cookie else None)

    def validar_origen(self, origin, host, secure=False, mutacion=False, cookie=False):
        if not origin:
            hosts = {urlsplit(x).netloc.lower() for x in self.origenes}
            return not mutacion and str(host).lower() in hosts
        try:
            p = urlsplit(origin)
            if p.path or p.query or p.fragment or p.username or p.password: return False
            if p.scheme != ("https" if secure else "http"): return False
            normalized = f"{p.scheme}://{p.netloc}".lower().rstrip("/")
            return normalized in self.origenes and p.netloc.lower() == str(host).lower()
        except Exception:
            return False

    def cors(self, origin, host, secure=False):
        if self.validar_origen(origin, host, secure):
            return {"Access-Control-Allow-Origin": origin,
                    "Vary": "Origin", "Access-Control-Allow-Credentials": "true"}
        return {}

    @staticmethod
    def filtrar_estado(datos, privado=False):
        if not privado: return datos
        reloj = (datos.get("datos", {}).get("reloj") if isinstance(datos, dict) else None)
        return {"telemetria": {"modo_privado": True},
                "silvestra": {"estado": "privado", "subtitulo": "",
                              "tarjeta": "MODO PRIVADO ACTIVO // INFORMACIÓN OCULTA"},
                "biometria": None, "contexto": None,
                "datos": {"recordatorios": [], "notas": [], "eventos": [], "reloj": reloj},
                "ts": datos.get("ts") if isinstance(datos, dict) else None}

    def observation(self, identity, payload):
        if not self.gestor.autorizar(identity, Scope.SENSOR_SUBMIT):
            raise PermissionError("scope sensor:submit requerido")
        return Observation("1.0", str(uuid4()), str(uuid4()), identity["device_id"],
                           identity["session_id"], datetime.now(timezone.utc).isoformat(),
                           payload=payload)

    def command(self, identity, operation, payload=None, sensitive=False):
        if not self.gestor.autorizar(identity, Scope.OPERATION_REQUEST):
            raise PermissionError("scope operation:request requerido")
        body = dict(payload or {})
        body["operacion"] = str(operation)
        body["sensible"] = bool(sensitive)
        return CommandRequest("1.0", str(uuid4()), str(uuid4()), identity["device_id"],
                              identity["session_id"], datetime.now(timezone.utc).isoformat(),
                              payload=body)

    def aprobar(self, identity, command, decision="approved"):
        if not isinstance(command, CommandRequest): raise TypeError("CommandRequest requerido")
        if not self.gestor.autorizar(identity, Scope.OPERATION_APPROVE):
            raise PermissionError("scope operation:approve requerido")
        if identity.get("tipo_dispositivo") not in ("pc_nucleo", "telefono_movil"):
            raise PermissionError("dispositivo aprobador no autorizado")
        if identity["device_id"] == command.device_id:
            raise PermissionError("el solicitante no puede aprobar su propio comando")
        approval = ApprovalRequest("1.0", str(uuid4()), command.correlation_id,
            identity["device_id"], identity["session_id"], datetime.now(timezone.utc).isoformat(),
            payload={"command_message_id": command.message_id, "decision": decision})
        with self._lock: self._aprobaciones[command.message_id] = (approval, dict(identity))
        return approval

    def guardar_pendiente(self, identity, command):
        if not self.gestor.autorizar(identity, Scope.OPERATION_REQUEST):
            raise PermissionError("scope operation:request requerido")
        if command.device_id != identity.get("device_id"):
            raise PermissionError("el dispositivo no coincide con el sobre")
        with self._lock:
            self._pendientes[command.message_id] = (identity, command)
        return command.message_id

    def aprobar_pendiente(self, identity, message_id):
        with self._lock: pending = self._pendientes.get(str(message_id))
        if not pending: raise ValueError("solicitud inexistente o ya resuelta")
        approval = self.aprobar(identity, pending[1])
        return pending[0], pending[1], approval

    def ejecutar_controlado(self, app, identity, command, approval=None):
        if not self.validar_ejecucion(identity, command, approval):
            if command.payload.get("sensible") and approval is None:
                return {"estado": "pendiente_autorizacion", "message_id": self.guardar_pendiente(identity, command)}
            return {"estado": "rechazada", "motivo": "scope_o_aprobacion_invalida"}
        integration = getattr(app, "integracion_cognitiva", None)
        if integration is None:
            return {"estado": "rechazada", "motivo": "integracion_no_disponible"}
        try:
            from ejecucion_modelo import SolicitudEjecucion
            params = command.payload.get("parametros", {})
            if not isinstance(params, dict): return {"estado": "rechazada", "motivo": "parametros_invalidos"}
            req = SolicitudEjecucion("usuario", command.payload["operacion"], params)
            result = integration.ejecutar_solicitud(req)
            value = result.get("resultado") if isinstance(result, dict) else result
            meta = getattr(value, "metadatos", {}) or {}
            auth = meta.get("id_autorizacion") if isinstance(meta, dict) else None
            if approval and auth:
                confirmed = integration.motor_permisos.confirmar_autorizacion(auth, actor="usuario")
                if not confirmed.get("aprobada"):
                    return {"estado": "pendiente_autorizacion", "motivo": "permiso_central_no_confirmado"}
                result = integration.ejecutar_solicitud(req)
            with self._lock: self._pendientes.pop(command.message_id, None)
            value = result.get("resultado") if isinstance(result, dict) else result
            return {"estado": getattr(value, "estado", "completada"),
                    "id_solicitud": getattr(result, "id_solicitud", req.id_solicitud)}
        except Exception as exc:
            return {"estado": "rechazada", "motivo": type(exc).__name__}

    def validar_ejecucion(self, identity, command, approval=None):
        if not isinstance(command, CommandRequest): return False
        if not self.gestor.autorizar(identity, Scope.OPERATION_REQUEST): return False
        if command.device_id != identity.get("device_id"): return False
        if not command.payload.get("sensible"): return True
        with self._lock: registrada = self._aprobaciones.get(command.message_id)
        return bool(isinstance(approval, ApprovalRequest) and registrada and
                    approval is registrada[0] and self.gestor.autorizar(registrada[1], Scope.OPERATION_APPROVE) and
                    approval.payload.get("decision") == "approved" and
                    approval.payload.get("command_message_id") == command.message_id and
                    approval.device_id != command.device_id)
