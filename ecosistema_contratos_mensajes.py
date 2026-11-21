from dataclasses import dataclass, field
from datetime import datetime
from ecosistema_contratos_base import *
from ecosistema_contratos_base import _id, _safe

@dataclass(frozen=True)
class SobreMensaje:
    version:str; message_id:str; correlation_id:str; device_id:str; session_id:str; sent_at:str; kind:TipoMensaje; payload:dict
    def __post_init__(self):
        if self.version!=VERSION: raise ValueError("versión no soportada")
        for n in ("message_id","correlation_id","device_id","session_id"): object.__setattr__(self,n,_id(getattr(self,n),n))
        try:
            dt=datetime.fromisoformat(self.sent_at.replace("Z","+00:00"))
            if dt.tzinfo is None: raise ValueError("zona horaria requerida")
            object.__setattr__(self,"kind",TipoMensaje(self.kind))
        except (AttributeError,TypeError,ValueError) as e: raise ValueError("kind o fecha inválidos") from e
        if not isinstance(self.payload,dict): raise TypeError("payload debe ser objeto")
        object.__setattr__(self,"sent_at",dt.isoformat()); object.__setattr__(self,"payload",_safe(self.payload))
    def a_dict(self): return {"version":self.version,"message_id":self.message_id,"correlation_id":self.correlation_id,"device_id":self.device_id,"session_id":self.session_id,"sent_at":self.sent_at,"kind":self.kind.value,"payload":self.payload}
    def a_json_seguro(self): return serializar_seguro(self.a_dict())

@dataclass(frozen=True)
class Observation(SobreMensaje):
    kind:TipoMensaje=field(default=TipoMensaje.OBSERVATION,init=False)
    def __post_init__(self):
        super().__post_init__()
        if {"command","accion","requiere_ejecucion"}.intersection(self.payload): raise ValueError("observación no ejecutable")
    @property
    def ejecutable(self): return False
@dataclass(frozen=True)
class CommandRequest(SobreMensaje):
    kind:TipoMensaje=field(default=TipoMensaje.COMMAND_REQUEST,init=False)
    def __post_init__(self):
        super().__post_init__()
        if not str(self.payload.get("operacion","")).strip(): raise ValueError("operación requerida")
@dataclass(frozen=True)
class ApprovalRequest(SobreMensaje):
    kind:TipoMensaje=field(default=TipoMensaje.APPROVAL_REQUEST,init=False)
    def __post_init__(self):
        super().__post_init__()
        if self.payload.get("decision") not in ("pending","approved","rejected"): raise ValueError("decisión inválida")
        _id(self.payload.get("command_message_id"),"command_message_id")
@dataclass(frozen=True)
class Result(SobreMensaje):
    kind:TipoMensaje=field(default=TipoMensaje.RESULT,init=False)
    def __post_init__(self):
        super().__post_init__()
        if self.payload.get("estado") not in ("accepted","completed","rejected","failed","cancelled"): raise ValueError("estado inválido")
@dataclass(frozen=True)
class Event(SobreMensaje):
    kind:TipoMensaje=field(default=TipoMensaje.EVENT,init=False)
    def __post_init__(self):
        super().__post_init__()
        if not str(self.payload.get("event_type","")).strip(): raise ValueError("event_type requerido")

