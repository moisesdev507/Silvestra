"""Validacion compacta de esquemas y tipos para SolicitudEjecucion."""
from __future__ import annotations

from typing import Any


TIPOS_ESPERADOS = {
    "str": str, "string": str, "int": int, "integer": int,
    "float": float, "number": (int, float), "bool": bool,
    "boolean": bool, "dict": dict, "list": list,
    "tuple": tuple, "any": object,
}


def esquema_parametros(esquema: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    if not isinstance(esquema, dict):
        return [], [], {}
    requeridos = esquema.get("requeridos", esquema.get("required", []))
    opcionales = esquema.get("opcionales", esquema.get("optional", []))
    tipos = esquema.get("tipos", esquema.get("properties", {}))
    if isinstance(requeridos, str):
        requeridos = [requeridos]
    if isinstance(opcionales, str):
        opcionales = [opcionales]
    if not isinstance(requeridos, list):
        requeridos = list(requeridos or [])
    if not isinstance(opcionales, list):
        opcionales = list(opcionales or [])
    if not isinstance(tipos, dict):
        tipos = {}
    return requeridos, opcionales, tipos


def coincide_tipo(valor: Any, especificacion: Any) -> bool:
    if isinstance(especificacion, dict):
        especificacion = especificacion.get("type", "any")
    tipo = str(especificacion).strip().lower()
    if tipo in ("str", "string"):
        return isinstance(valor, str)
    if tipo in ("int", "integer"):
        return isinstance(valor, int) and not isinstance(valor, bool)
    if tipo in ("float",):
        return isinstance(valor, float)
    if tipo in ("number",):
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    if tipo in ("bool", "boolean"):
        return isinstance(valor, bool)
    if tipo in ("dict",):
        return isinstance(valor, dict)
    if tipo in ("list",):
        return isinstance(valor, list)
    if tipo in ("tuple",):
        return isinstance(valor, tuple)
    if tipo in ("any",):
        return True
    if isinstance(especificacion, type):
        return isinstance(valor, especificacion)
    return bool(TIPOS_ESPERADOS.get(tipo)) and isinstance(
        valor, TIPOS_ESPERADOS[tipo]
    )
