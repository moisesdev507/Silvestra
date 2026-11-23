"""Compuerta de permisos y confirmación humana del núcleo agéntico."""
from __future__ import annotations

from dataclasses import dataclass

import agente_herramientas as ah
import verificacion_modelo as vm


@dataclass(frozen=True)
class DecisionPermiso:
    permitido: bool
    riesgo: str
    motivo: str
    confirmado: bool = False

    def a_dict(self):
        return {
            "permitido": self.permitido,
            "riesgo": self.riesgo,
            "motivo": self.motivo,
            "confirmado": self.confirmado,
        }


class CompuertaPermisos:
    """Fail-closed para riesgo alto: exige un callback humano inyectable."""

    def __init__(self, confirmar=None):
        self.confirmar = confirmar if callable(confirmar) else None

    def evaluar(self, herramienta, parametros=None):
        if isinstance(herramienta, str):
            nombre = herramienta
            descripcion = ""
            riesgo = ah.clasificar_riesgo(nombre, descripcion)
        else:
            nombre = str(getattr(herramienta, "nombre", herramienta))
            descripcion = str(getattr(herramienta, "descripcion", "") or "")
            riesgo = getattr(herramienta, "riesgo", None) or ah.clasificar_riesgo(
                nombre, descripcion)
        riesgo = str(riesgo or "bajo").strip().lower()
        if riesgo not in ("bajo", "medio", "alto"):
            riesgo = "alto"
        if riesgo != "alto":
            return DecisionPermiso(True, riesgo, "riesgo_aceptable")
        if self.confirmar is None:
            return DecisionPermiso(False, riesgo, "confirmacion_no_disponible")
        datos = vm.sanitizar_datos(parametros if isinstance(parametros, dict) else {})
        try:
            aprobado = bool(self.confirmar(nombre, descripcion, datos))
        except Exception:
            aprobado = False
        if not aprobado:
            return DecisionPermiso(False, riesgo, "confirmacion_rechazada")
        return DecisionPermiso(True, riesgo, "confirmacion_humana", True)


def requiere_confirmacion(herramienta):
    """True cuando la herramienta pertenece al nivel de riesgo alto."""
    riesgo = getattr(herramienta, "riesgo", None)
    if riesgo is None:
        riesgo = ah.clasificar_riesgo(
            getattr(herramienta, "nombre", herramienta),
            getattr(herramienta, "descripcion", ""),
        )
    return str(riesgo).lower() == "alto"
