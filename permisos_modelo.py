"""Modelo serializable para politicas, autorizaciones y auditoria."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional


NIVEL_PROHIBIDA = "prohibida"
NIVEL_SOLO_LECTURA = "solo_lectura"
NIVEL_REQUIERE_CONFIRMACION = "requiere_confirmacion"
NIVEL_SENSIBLE_REFORZADA = "sensible_reforzada"
NIVELES_AUTORIZACION = (
    NIVEL_PROHIBIDA,
    NIVEL_SOLO_LECTURA,
    NIVEL_REQUIERE_CONFIRMACION,
    NIVEL_SENSIBLE_REFORZADA,
)

ESTADO_PENDIENTE = "pendiente"
ESTADO_APROBADA = "aprobada"
ESTADO_DENEGADA = "denegada"
ESTADO_CADUCADA = "caducada"
ESTADO_REVOCADA = "revocada"
ESTADO_CONSUMIDA = "consumida"
ESTADOS_AUTORIZACION = (
    ESTADO_PENDIENTE,
    ESTADO_APROBADA,
    ESTADO_DENEGADA,
    ESTADO_CADUCADA,
    ESTADO_REVOCADA,
    ESTADO_CONSUMIDA,
)

ORIGINES_VALIDOS = ("cerebro", "planificador", "usuario", "sistema")
CLAVES_SENSIBLES = (
    "password", "passwd", "token", "secret", "clave", "api_key",
    "apikey", "contenido", "authorization",
)


@dataclass
class PoliticaOperacion:
    herramienta: str
    nivel_autorizacion: str
    riesgo_maximo_permitido: str = "bajo"
    permisos_requeridos: tuple[str, ...] = ()
    ttl_seg_por_defecto: float = 300.0
    requiere_doble_confirmacion: bool = False
    habilitada: bool = True

    def __post_init__(self) -> None:
        self.herramienta = str(self.herramienta or "").strip().lower()
        self.nivel_autorizacion = str(self.nivel_autorizacion or "").strip().lower()
        self.riesgo_maximo_permitido = str(self.riesgo_maximo_permitido or "bajo").strip().lower()
        if self.nivel_autorizacion not in NIVELES_AUTORIZACION:
            raise ValueError("nivel_autorizacion invalido")
        if isinstance(self.permisos_requeridos, str):
            self.permisos_requeridos = tuple(
                p.strip() for p in self.permisos_requeridos.split(",") if p.strip()
            )
        else:
            self.permisos_requeridos = tuple(str(p) for p in self.permisos_requeridos)
        self.ttl_seg_por_defecto = float(self.ttl_seg_por_defecto)
        if self.ttl_seg_por_defecto <= 0:
            raise ValueError("ttl_seg_por_defecto debe ser positivo")
        if not isinstance(self.requiere_doble_confirmacion, bool):
            raise TypeError("requiere_doble_confirmacion debe ser bool")
        if not isinstance(self.habilitada, bool):
            raise TypeError("habilitada debe ser bool")

    def valida_integridad(self) -> tuple[bool, str]:
        if not self.herramienta:
            return False, "herramienta obligatoria"
        if self.nivel_autorizacion not in NIVELES_AUTORIZACION:
            return False, "nivel_autorizacion invalido"
        if self.nivel_autorizacion == NIVEL_SENSIBLE_REFORZADA:
            if not self.requiere_doble_confirmacion:
                return False, "la sensible reforzada requiere doble confirmacion"
        return True, ""

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, datos: dict[str, Any]) -> "PoliticaOperacion":
        if not isinstance(datos, dict):
            raise TypeError("PoliticaOperacion debe crearse desde un diccionario")
        return cls(
            herramienta=datos.get("herramienta", ""),
            nivel_autorizacion=datos.get("nivel_autorizacion", ""),
            riesgo_maximo_permitido=datos.get("riesgo_maximo_permitido", "bajo"),
            permisos_requeridos=tuple(datos.get("permisos_requeridos", ()) or ()),
            ttl_seg_por_defecto=float(datos.get("ttl_seg_por_defecto", 300.0)),
            requiere_doble_confirmacion=bool(datos.get("requiere_doble_confirmacion", False)),
            habilitada=bool(datos.get("habilitada", True)),
        )


@dataclass
class SolicitudAutorizacion:
    id_solicitud: str
    herramienta: str
    origen: str
    nivel_autorizacion: str
    huella_operacion: str
    id_autorizacion: str = field(default_factory=lambda: str(uuid.uuid4()))
    estado: str = ESTADO_PENDIENTE
    creada_en: float = field(default_factory=time.time)
    expira_en: float = 0.0

    def __post_init__(self) -> None:
        self.herramienta = str(self.herramienta or "").strip().lower()
        self.origen = str(self.origen or "sistema").strip().lower()
        if self.origen not in ORIGINES_VALIDOS:
            raise ValueError("origen de autorizacion invalido")
        if self.nivel_autorizacion not in NIVELES_AUTORIZACION:
            raise ValueError("nivel_autorizacion invalido")
        if self.estado not in ESTADOS_AUTORIZACION:
            raise ValueError("estado de autorizacion invalido")

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, datos: dict[str, Any]) -> "SolicitudAutorizacion":
        if not isinstance(datos, dict):
            raise TypeError("SolicitudAutorizacion debe crearse desde un diccionario")
        return cls(
            id_solicitud=str(datos.get("id_solicitud", "")),
            herramienta=str(datos.get("herramienta", "")),
            origen=str(datos.get("origen", "sistema")),
            nivel_autorizacion=str(datos.get("nivel_autorizacion", "")),
            huella_operacion=str(datos.get("huella_operacion", "")),
            id_autorizacion=str(datos.get("id_autorizacion") or uuid.uuid4()),
            estado=str(datos.get("estado", ESTADO_PENDIENTE)),
            creada_en=float(datos.get("creada_en") or time.time()),
            expira_en=float(datos.get("expira_en") or 0.0),
        )


@dataclass
class ConcesionAutorizacion:
    id_solicitud: str
    id_autorizacion: str
    huella_operacion: str
    nonce: str = field(default_factory=lambda: str(uuid.uuid4()))
    aprobada_por: str = "usuario"
    expira_en: float = 0.0
    consumida: bool = False
    revocada: bool = False

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EventoAuditoria:
    tipo_evento: str
    id_solicitud: str
    id_autorizacion: str
    herramienta: str
    origen: str
    actor: str
    decision: str
    motivo: str
    parametros_sanitizados: dict[str, Any] = field(default_factory=dict)
    id_evento: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


def huella_operacion(herramienta: str, parametros: dict[str, Any], id_solicitud: str) -> str:
    """Genera SHA-256 canonico sobre herramienta, parametros e id_solicitud."""
    canonico = json.dumps(
        {
            "herramienta": str(herramienta).strip().lower(),
            "parametros": parametros if isinstance(parametros, dict) else {},
            "id_solicitud": str(id_solicitud),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def sanitizar_parametros(parametros: dict[str, Any]) -> dict[str, Any]:
    """Enmascara claves sensibles sin modificar los parametros originales."""
    limpio: dict[str, Any] = {}
    if not isinstance(parametros, dict):
        return limpio
    for clave, valor in parametros.items():
        nombre = str(clave).strip().lower()
        if any(sens in nombre for sens in CLAVES_SENSIBLES):
            limpio[str(clave)] = "***"
        elif isinstance(valor, dict):
            limpio[str(clave)] = sanitizar_parametros(valor)
        else:
            limpio[str(clave)] = valor
    return limpio
