"""Contratos compactos y sanitizados para integrar observaciones multimodales."""
from __future__ import annotations
import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass, field


_SENSIBLE = re.compile(r"(?i)(password|passwd|token|secret|clave|api[_-]?key|authorization)\s*[:=]\s*\S+")
_SECRETO_CLAVE = re.compile(r"(?i)(password|passwd|token|secret|clave|api[_-]?key|authorization)")
_IDENTIDAD_CLAVE = re.compile(r"(?i)(identidad|identity|nombre_persona|rostro_id|face_id)")
_RUTA = re.compile(r"(?i)(?:[a-z]:\\|\\\\)[^\s]+")
_DESCARTAR = ("imagen", "image", "frame", "array", "pcm", "wav", "bytes",
              "ruta", "path", "archivo", "referencia", "buffer", "captura")


def sanitizar_valor(valor, clave="", profundidad=0):
    """Copia datos inocuos; descarta medios, rutas, arrays y objetos opacos."""
    nombre = str(clave).lower()
    if any(x in nombre for x in _DESCARTAR):
        return None
    if _SECRETO_CLAVE.search(nombre):
        return "***"
    if _IDENTIDAD_CLAVE.search(nombre):
        return "***"
    if profundidad > 5 or valor is None or isinstance(valor, (bool, int)):
        return valor if profundidad <= 5 else None
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, str):
        texto = _SENSIBLE.sub(lambda m: m.group(1) + "=***", valor)
        texto = _RUTA.sub("[ruta omitida]", texto)
        return texto[:500]
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return None
    tipo = type(valor)
    if tipo.__module__.startswith("numpy") or tipo.__module__.startswith("PIL"):
        return None
    if isinstance(valor, dict):
        limpio = {}
        for k, v in list(valor.items())[:40]:
            dato = sanitizar_valor(v, str(k), profundidad + 1)
            if dato is not None:
                limpio[str(k)[:60]] = dato
        return limpio
    if isinstance(valor, (list, tuple, set)):
        return [limpio for x in list(valor)[:40]
                if (limpio := sanitizar_valor(x, clave, profundidad + 1)) is not None]
    if hasattr(valor, "value") and isinstance(valor.value, (str, int)):
        return sanitizar_valor(valor.value, clave, profundidad + 1)
    return None


def confianza_valida(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    valor = float(valor)
    return valor if math.isfinite(valor) and 0 <= valor <= 1 else None


@dataclass
class PoliticaIntegracionMultimodal:
    ventana_correlacion_seg: float = 8.0
    ttl_observacion_seg: float = 120.0
    ventana_dedup_seg: float = 3.0
    max_observaciones_historial: int = 48
    max_situaciones_historial: int = 16
    umbral_correlacion: float = 0.52
    max_resumen_cerebro_chars: int = 550
    autorizacion_externa: bool = False

    def __post_init__(self):
        self.ventana_correlacion_seg = max(0.0, float(self.ventana_correlacion_seg))
        self.ttl_observacion_seg = max(1.0, float(self.ttl_observacion_seg))
        self.ventana_dedup_seg = max(0.0, float(self.ventana_dedup_seg))
        self.max_observaciones_historial = max(1, int(self.max_observaciones_historial))
        self.max_situaciones_historial = max(1, int(self.max_situaciones_historial))
        self.umbral_correlacion = min(1.0, max(0.0, float(self.umbral_correlacion)))
        self.max_resumen_cerebro_chars = min(550, max(40, int(self.max_resumen_cerebro_chars)))


@dataclass
class ObservacionIntegrada:
    modalidad: str
    tipo_evento: str
    resumen: str
    id_observacion: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    etiquetas_semanticas: tuple[str, ...] = ()
    datos_estructurados: dict = field(default_factory=dict)
    nivel_confianza: float | None = None
    relevancia: str = "baja"
    id_origen: str = ""
    contexto_asociado: dict = field(default_factory=dict)
    ttl_seg: float = 120.0
    huella_dedup: str = ""

    def __post_init__(self):
        if self.modalidad not in ("vision", "camara", "interfaz", "audio", "contexto"):
            raise ValueError("Modalidad integrada desconocida")
        self.timestamp = float(self.timestamp)
        self.nivel_confianza = confianza_valida(self.nivel_confianza)
        self.resumen = str(sanitizar_valor(self.resumen) or "")[:500]
        self.etiquetas_semanticas = tuple(dict.fromkeys(
            str(sanitizar_valor(x) or "").lower()[:60]
            for x in self.etiquetas_semanticas if x))[:32]
        self.datos_estructurados = sanitizar_valor(self.datos_estructurados) or {}
        self.contexto_asociado = sanitizar_valor(self.contexto_asociado) or {}
        self.ttl_seg = max(1.0, float(self.ttl_seg))
        if not self.huella_dedup:
            base = repr((self.modalidad, self.tipo_evento, self.resumen,
                         self.etiquetas_semanticas, self.datos_estructurados))
            self.huella_dedup = hashlib.sha256(base.encode("utf-8")).hexdigest()


@dataclass
class CorrelacionMultimodal:
    modalidades: tuple[str, ...]
    ids_observaciones: tuple[str, ...]
    tipo_relacion: str
    puntuacion_afinidad: float
    confianza_relacion: float | None = None
    id_correlacion: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    hechos_confirmados: list[str] = field(default_factory=list)
    hipotesis_correlacion: str = ""
    es_probable: bool = True


@dataclass
class SituacionIntegrada:
    resumen_consolidado: str
    id_situacion: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    hechos_confirmados: list[str] = field(default_factory=list)
    correlaciones_probables: list[CorrelacionMultimodal] = field(default_factory=list)
    modalidades_activas: list[str] = field(default_factory=list)
    modalidades_con_fallo: list[str] = field(default_factory=list)
    contexto_windows: dict = field(default_factory=dict)
    requiere_atencion: bool = False
    sugerencia_accion: dict | None = None
