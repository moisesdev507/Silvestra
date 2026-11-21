"""Adaptador aislado para inventariar acciones heredadas sin enlazar handlers."""
from __future__ import annotations

from typing import Any

from ejecucion_modelo import ContratoHerramienta


def _tipo_desde_accion(necesita_texto: bool) -> dict[str, Any]:
    if necesita_texto:
        return {
            "requeridos": ["texto"],
            "opcionales": [],
            "tipos": {"texto": "str"},
        }
    return {"requeridos": [], "opcionales": [], "tipos": {}}


def inventariar_acciones() -> list[ContratoHerramienta]:
    """Crea contratos descriptivos con handler=None; nunca ejecuta acciones heredadas."""
    import acciones

    contratos: list[ContratoHerramienta] = []
    for nombre, contenido in getattr(acciones, "ACCIONES", {}).items():
        descripcion = str(contenido[2]) if len(contenido) > 2 else "Accion heredada."
        necesita_texto = bool(contenido[1]) if len(contenido) > 1 else False
        contratos.append(ContratoHerramienta(
            nombre=str(nombre),
            categoria="sistema",
            descripcion=f"Inventario heredado (sin ejecucion): {descripcion}",
            parametros_esquema=_tipo_desde_accion(necesita_texto),
            handler=None,
            nivel_riesgo="medio",
            requiere_confirmacion=True,
            cancelable=False,
            asincrona=False,
            timeout_seg=30.0,
            habilitada=False,
        ))

    for nombre, descripcion in getattr(acciones, "ESPECIALES", {}).items():
        contratos.append(ContratoHerramienta(
            nombre=str(nombre),
            categoria="sistema",
            descripcion=f"Inventario especial heredado (sin ejecucion): {descripcion}",
            parametros_esquema={"requeridos": [], "opcionales": [], "tipos": {}},
            handler=None,
            nivel_riesgo="alto",
            requiere_confirmacion=True,
            cancelable=True,
            asincrona=False,
            timeout_seg=30.0,
            habilitada=False,
        ))

    for nombre, contenido in getattr(acciones, "VIVAS", {}).items():
        descripcion = str(contenido[1]) if isinstance(contenido, (tuple, list)) and len(contenido) > 1 else str(contenido)
        con_texto = nombre in getattr(acciones, "CON_TEXTO", set())
        contratos.append(ContratoHerramienta(
            nombre=str(nombre),
            categoria="sistema",
            descripcion=f"Inventario vivo heredado (sin ejecucion): {descripcion}",
            parametros_esquema=_tipo_desde_accion(con_texto),
            handler=None,
            nivel_riesgo="medio",
            requiere_confirmacion=True,
            cancelable=False,
            asincrona=False,
            timeout_seg=30.0,
            habilitada=False,
        ))
    return contratos
