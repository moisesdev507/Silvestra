"""Contratos sanitizados para inteligencia auditiva."""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class CategoriaSonido(str, Enum):
    alarma = "alarma"
    timbre = "timbre"
    golpes = "golpes"
    aplausos = "aplausos"
    ladridos = "ladridos"
    sirena = "sirena"
    voz_humana = "voz_humana"
    ruido_ambiental = "ruido_ambiental"
    sonido_no_verbal = "sonido_no_verbal"
    eco_silvestra = "eco_silvestra"
    desconocido = "desconocido"


class NivelRelevanciaSonido(str, Enum):
    critica = "critica"
    alta = "alta"
    media = "media"
    irrelevante = "irrelevante"


@dataclass
class PoliticaPercepcionAuditiva:
    habilitada: bool = True
    permiso_microfono: bool = False
    permitir_grabacion_continua: bool = False
    permitir_envio_externo: bool = False
    duracion_max_seg: float = 30.0
    max_bytes_audio: int = 10 * 1024 * 1024
    umbral_confianza_relevante: float = 0.55
    ignorar_eco_propio: bool = True
    ttl_historial_seg: float = 180.0
    max_eventos_historial: int = 32

    def __post_init__(self):
        self.duracion_max_seg = max(0.1, float(self.duracion_max_seg))
        self.max_bytes_audio = max(1, int(self.max_bytes_audio))
        self.umbral_confianza_relevante = min(1.0, max(0.0, float(self.umbral_confianza_relevante)))
        self.ttl_historial_seg = max(1.0, float(self.ttl_historial_seg))
        self.max_eventos_historial = max(1, int(self.max_eventos_historial))


@dataclass
class ClasificacionAcustica:
    categoria: CategoriaSonido = CategoriaSonido.desconocido
    subetiqueta: str = ""
    confianza: float | None = None
    es_voz: bool = False
    es_relevante: bool = False
    origen_clasificador: str = ""


@dataclass
class EventoAcustico:
    id_evento: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    fuente: str = "archivo"
    duracion_seg: float = 0.0
    energia_rms: float = 0.0
    ratio_voz_vad: float = 0.0
    clasificacion: ClasificacionAcustica = field(default_factory=ClasificacionAcustica)
    relevancia: NivelRelevanciaSonido = NivelRelevanciaSonido.irrelevante
    repeticiones_recientes: int = 0
    observaciones_verificables: list[str] = field(default_factory=list)
    interpretaciones_inciertas: list[str] = field(default_factory=list)
    contexto_windows_asociado: dict = field(default_factory=dict)
    transcripcion_breve: str = ""
    sugerencia_accion: dict | None = None

    def a_dict(self):
        return {"id_evento": self.id_evento, "timestamp": self.timestamp,
                "fuente": self.fuente, "duracion_seg": self.duracion_seg,
                "energia_rms": self.energia_rms, "ratio_voz_vad": self.ratio_voz_vad,
                "clasificacion": {"categoria": self.clasificacion.categoria.value,
                    "subetiqueta": self.clasificacion.subetiqueta,
                    "confianza": self.clasificacion.confianza,
                    "es_voz": self.clasificacion.es_voz,
                    "es_relevante": self.clasificacion.es_relevante,
                    "origen_clasificador": self.clasificacion.origen_clasificador},
                "relevancia": self.relevancia.value,
                "repeticiones_recientes": self.repeticiones_recientes,
                "observaciones_verificables": list(self.observaciones_verificables),
                "interpretaciones_inciertas": list(self.interpretaciones_inciertas),
                "contexto_windows_asociado": dict(self.contexto_windows_asociado),
                "transcripcion_breve": self.transcripcion_breve,
                "sugerencia_accion": self.sugerencia_accion}
