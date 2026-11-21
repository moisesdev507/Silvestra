"""Modelos sanitizados y modos de autonomia controlada."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


RESTRINGIDO = "restringido"
SUPERVISADO = "supervisado"
PREAUTORIZADO = "preautorizado"
MODOS_AUTONOMIA = (RESTRINGIDO, SUPERVISADO, PREAUTORIZADO)

RECIBIDA = "recibida"
RESPONDIDA_SIN_EJECUCION = "respondida_sin_ejecucion"
PLANIFICANDO = "planificando"
ESPERANDO_AUTORIZACION = "esperando_autorizacion"
EJECUTANDO = "ejecutando"
VERIFICANDO = "verificando"
RECUPERANDO = "recuperando"
COMPLETADA = "completada"
PARCIAL = "parcial"
FALLIDA = "fallida"
CANCELADA = "cancelada"
REQUIERE_INTERVENCION = "requiere_intervencion_humana"

CLAVES_SENSIBLES = (
    "password", "passwd", "token", "secret", "clave", "api_key",
    "apikey", "texto", "contenido", "authorization",
)


def sanitizar_datos(datos: Any) -> Any:
    if isinstance(datos, dict):
        return {
            str(k): "***" if any(s in str(k).lower() for s in CLAVES_SENSIBLES)
            else sanitizar_datos(v)
            for k, v in datos.items()
        }
    if isinstance(datos, list):
        return [sanitizar_datos(v) for v in datos]
    if isinstance(datos, tuple):
        return [sanitizar_datos(v) for v in datos]
    return datos


@dataclass
class PasoPlanOperativo:
    id_paso: str
    titulo: str
    herramienta: str
    parametros: dict[str, Any] = field(default_factory=dict)
    dependencias: tuple[str, ...] = ()
    estado: str = RECIBIDA
    id_solicitud: Optional[str] = None
    id_autorizacion: Optional[str] = None
    informe_verificacion: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.id_paso = str(self.id_paso)
        self.titulo = str(self.titulo).strip()
        self.herramienta = str(self.herramienta).strip().lower()
        if isinstance(self.dependencias, str):
            self.dependencias = tuple(
                d.strip() for d in self.dependencias.split(",") if d.strip()
            )
        else:
            self.dependencias = tuple(str(d) for d in self.dependencias)
        self.parametros = dict(self.parametros)

    def a_dict(self) -> dict:
        return {
            "id_paso": self.id_paso,
            "titulo": self.titulo,
            "herramienta": self.herramienta,
            "parametros": sanitizar_datos(self.parametros),
            "dependencias": list(self.dependencias),
            "estado": self.estado,
            "id_solicitud": self.id_solicitud,
            "id_autorizacion": self.id_autorizacion,
            "informe_verificacion": sanitizar_datos(self.informe_verificacion),
        }


@dataclass
class OrdenOperativa:
    objetivo: str
    origen: str
    modo_autonomia: str = SUPERVISADO
    requiere_ejecucion: bool = True
    id_orden: str = field(default_factory=lambda: str(uuid.uuid4()))
    estado: str = RECIBIDA
    pasos: list[PasoPlanOperativo] = field(default_factory=list)
    progreso_pct: float = 0.0
    historial_eventos: list[dict[str, Any]] = field(default_factory=list)
    creada_en: float = field(default_factory=time.time)
    actualizada_en: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.modo_autonomia not in MODOS_AUTONOMIA:
            raise ValueError("Modo de autonomia invalido")
        self.objetivo = str(self.objetivo).strip()

    def registrar_evento(self, tipo: str, detalle: str = "") -> None:
        self.historial_eventos.append({
            "tipo": str(tipo),
            "detalle": sanitizar_datos(detalle),
            "timestamp": time.time(),
        })
        self.actualizada_en = time.time()

    def actualizar_progreso(self) -> float:
        if not self.pasos:
            self.progreso_pct = 100.0 if self.estado == COMPLETADA else 0.0
        else:
            terminales = sum(
                1 for p in self.pasos
                if p.estado in (COMPLETADA, FALLIDA, CANCELADA, REQUIERE_INTERVENCION)
            )
            self.progreso_pct = round(terminales * 100.0 / len(self.pasos), 2)
        self.actualizada_en = time.time()
        return self.progreso_pct

    def a_dict(self) -> dict:
        return {
            "id_orden": self.id_orden,
            "objetivo": self.objetivo,
            "origen": self.origen,
            "modo_autonomia": self.modo_autonomia,
            "requiere_ejecucion": bool(self.requiere_ejecucion),
            "estado": self.estado,
            "pasos": [p.a_dict() for p in self.pasos],
            "progreso_pct": self.progreso_pct,
            "historial_eventos": sanitizar_datos(self.historial_eventos),
            "creada_en": self.creada_en,
            "actualizada_en": self.actualizada_en,
        }


@dataclass
class InformeOperativoFinal:
    id_orden: str
    completados: list[str] = field(default_factory=list)
    parciales: list[str] = field(default_factory=list)
    fallidas: list[str] = field(default_factory=list)
    pendientes: list[str] = field(default_factory=list)
    cancelados: list[str] = field(default_factory=list)
    resumen_legible: str = ""
    auditoria_sanitizada: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict:
        return {
            "id_orden": self.id_orden,
            "completados": list(self.completados),
            "parciales": list(self.parciales),
            "fallidas": list(self.fallidas),
            "pendientes": list(self.pendientes),
            "cancelados": list(self.cancelados),
            "resumen_legible": self.resumen_legible,
            "auditoria_sanitizada": sanitizar_datos(self.auditoria_sanitizada),
        }
