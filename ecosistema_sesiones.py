"""Autenticación hash y ciclo de vida de sesiones del ecosistema."""
from threading import RLock
import base64, hashlib, hmac, secrets, time
from ecosistema_almacen import AlmacenEcosistema
from ecosistema_contratos import Scope, TipoDispositivo
_TTL_SESION=3600
def _hash(secret,salt): return hashlib.pbkdf2_hmac("sha256",secret.encode("utf-8"),salt,80000).hex()
def _salt(): return secrets.token_bytes(16)
def _b64(raw): return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
class GestorSesiones:
    def __init__(self,almacen=None,reloj=time.time):
        self.almacen=almacen or AlmacenEcosistema(); self._lock=RLock(); self._now=reloj; self._proof_key=secrets.token_bytes(32)
    def identidad_nucleo(self):
        data = self.almacen.cargar()
        for did, row in data["dispositivos"].items():
            if row["tipo_dispositivo"] == TipoDispositivo.PC_NUCLEO.value and not row["revocado"]:
                return self._identity((did, row, None))
        return None

    def _buscar(self, secret, campo, now=None):
        if not isinstance(secret, str) or not secret or len(secret) > 200: return None
        now = self._now() if now is None else now
        with self._lock:
            data = self.almacen.cargar()
            for did, row in data["dispositivos"].items():
                if row.get("revocado"): continue
                if campo == "token_hash":
                    salt = base64.urlsafe_b64decode(row["token_salt"] + "==") if row.get("token_salt") else b""
                    if salt and hmac.compare_digest(_hash(secret, salt), row[campo]):
                        return did, row, None
                else:
                    for sess in row.get("sesiones", []):
                        salt = base64.urlsafe_b64decode(sess["salt"] + "==")
                        if (sess.get("revocada") or sess["expira_en"] <= now): continue
                        if hmac.compare_digest(_hash(secret, salt), sess["hash"]):
                            return did, row, sess
        return None

    def revocar(self, device_id):
        changed = False
        with self._lock:
            def revoke(data):
                nonlocal changed
                row = data["dispositivos"].get(str(device_id))
                if row:
                    row["revocado"] = True; row["sesiones"] = []; changed = True
            self.almacen.actualizar(revoke)
        return changed

    def autenticar_token(self, token):
        found = self._buscar(token, "token_hash")
        return self._identity(found) if found else None

    def _proof(self, identity):
        raw = "|".join((identity["device_id"], identity["session_id"],
                        identity["tipo_dispositivo"], ",".join(sorted(identity["scopes"])),
                        identity["auth_kind"], str(identity["credential_version"])))
        return hmac.new(self._proof_key, raw.encode(), hashlib.sha256).hexdigest()

    def autenticar_cookie(self, cookie):
        found = self._buscar(cookie, "cookie")
        return self._identity(found) if found else None

    def _identity(self, found):
        did, row, sess = found
        identity = {"device_id": did, "tipo_dispositivo": row["tipo_dispositivo"],
                    "scopes": frozenset(row["scopes"]),
                    "session_id": sess["session_id"] if sess else row["session_id"],
                    "auth_kind": "cookie" if sess else ("token" if row.get("token_hash") else "local"),
                    "credential_version": row.get("credential_version", 0)}
        identity["_proof"] = self._proof(identity)
        return identity

    def heartbeat(self, identity, ahora=None):
        if not identity: return False
        now = self._now() if ahora is None else float(ahora); did = identity.get("device_id")
        sid = identity.get("session_id"); ok = False
        with self._lock:
            def beat(data):
                nonlocal ok
                row = data["dispositivos"].get(did)
                if not row or row["revocado"]: return
                for sess in row["sesiones"]:
                    if sess["session_id"] == sid and not sess["revocada"] and sess["expira_en"] > now:
                        sess["latido"] = now; sess["expira_en"] = now + _TTL_SESION
                        row["latido"] = now; row["conectado"] = True; ok = True; return
            self.almacen.actualizar(beat)
        return ok

    def desconectados(self, timeout_seg=90, ahora=None):
        now = self._now() if ahora is None else float(ahora)
        data = self.almacen.cargar()
        return [did for did, row in data["dispositivos"].items()
                if not row["revocado"] and now - row["latido"] > timeout_seg]

    def marcar_desconectados(self, timeout_seg=90, ahora=None):
        now = self._now() if ahora is None else float(ahora); result = []
        def scan(data):
            for did, row in data["dispositivos"].items():
                if row["tipo_dispositivo"] == "pc_nucleo": continue
                offline = row["revocado"] or now - row["latido"] > timeout_seg
                if row.get("conectado", True) and offline: result.append(did)
                row["conectado"] = not offline
        self.almacen.actualizar(scan)
        return result

    def autorizar(self, identity, scope):
        try: needed = Scope(scope).value
        except (ValueError, TypeError): return False
        if not identity: return False
        try:
            if not hmac.compare_digest(str(identity.get("_proof", "")), self._proof(identity)):
                return False
            data = self.almacen.cargar()
            row = data["dispositivos"].get(identity["device_id"])
            if not row or row["revocado"] or needed not in row["scopes"]:
                return False
            if identity["credential_version"] != row.get("credential_version", 0):
                return False
            if identity["auth_kind"] == "cookie":
                return any(s["session_id"] == identity["session_id"] and not s["revocada"]
                           and s["expira_en"] > self._now() for s in row.get("sesiones", []))
            if identity["auth_kind"] == "token":
                return bool(row.get("token_hash"))
            return identity["auth_kind"] == "local"
        except (KeyError, TypeError, ValueError):
            return False

    def rotar_token(self, identity):
        if not self.autorizar(identity, Scope.STATE_READ): return None
        did = identity.get("device_id"); token = _b64(secrets.token_bytes(32)); salt = _salt()
        with self._lock:
            def rotate(data):
                row = data["dispositivos"].get(did)
                if not row or row["revocado"]: return False
                row["token_salt"] = _b64(salt); row["token_hash"] = _hash(token, salt)
                row["credential_version"] = row.get("credential_version", 0) + 1
                row["sesiones"] = []; return True
            if self.almacen.actualizar(rotate): return token
        return None
