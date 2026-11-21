"""Contratos locales, versionados y fail-closed para el ecosistema Silvestra."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import RLock
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4
import json, math, re, time

VERSION="1.0"
class TipoDispositivo(str,Enum):
    PC_NUCLEO="pc_nucleo"; TABLET_HUD="tablet_hud"; TELEFONO_MOVIL="telefono_movil"
    WEARABLE_SENSOR="wearable_sensor"; INTERFAZ_3D_NEXUS="interfaz_3d_nexus"; NODO_ROBOTICO="nodo_robotico"
class TipoMensaje(str,Enum):
    OBSERVATION="Observation"; COMMAND_REQUEST="CommandRequest"; APPROVAL_REQUEST="ApprovalRequest"; RESULT="Result"; EVENT="Event"
class Scope(str,Enum):
    STATE_READ="state:read"; UI_CONTROL="ui:control"; OPERATION_REQUEST="operation:request"
    SENSOR_SUBMIT="sensor:submit"; OPERATION_APPROVE="operation:approve"

_SEC=re.compile(r"(?i)token|secret|password|passwd|api[_-]?key|credential|authorization")
_INLINE=re.compile(r"(?i)\b(bearer\s+|(?:token|secret|password|api[_-]?key)\s*[:=]\s*)[^\s,;]+")
_CRED=re.compile(r"(?i)\b(?:sk-|ghp_|gsk_|nvapi-)[a-z0-9_-]{12,}\b|\b\d{6,12}:[a-z0-9_-]{20,}\b")
_URL=re.compile(r"https?://[^\s\"'<>]+",re.I)
def _id(x,n):
    try: return str(UUID(str(x)))
    except (ValueError,TypeError,AttributeError) as e: raise ValueError(n+" debe ser UUID") from e
def _text(x):
    x=_CRED.sub("[CREDENCIAL REDACTADA]",_INLINE.sub(lambda m:m[1]+"[REDACTADO]",str(x)))
    def url(m):
        try:
            p=urlsplit(m[0]); host=p.hostname or "[HOST]"
            return urlunsplit((p.scheme,host+(":"+str(p.port) if p.port else ""),"/","",""))
        except Exception: return "[URL REDACTADA]"
    return _URL.sub(url,x)[:4096]
def _safe(x,k="",d=0):
    if d>10: raise ValueError("payload profundo")
    if _SEC.search(str(k)): return "[REDACTADO]"
    if x is None or isinstance(x,(bool,int)): return x
    if isinstance(x,float):
        if not math.isfinite(x): raise ValueError("número inválido")
        return x
    if isinstance(x,str): return _text(x)
    if isinstance(x,dict):
        if len(x)>128 or any(not isinstance(a,str) or len(a)>100 for a in x): raise ValueError("mapa inválido")
        return {a:_safe(b,a,d+1) for a,b in x.items()}
    if isinstance(x,(list,tuple)):
        if len(x)>128: raise ValueError("lista inválida")
        return [_safe(a,d=d+1) for a in x]
    raise TypeError("payload debe ser JSON")
def serializar_seguro(x): return json.dumps(_safe(x),ensure_ascii=False,separators=(",",":"))

@dataclass(frozen=True)
class RegistroDispositivo:
    device_id:str; tipo:TipoDispositivo; capacidades:tuple=(); version_cliente:str="1.0"; revocado:bool=False
    def __post_init__(self):
        object.__setattr__(self,"device_id",_id(self.device_id,"device_id")); object.__setattr__(self,"tipo",TipoDispositivo(self.tipo))
        c=tuple(dict.fromkeys(str(x).strip() for x in self.capacidades)); central={"memoria_central","inteligencia_central","ejecucion_central"}
        if len(c)>64 or any(not x or len(x)>80 for x in c) or (self.tipo!=TipoDispositivo.PC_NUCLEO and central.intersection(c)): raise ValueError("capacidades inválidas")
        if not self.version_cliente or len(self.version_cliente)>64: raise ValueError("versión inválida")
        object.__setattr__(self,"capacidades",c)

@dataclass(frozen=True)
class SesionDispositivo:
    session_id:str; device_id:str; scopes:frozenset=frozenset(); creada_en:float=field(default_factory=time.time)
    ultimo_latido:float=field(default_factory=time.time); expira_en:float=0.; ttl_seg:float=3600.; revocada:bool=False
    def __post_init__(self):
        object.__setattr__(self,"session_id",_id(self.session_id,"session_id")); object.__setattr__(self,"device_id",_id(self.device_id,"device_id"))
        object.__setattr__(self,"scopes",frozenset(Scope(x) for x in self.scopes))
        if self.ttl_seg<=0 or self.expira_en<0 or not all(math.isfinite(float(x)) for x in (self.creada_en,self.ultimo_latido,self.ttl_seg)): raise ValueError("sesión inválida")

