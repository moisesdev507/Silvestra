from threading import RLock
from uuid import uuid4
import time
from ecosistema_contratos_base import *
from ecosistema_contratos_base import _id
from ecosistema_contratos_mensajes import CommandRequest, ApprovalRequest

class RegistroDispositivos:
    def __init__(self): self._lock=RLock(); self._d={}; self._s={}; self._core=None
    def registrar(self,d):
        if not isinstance(d,RegistroDispositivo): raise TypeError("RegistroDispositivo requerido")
        with self._lock:
            if d.device_id in self._d or (d.tipo==TipoDispositivo.PC_NUCLEO and self._core): raise ValueError("dispositivo duplicado o núcleo existente")
            self._d[d.device_id]=d
            if d.tipo==TipoDispositivo.PC_NUCLEO: self._core=d.device_id
        return d
    def crear_sesion(self,device_id,scopes=(),ttl_seg=3600,ahora=None):
        now=time.time() if ahora is None else float(ahora); did=_id(device_id,"device_id")
        with self._lock:
            d=self._d.get(did)
            if not d or d.revocado or ttl_seg<=0: raise PermissionError("dispositivo no autorizado")
            s=SesionDispositivo(str(uuid4()),did,frozenset(scopes),now,now,now+ttl_seg,float(ttl_seg)); self._s[s.session_id]=s; return s
    def autorizar(self,device_id,session_id,scope,ahora=None):
        try: did,sid,need=_id(device_id,"device_id"),_id(session_id,"session_id"),Scope(scope)
        except (ValueError,TypeError): return False
        now=time.time() if ahora is None else float(ahora)
        with self._lock:
            d,s=self._d.get(did),self._s.get(sid)
            return bool(d and not d.revocado and s and s.device_id==did and not s.revocada and s.expira_en>now and need in s.scopes)
    def latido(self,device_id,session_id,ahora=None):
        now=time.time() if ahora is None else float(ahora); sid=_id(session_id,"session_id")
        with self._lock:
            s=self._s.get(sid)
            if not s or s.device_id!=_id(device_id,"device_id") or s.revocada or s.expira_en<=now: return False
            self._s[sid]=SesionDispositivo(sid,s.device_id,s.scopes,s.creada_en,now,now+s.ttl_seg,s.ttl_seg); return True
    def revocar_sesion(self,session_id):
        sid=_id(session_id,"session_id")
        with self._lock:
            s=self._s.get(sid)
            if not s: return False
            self._s[sid]=SesionDispositivo(sid,s.device_id,s.scopes,s.creada_en,s.ultimo_latido,s.expira_en,s.ttl_seg,True); return True
    def revocar_dispositivo(self,device_id):
        did=_id(device_id,"device_id")
        with self._lock:
            d=self._d.get(did)
            if not d: return False
            self._d[did]=RegistroDispositivo(did,d.tipo,d.capacidades,d.version_cliente,True)
            for sid,s in tuple(self._s.items()):
                if s.device_id==did: self.revocar_sesion(sid)
            return True
    def autorizar_operacion(self,cmd,approval=None,ahora=None):
        if not isinstance(cmd,CommandRequest) or not self.autorizar(cmd.device_id,cmd.session_id,Scope.OPERATION_REQUEST,ahora): return False
        if not (cmd.payload.get("sensible") or cmd.payload.get("sensibilidad") in ("sensible","destructiva")): return True
        return bool(isinstance(approval,ApprovalRequest) and approval.payload.get("decision")=="approved" and
                    approval.payload.get("command_message_id")==cmd.message_id and
                    self.autorizar(approval.device_id,approval.session_id,Scope.OPERATION_APPROVE,ahora))


