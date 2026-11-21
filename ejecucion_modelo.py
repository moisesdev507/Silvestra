"""Contratos y resultados normalizados para el futuro sistema de ejecucion."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional


ESTADOS_SOLICITUD = (
    "creada", "validada", "pendiente_autorizacion", "en_ejecucion",
    "completada", "fallida", "cancelada", "rechazada",
)
ESTADO_CREADA = "creada"
ESTADO_VALIDADA = "validada"
ESTADO_PENDIENTE_AUTORIZACION = "pendiente_autorizacion"
ESTADO_EN_EJECUCION = "en_ejecucion"
ESTADO_COMPLETADA = "completada"
ESTADO_FALLIDA = "fallida"
ESTADO_CANCELADA = "cancelada"
ESTADO_RECHAZADA = "rechazada"

ORIGENES_VALIDOS = {"cerebro", "planificador", "usuario", "sistema"}
NIVELES_RIESGO_VALIDOS = {"bajo", "medio", "alto", "critico"}


@dataclass
class SolicitudEjecucion:
    origen: str
    herramienta: str
    parametros: dict[str, Any] = field(default_factory=dict)
    id_solicitud: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_creacion: float = field(default_factory=time.time)
    estado: str = ESTADO_CREADA
    id_plan: Optional[str] = None
    id_tarea: Optional[str] = None

    def __post_init__(self) -> None:
        self.origen = str(self.origen or "sistema").strip().lower()
        self.herramienta = str(self.herramienta or "").strip().lower()
        if not isinstance(self.parametros, dict):
            raise TypeError("parametros debe ser un diccionario")
        if self.estado not in ESTADOS_SOLICITUD:
            raise ValueError("estado de solicitud invalido")

    def a_dict(self) -> dict[str, Any]:
        return {
            "id_solicitud": self.id_solicitud,
            "timestamp_creacion": self.timestamp_creacion,
            "origen": self.origen,
            "herramienta": self.herramienta,
            "parametros": dict(self.parametros),
            "id_plan": self.id_plan,
            "id_tarea": self.id_tarea,
            "estado": self.estado,
        }

    @classmethod
    def de_dict(cls, datos: dict[str, Any]) -> "SolicitudEjecucion":
        if not isinstance(datos, dict):
            raise TypeError("SolicitudEjecucion debe crearse desde un diccionario")
        solicitud = cls(
            origen=datos.get("origen", "sistema"),
            herramienta=datos.get("herramienta", ""),
            parametros=datos.get("parametros", {}),
            id_solicitud=str(datos.get("id_solicitud") or uuid.uuid4()),
            timestamp_creacion=float(datos.get("timestamp_creacion") or time.time()),
            estado=datos.get("estado", ESTADO_CREADA),
            id_plan=datos.get("id_plan"),
            id_tarea=datos.get("id_tarea"),
        )
        return solicitud


@dataclass
class ContratoHerramienta:
    nombre: str
    categoria: str
    descripcion: str
    parametros_esquema: dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None
    nivel_riesgo: str = "bajo"
    requiere_confirmacion: bool = False
    permisos_requeridos: tuple[str, ...] = ()
    cancelable: bool = False
    asincrona: bool = False
    timeout_seg: float = 30.0
    habilitada: bool = True

    def __post_init__(self) -> None:
        self.nombre = str(self.nombre or "").strip().lower()
        self.categoria = str(self.categoria or "").strip().lower()
        self.descripcion = str(self.descripcion or "").strip()
        if not isinstance(self.parametros_esquema, dict):
            raise TypeError("parametros_esquema debe ser un diccionario")
        self.nivel_riesgo = str(self.nivel_riesgo or "bajo").strip().lower()
        if self.nivel_riesgo not in NIVELES_RIESGO_VALIDOS:
            raise ValueError("nivel_riesgo invalido")
        if not isinstance(self.requiere_confirmacion, bool):
            raise TypeError("requiere_confirmacion debe ser bool")
        if not isinstance(self.cancelable, bool):
            raise TypeError("cancelable debe ser bool")
        if not isinstance(self.asincrona, bool):
            raise TypeError("asincrona debe ser bool")
        if not isinstance(self.habilitada, bool):
            raise TypeError("habilitada debe ser bool")
        if isinstance(self.permisos_requeridos, str):
            self.permisos_requeridos = tuple(
                p.strip() for p in self.permisos_requeridos.split(",") if p.strip()
            )
        else:
            self.permisos_requeridos = tuple(str(p) for p in self.permisos_requeridos)
        self.timeout_seg = float(self.timeout_seg)
        if self.timeout_seg <= 0:
            raise ValueError("timeout_seg debe ser positivo")

    def metadatos(self) -> dict[str, Any]:
        return {
            "nivel_riesgo": self.nivel_riesgo,
            "requiere_confirmacion": self.requiere_confirmacion,
            "permisos_requeridos": list(self.permisos_requeridos),
            "cancelable": self.cancelable,
            "asincrona": self.asincrona,
            "timeout_seg": self.timeout_seg,
            "categoria": self.categoria,
            "habilitada": self.habilitada,
        }

    def valida_integridad(self) -> tuple[bool, str]:
        if not self.nombre or " " in self.nombre:
            return False, "El nombre debe existir y no contener espacios."
        if not self.categoria:
            return False, "La categoria es obligatoria."
        if not self.descripcion:
            return False, "La descripcion es obligatoria."
        if self.handler is not None and not callable(self.handler):
            return False, "handler debe ser callable o None."
        if not isinstance(self.parametros_esquema, dict):
            return False, "parametros_esquema debe ser un diccionario."
        requeridos = self.parametros_esquema.get("requeridos", self.parametros_esquema.get("required", []))
        opcionales = self.parametros_esquema.get("opcionales", self.parametros_esquema.get("optional", []))
        if isinstance(requeridos, str) or isinstance(opcionales, str):
            return False, "Las listas requeridos/opcionales deben ser listas."
        if requeridos is not None and not isinstance(requeridos, (list, tuple)):
            return False, "requeridos debe ser una lista."
        if opcionales is not None and not isinstance(opcionales, (list, tuple)):
            return False, "opcionales debe ser una lista."
        return True, ""

    def a_dict(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "categoria": self.categoria,
            "descripcion": self.descripcion,
            "parametros_esquema": dict(self.parametros_esquema),
            **self.metadatos(),
        }


@dataclass
class ResultadoEjecucion:
    id_solicitud: str
    herramienta: str
    estado: str
    exito: bool
    datos: Any = None
    error: Optional[dict[str, Any]] = None
    duracion_ms: float = 0.0
    metadatos: dict[str, Any] = field(default_factory=dict)
    timestamp_fin: float = field(default_factory=time.time)

    def a_dict(self) -> dict[str, Any]:
        return {
            "id_solicitud": self.id_solicitud,
            "herramienta": self.herramienta,
            "estado": self.estado,
            "exito": self.exito,
            "datos": self.datos,
            "error": dict(self.error) if self.error else None,
            "duracion_ms": round(max(0.0, float(self.duracion_ms)), 3),
            "metadatos": dict(self.metadatos),
            "timestamp_fin": self.timestamp_fin,
        }


def resultado_error(
    solicitud: SolicitudEjecucion,
    codigo: str,
    mensaje: str,
    recuperable: bool = True,
    duracion_ms: float = 0.0,
    metadatos: Optional[dict[str, Any]] = None,
) -> ResultadoEjecucion:
    """Construye un resultado fallido sin lanzar excepciones."""
    return ResultadoEjecucion(
        id_solicitud=solicitud.id_solicitud,
        herramienta=solicitud.herramienta,
        estado=ESTADO_RECHAZADA,
        exito=False,
        datos=None,
        error={"codigo": codigo, "mensaje": mensaje, "recuperable": bool(recuperable)},
        duracion_ms=duracion_ms,
        metadatos=dict(metadatos or {}),
    )
