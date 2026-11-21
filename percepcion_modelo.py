"""Modelos canonicos para eventos perceptivos multimodales."""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


MODALIDADES = (
    "camara", "imagen", "captura_screenshot",
    "captura_pantalla", "audio", "contexto_sistema", "evento_interno",
)

RECIBIDO = "recibido"
NORMALIZADO = "normalizado"
EN_COLA = "en_cola"
PROCESANDO = "procesando"
PROCESADO = "procesado"
DESCARTADO = "descartado"
CANCELADO = "cancelado"
EXPIRADO = "expirado"
FALLIDO = "fallido"

TRANSICIONES_PERCEPCION = {
    RECIBIDO: {NORMALIZADO, DESCARTADO, FALLIDO, CANCELADO},
    NORMALIZADO: {EN_COLA, DESCARTADO, EXPIRADO, CANCELADO, FALLIDO},
    EN_COLA: {PROCESANDO, DESCARTADO, EXPIRADO, CANCELADO, FALLIDO},
    PROCESANDO: {PROCESADO, DESCARTADO, EXPIRADO, CANCELADO, FALLIDO},
    PROCESADO: set(),
    DESCARTADO: set(),
    CANCELADO: set(),
    EXPIRADO: set(),
    FALLIDO: set(),
}


@dataclass
class PoliticaRecursosModalidad:
    max_bytes: int = 5 * 1024 * 1024
    max_duracion_seg: float = 30.0
    ttl_seg: float = 5.0
    max_pendientes: int = 20

    def __post_init__(self) -> None:
        self.max_bytes = max(1, int(self.max_bytes))
        self.max_duracion_seg = max(0.0, float(self.max_duracion_seg))
        self.ttl_seg = max(0.0, float(self.ttl_seg))
        self.max_pendientes = max(1, int(self.max_pendientes))


@dataclass
class ReferenciaContenido:
    ruta: Optional[str] = None
    tipo: str = "metadatos"
    tamano: int = 0
    duracion_seg: float = 0.0
    huella: str = ""
    liberada: bool = False

    def liberar(self) -> None:
        self.liberada = True

    def a_dict(self) -> dict:
        return {
            "ruta": os.path.basename(self.ruta) if self.ruta else None,
            "tipo": self.tipo,
            "tamano": self.tamano,
            "duracion_seg": self.duracion_seg,
            "huella": self.huella,
            "liberada": self.liberada,
        }


@dataclass
class EventoPerceptivo:
    modalidad: str
    fuente: str
    prioridad: int = 0
    id_evento: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadatos: dict[str, Any] = field(default_factory=dict)
    estado: str = RECIBIDO
    referencia_contenido: Optional[ReferenciaContenido] = None
    resultado_estructurado: Optional[dict[str, Any]] = None
    huella_sha256: str = ""

    def __post_init__(self) -> None:
        if self.modalidad not in MODALIDADES:
            raise ValueError("Modalidad desconocida")
        self.metadatos = sanitizar_metadatos(self.metadatos)

    def transicionar(self, nuevo: str) -> bool:
        permitidos = TRANSICIONES_PERCEPCION.get(self.estado, set())
        if nuevo not in permitidos:
            return False
        self.estado = nuevo
        return True

    def liberar_recurso(self) -> None:
        if self.referencia_contenido is not None:
            self.referencia_contenido.liberar()

    def huella(self) -> str:
        if self.huella_sha256:
            return self.huella_sha256
        canon = repr((self.modalidad, self.fuente, self.metadatos))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def a_dict(self) -> dict:
        return {
            "id_evento": self.id_evento,
            "modalidad": self.modalidad,
            "fuente": self.fuente,
            "timestamp": self.timestamp,
            "prioridad": self.prioridad,
            "metadatos": dict(self.metadatos),
            "estado": self.estado,
            "referencia_contenido": (
                self.referencia_contenido.a_dict()
                if self.referencia_contenido else None
            ),
            "resultado_estructurado": self.resultado_estructurado,
            "huella_sha256": self.huella(),
        }


def sanitizar_metadatos(datos: dict[str, Any]) -> dict[str, Any]:
    sensibles = ("password", "passwd", "token", "secret", "clave", "api_key",
                 "texto", "contenido", "authorization")
    limpio = {}
    for clave, valor in (datos or {}).items():
        nombre = str(clave).lower()
        if any(s in nombre for s in sensibles):
            limpio[str(clave)] = "***"
        elif isinstance(valor, dict):
            limpio[str(clave)] = sanitizar_metadatos(valor)
        else:
            limpio[str(clave)] = valor
    return limpio
