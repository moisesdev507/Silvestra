"""Modelos serializables y estados de verificacion independiente."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


PENDIENTE = "pendiente"
VERIFICANDO = "verificando"
VERIFICADO = "verificado"
FALLIDO = "fallido"
RESULTADO_PARCIAL = "resultado_parcial"
RECUPERACION_PENDIENTE = "recuperacion_pendiente"
RECUPERANDO = "recuperando"
RECUPERADO = "recuperado"
REQUIERE_INTERVENCION = "requiere_intervencion_humana"

TRANSICIONES_VERIFICACION = {
    PENDIENTE: {VERIFICANDO, REQUIERE_INTERVENCION},
    VERIFICANDO: {VERIFICADO, FALLIDO, RESULTADO_PARCIAL, REQUIERE_INTERVENCION},
    RESULTADO_PARCIAL: {RECUPERACION_PENDIENTE, REQUIERE_INTERVENCION},
    RECUPERACION_PENDIENTE: {RECUPERANDO, REQUIERE_INTERVENCION},
    RECUPERANDO: {RECUPERADO, REQUIERE_INTERVENCION, FALLIDO},
    VERIFICADO: set(),
    FALLIDO: set(),
    RECUPERADO: set(),
    REQUIERE_INTERVENCION: set(),
}


class CategoriaError:
    TEMPORAL = "temporal"
    PERMANENTE = "permanente"
    PERMISOS = "permisos"
    TIMEOUT = "timeout"
    CANCELADA = "cancelada"
    INCONSISTENTE = "inconsistente"
    RECURSO_DESAPARECIDO = "recurso_desaparecido"
    COMUNICACION = "comunicacion"

    TODOS = (
        TEMPORAL, PERMANENTE, PERMISOS, TIMEOUT, CANCELADA,
        INCONSISTENTE, RECURSO_DESAPARECIDO, COMUNICACION,
    )


CLAVES_SENSIBLES = (
    "password", "passwd", "token", "secret", "clave", "api_key",
    "apikey", "texto", "contenido", "authorization",
)


def sanitizar_datos(datos: Any) -> Any:
    if isinstance(datos, dict):
        limpio = {}
        for clave, valor in datos.items():
            nombre = str(clave).lower()
            if any(s in nombre for s in CLAVES_SENSIBLES):
                limpio[str(clave)] = "***"
            else:
                limpio[str(clave)] = sanitizar_datos(valor)
        return limpio
    if isinstance(datos, list):
        return [sanitizar_datos(v) for v in datos]
    if isinstance(datos, tuple):
        return [sanitizar_datos(v) for v in datos]
    return datos


@dataclass
class CriterioVerificacion:
    herramienta: str
    idempotente: bool = False
    evidencias_requeridas: tuple[str, ...] = ()
    estrategia_recuperacion: str = "ninguna"
    max_reintentos: int = 0
    backoff_seg: float = 0.0

    def __post_init__(self) -> None:
        self.herramienta = str(self.herramienta or "").strip().lower()
        if not isinstance(self.idempotente, bool):
            raise TypeError("idempotente debe ser bool")
        if isinstance(self.evidencias_requeridas, str):
            self.evidencias_requeridas = tuple(
                e.strip() for e in self.evidencias_requeridas.split(",") if e.strip()
            )
        else:
            self.evidencias_requeridas = tuple(str(e) for e in self.evidencias_requeridas)
        if self.estrategia_recuperacion not in (
            "ninguna", "reintento_idempotente", "reanudar_punto_seguro", "escalar_humano"
        ):
            raise ValueError("estrategia_recuperacion invalida")
        self.max_reintentos = max(0, min(3, int(self.max_reintentos)))
        self.backoff_seg = max(0.0, float(self.backoff_seg))

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenciaVerificacion:
    fuente: str
    verificada: bool
    coincide_esperado: bool
    es_parcial: bool = False
    insuficiente: bool = False
    datos: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.datos = sanitizar_datos(self.datos if isinstance(self.datos, dict) else {})

    def positiva(self) -> bool:
        return bool(
            self.verificada and self.coincide_esperado
            and not self.es_parcial and not self.insuficiente
        )

    def a_dict(self) -> dict:
        return {
            "fuente": str(self.fuente),
            "verificada": bool(self.verificada),
            "coincide_esperado": bool(self.coincide_esperado),
            "es_parcial": bool(self.es_parcial),
            "insuficiente": bool(self.insuficiente),
            "datos": sanitizar_datos(self.datos),
        }


@dataclass
class InformeVerificacion:
    id_solicitud: str
    herramienta: str
    solicitud_original: dict[str, Any] = field(default_factory=dict)
    resultado_esperado: Any = None
    evidencia: Optional[EvidenciaVerificacion] = None
    errores_detectados: list[str] = field(default_factory=list)
    intentos_realizados: int = 0
    acciones_recuperacion: list[str] = field(default_factory=list)
    estado_final: str = PENDIENTE
    id_informe: str = field(default_factory=lambda: str(uuid.uuid4()))
    creado_en: float = field(default_factory=time.time)
    actualizado_en: float = field(default_factory=time.time)

    def transicionar(self, nuevo: str) -> bool:
        permitidos = TRANSICIONES_VERIFICACION.get(self.estado_final, set())
        if nuevo not in permitidos:
            return False
        self.estado_final = nuevo
        self.actualizado_en = time.time()
        return True

    def a_dict(self) -> dict:
        evidencia = self.evidencia.a_dict() if self.evidencia else None
        return {
            "id_informe": self.id_informe,
            "id_solicitud": self.id_solicitud,
            "solicitud_original": sanitizar_datos(self.solicitud_original),
            "herramienta": self.herramienta,
            "resultado_esperado": sanitizar_datos(self.resultado_esperado),
            "evidencia": evidencia,
            "errores_detectados": list(self.errores_detectados),
            "intentos_realizados": int(self.intentos_realizados),
            "acciones_recuperacion": list(self.acciones_recuperacion),
            "estado_final": self.estado_final,
            "creado_en": self.creado_en,
            "actualizado_en": self.actualizado_en,
        }
