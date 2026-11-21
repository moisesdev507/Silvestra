"""Contratos de interpretación temporal de situaciones multimodales."""
from __future__ import annotations
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class EstadoSituacion(str, Enum):
    iniciada = "iniciada"
    actualizada = "actualizada"
    resuelta = "resuelta"
    expirada = "expirada"


class NivelIncertidumbre(str, Enum):
    baja = "baja"
    media = "media"
    alta = "alta"
    insuficiente = "insuficiente"


_SECRET = re.compile(r"(?i)(password|passwd|token|secret|clave|api[_-]?key|authorization)\s*[:=]\s*\S+")
_PATH = re.compile(r"(?i)(?:[a-z]:\\|\\\\)[^\s]+")


def sanitizar_dato(valor, profundidad=0):
    if profundidad > 5 or valor is None or isinstance(valor, (bool, int)):
        return valor if profundidad <= 5 else None
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, str):
        return _PATH.sub("[ruta omitida]", _SECRET.sub(lambda m: m.group(1)+"=***", valor))[:500]
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return None
    if type(valor).__module__.startswith(("numpy", "PIL")):
        return None
    if isinstance(valor, dict):
        return {str(k)[:60]: ("***" if re.search(r"(?i)password|token|secret|clave|api[_-]?key|identity|identidad|nombre_persona|rostro", str(k))
            else sanitizar_dato(v, profundidad+1)) for k,v in list(valor.items())[:40]
            if not any(x in str(k).lower() for x in ("imagen", "frame", "pcm", "wav", "bytes", "ruta", "path", "buffer"))}
    if isinstance(valor, (list, tuple, set)):
        return [x for v in list(valor)[:40] if (x := sanitizar_dato(v, profundidad+1)) is not None]
    return None


def confianza_valida(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int,float)):
        return None
    valor=float(valor)
    return valor if math.isfinite(valor) and 0 <= valor <= 1 else None


@dataclass
class PoliticaInterpretacionSituaciones:
    max_situaciones_activas: int = 12
    ttl_situacion_seg: float = 180.0
    ventana_fusion_actualizacion_seg: float = 25.0
    umbral_relevancia_iniciativa: str = "alta"
    max_resumen_cerebro_chars: int = 550
    autorizacion_externa: bool = False

    def __post_init__(self):
        self.max_situaciones_activas=max(1,int(self.max_situaciones_activas))
        self.ttl_situacion_seg=max(1.0,float(self.ttl_situacion_seg))
        self.ventana_fusion_actualizacion_seg=max(0.0,float(self.ventana_fusion_actualizacion_seg))
        self.max_resumen_cerebro_chars=min(550,max(40,int(self.max_resumen_cerebro_chars)))


@dataclass
class EvidenciaSituacion:
    id_observacion: str
    modalidad: str
    timestamp: float
    descripcion_hecho: str
    confianza: float | None = None
    relevancia: str = "baja"

    def __post_init__(self):
        self.confianza=confianza_valida(self.confianza)
        self.descripcion_hecho=str(sanitizar_dato(self.descripcion_hecho) or "")[:500]


@dataclass
class InterpretacionSituacion:
    categoria_situacion: str
    inicio_ts: float
    ultima_actualizacion_ts: float
    id_situacion: str = field(default_factory=lambda: str(uuid.uuid4()))
    estado: EstadoSituacion = EstadoSituacion.iniciada
    cierre_ts: float | None = None
    relevancia: str = "baja"
    confianza_interpretacion: float | None = None
    nivel_incertidumbre: NivelIncertidumbre = NivelIncertidumbre.insuficiente
    riesgo_falso_positivo: float = 1.0
    hechos_observados: list[str] = field(default_factory=list)
    relaciones_probables: list[str] = field(default_factory=list)
    hipotesis: list[str] = field(default_factory=list)
    conclusiones_verificadas: list[str] = field(default_factory=list)
    lagunas_informacion: list[str] = field(default_factory=list)
    secuencia_temporal: list[str] = field(default_factory=list)
    evidencias: list[EvidenciaSituacion] = field(default_factory=list)
    modalidades_involucradas: list[str] = field(default_factory=list)
    modalidades_con_fallo: list[str] = field(default_factory=list)
    contexto_asociado: dict = field(default_factory=dict)
    resumen_interpretado: str = ""
    sugerencia_pasiva: dict | None = None

    def __post_init__(self):
        self.confianza_interpretacion=confianza_valida(self.confianza_interpretacion)
        self.riesgo_falso_positivo=min(1.0,max(0.0,float(self.riesgo_falso_positivo)))
        for campo in ("hechos_observados","relaciones_probables","hipotesis",
                      "conclusiones_verificadas","lagunas_informacion","secuencia_temporal",
                      "modalidades_involucradas","modalidades_con_fallo"):
            setattr(self,campo,list(dict.fromkeys(str(sanitizar_dato(x) or "")[:500] for x in getattr(self,campo))))
        self.sugerencia_pasiva=sanitizar_dato(self.sugerencia_pasiva)
        self.contexto_asociado=sanitizar_dato(self.contexto_asociado) or {}
        self.resumen_interpretado=str(sanitizar_dato(self.resumen_interpretado) or "")[:550]
