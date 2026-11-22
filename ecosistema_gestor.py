"""Emparejamiento, sesiones y permisos fail-closed para dispositivos remotos."""
from datetime import datetime, timezone
from ecosistema_sesiones import GestorSesiones
from uuid import uuid4
import base64, hashlib, hmac, secrets, time

from ecosistema_almacen import AlmacenEcosistema
from ecosistema_contratos import TipoDispositivo, Scope

_ITER = 80000
_TTL_CODIGO = 180
_TTL_SESION = 3600


def _hash(secret, salt):
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, _ITER).hex()


def _salt():
    return secrets.token_bytes(16)


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class GestorEcosistema(GestorSesiones):
    def __init__(self, almacen=None, reloj=time.time):
        super().__init__(almacen, reloj)

    def registrar_local(self, tipo, scopes=(), device_id=None, capacidades=(), version_cliente="1.0"):
        tipo = TipoDispositivo(tipo)
        scopes = self._scopes(tipo, scopes)
        capacidades = self._capacidades(tipo, capacidades)
        if not isinstance(version_cliente, str) or not version_cliente or len(version_cliente) > 64:
            raise ValueError("versión cliente inválida")
        did = str(device_id or uuid4())
        row = {"device_id": did, "tipo_dispositivo": tipo.value,
               "capacidades": list(capacidades), "version_cliente": version_cliente,
               "scopes": sorted(s.value for s in scopes),
               "revocado": False, "conectado": True, "creado_en": self._now(), "latido": self._now(),
               "session_id": str(uuid4()), "credential_version": 0,
               "token_salt": "", "token_hash": "", "sesiones": []}
        with self._lock:
            def put(data):
                if did in data["dispositivos"]: raise ValueError("device_id duplicado")
                if tipo == TipoDispositivo.PC_NUCLEO and any(
                        d["tipo_dispositivo"] == tipo.value for d in data["dispositivos"].values()):
                    raise ValueError("pc_nucleo único")
                data["dispositivos"][did] = row
            self.almacen.actualizar(put)
        return {k: v for k, v in row.items() if k not in ("token_salt", "token_hash", "sesiones")}

    def _scopes(self, tipo, scopes):
        try: result = frozenset(Scope(s) for s in scopes)
        except (ValueError, TypeError) as exc: raise ValueError("scope desconocido") from exc
        if Scope.OPERATION_APPROVE in result and tipo not in (TipoDispositivo.PC_NUCLEO, TipoDispositivo.TELEFONO_MOVIL):
            raise ValueError("solo núcleo o teléfono pueden aprobar")
        return result

    @staticmethod
    def _capacidades(tipo, values):
        caps = tuple(dict.fromkeys(str(x).strip() for x in values))
        core = {"memoria_central", "inteligencia_central", "ejecucion_central"}
        if len(caps) > 64 or any(not x or len(x) > 80 for x in caps): raise ValueError("capacidades inválidas")
        if tipo != TipoDispositivo.PC_NUCLEO and core.intersection(caps): raise ValueError("capacidad exclusiva del núcleo")
        return caps

    def emitir_codigo(self, tipo=TipoDispositivo.TABLET_HUD, scopes=(), ttl_seg=_TTL_CODIGO,
                      capacidades=(), version_cliente="1.0"):
        tipo = TipoDispositivo(tipo); scopes = self._scopes(tipo, scopes)
        capacidades = self._capacidades(tipo, capacidades)
        if tipo == TipoDispositivo.PC_NUCLEO or not 1 <= float(ttl_seg) <= 600:
            raise ValueError("emparejamiento no permitido o TTL inválido")
        if not isinstance(version_cliente, str) or not version_cliente or len(version_cliente) > 64:
            raise ValueError("versión cliente inválida")
        code = secrets.token_urlsafe(9); salt = _salt(); now = self._now()
        item = {"salt": _b64(salt), "hash": _hash(code, salt), "tipo": tipo.value,
                "scopes": sorted(s.value for s in scopes), "capacidades": list(capacidades),
                "version_cliente": version_cliente, "expira_en": now + float(ttl_seg)}
        with self._lock:
            def put(data):
                pending = data["emparejamientos"]
                for key, value in tuple(pending.items()):
                    if value.get("expira_en", 0) <= now: del pending[key]
                if len(pending) >= 8: raise ValueError("límite de códigos pendientes")
                pending[str(uuid4())] = item
            self.almacen.actualizar(put)
        return code

    def canjear_codigo(self, code):
        if not isinstance(code, str) or not code or len(code) > 80: return None
        now = self._now(); token = _b64(secrets.token_bytes(32)); cookie = _b64(secrets.token_bytes(32))
        did, sid = str(uuid4()), str(uuid4()); ts, cs = _salt(), _salt()
        result = {}
        with self._lock:
            def redeem(data):
                found = None
                for key, entry in tuple(data["emparejamientos"].items()):
                    salt = base64.urlsafe_b64decode(entry["salt"] + "==")
                    valid = hmac.compare_digest(_hash(code, salt), entry["hash"])
                    if valid and entry["expira_en"] > now: found = key, entry
                if not found: return
                key, entry = found
                row = {"device_id": did, "tipo_dispositivo": entry["tipo"],
                       "capacidades": entry["capacidades"], "version_cliente": entry["version_cliente"],
                       "scopes": entry["scopes"], "revocado": False, "conectado": True,
                       "creado_en": now, "latido": now, "session_id": sid,
                       "credential_version": 1,
                       "token_salt": _b64(ts), "token_hash": _hash(token, ts),
                       "sesiones": [{"session_id": sid, "salt": _b64(cs),
                           "hash": _hash(cookie, cs), "expira_en": now + _TTL_SESION,
                           "latido": now, "revocada": False}]}
                data["dispositivos"][did] = row
                del data["emparejamientos"][key]
                result.update(device_id=did, session_id=sid, token=token, cookie=cookie,
                              tipo_dispositivo=entry["tipo"], scopes=list(entry["scopes"]))
            self.almacen.actualizar(redeem)
        return result or None

    def emparejar_lan(self, tipo=TipoDispositivo.TABLET_HUD, scopes=(), capacidades=(), version_cliente="1.0"):
        tipo = TipoDispositivo(tipo); scopes = self._scopes(tipo, scopes)
        capacidades = self._capacidades(tipo, capacidades); now = self._now()
        token = _b64(secrets.token_bytes(32)); cookie = _b64(secrets.token_bytes(32))
        did, sid = f"lan_{uuid4()}", str(uuid4())
        ts, cs = _salt(), _salt(); result = {}
        with self._lock:
            def register(data):
                row = {"device_id": did, "tipo_dispositivo": tipo.value,
                       "capacidades": list(capacidades), "version_cliente": version_cliente,
                       "scopes": sorted(s.value for s in scopes), "revocado": False,
                       "conectado": True, "creado_en": now, "latido": now,
                       "session_id": sid, "credential_version": 1,
                       "token_salt": _b64(ts), "token_hash": _hash(token, ts),
                       "sesiones": [{"session_id": sid, "salt": _b64(cs),
                           "hash": _hash(cookie, cs), "expira_en": now + _TTL_SESION * 24,
                           "latido": now, "revocada": False}]}
                data["dispositivos"][did] = row
                result.update(device_id=did, session_id=sid, token=token, cookie=cookie,
                              tipo_dispositivo=tipo.value, scopes=sorted(s.value for s in scopes))
            self.almacen.actualizar(register)
        return result or None

    def set_privado(self, activo):
        if not isinstance(activo, bool): raise TypeError("activo debe ser bool")
        with self._lock:
            return self.almacen.actualizar(lambda d: d["preferencias"].__setitem__("modo_privado", activo))

    def modo_privado(self):
        return bool(self.almacen.cargar()["preferencias"].get("modo_privado", False))

    @staticmethod
    def cookie_header(cookie, secure=False, ttl=_TTL_SESION):
        flags = "; HttpOnly; SameSite=Lax; Path=/; Max-Age=" + str(int(ttl))
        return "SilvestraSession=" + cookie + flags + ("; Secure" if secure else "")

    @staticmethod
    def cookie_value(header):
        for part in str(header or "").split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name == "SilvestraSession": return value
        return ""
