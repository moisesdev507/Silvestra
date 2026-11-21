"""Modelos ligeros para percepcion continua de camara."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PoliticaCapturaCamara:
    intervalo_activo_seg: float = 1.0
    intervalo_reposo_seg: float = 3.0
    umbral_cambio_significativo: float = 0.12
    intervalo_resumen_vlm_seg: float = 15.0
    ttl_observacion_seg: float = 60.0
    max_observaciones_temporales: int = 40
    autorizacion_externa: bool = False
    habilitada: bool = True

    def __post_init__(self) -> None:
        self.intervalo_activo_seg = max(0.05, float(self.intervalo_activo_seg))
        self.intervalo_reposo_seg = max(0.1, float(self.intervalo_reposo_seg))
        self.umbral_cambio_significativo = min(
            1.0, max(0.0, float(self.umbral_cambio_significativo))
        )
        self.intervalo_resumen_vlm_seg = max(
            1.0, float(self.intervalo_resumen_vlm_seg)
        )
        self.ttl_observacion_seg = max(1.0, float(self.ttl_observacion_seg))
        self.max_observaciones_temporales = max(
            1, int(self.max_observaciones_temporales)
        )


@dataclass
class ResultadoComparacionFrame:
    puntuacion_cambio: float
    hay_cambio_significativo: bool
    hay_movimiento: bool
    regiones_movimiento: list[tuple[int, int, int, int]] = field(
        default_factory=list
    )
    anomalia_sensor: Optional[str] = None
    huella_frame: str = ""

    def __post_init__(self) -> None:
        self.puntuacion_cambio = min(
            1.0, max(0.0, float(self.puntuacion_cambio))
        )


@dataclass
class ObservacionCamara:
    timestamp: float
    fuente: str
    puntuacion_cambio: float
    detecciones_locales: list[dict[str, Any]] = field(default_factory=list)
    observaciones_verificables: list[str] = field(default_factory=list)
    interpretaciones_inciertas: list[str] = field(default_factory=list)
    resumen_breve: str = ""
    significativa: bool = False
    id_observacion: str = field(default_factory=lambda: str(uuid.uuid4()))

    def a_dict(self) -> dict:
        return {
            "id_observacion": self.id_observacion,
            "timestamp": self.timestamp,
            "fuente": self.fuente,
            "puntuacion_cambio": round(self.puntuacion_cambio, 4),
            "detecciones_locales": list(self.detecciones_locales),
            "observaciones_verificables": list(self.observaciones_verificables),
            "interpretaciones_inciertas": list(self.interpretaciones_inciertas),
            "resumen_breve": self.resumen_breve,
            "significativa": bool(self.significativa),
        }


@dataclass
class EventoVisualCamara:
    tipo_evento: str
    nivel_epistemico: str
    prioridad: int
    timestamp: float = field(default_factory=time.time)
    datos_sanitizados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tipo_evento not in (
            "movimiento", "cambio_escena", "elemento_detectado",
            "camara_desconectada", "camara_recuperada", "anomalia_sensor",
        ):
            raise ValueError("tipo_evento invalido")
        if self.nivel_epistemico not in (
            "deteccion", "observacion", "interpretacion"
        ):
            raise ValueError("nivel_epistemico invalido")

    def a_dict(self) -> dict:
        return {
            "tipo_evento": self.tipo_evento,
            "nivel_epistemico": self.nivel_epistemico,
            "prioridad": self.prioridad,
            "timestamp": self.timestamp,
            "datos_sanitizados": dict(self.datos_sanitizados),
        }
