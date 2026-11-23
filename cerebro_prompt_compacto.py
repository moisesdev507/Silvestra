"""Catálogo condicional de acciones y detección de intención operativa."""
from __future__ import annotations

import re
import unicodedata

from cerebro_categorias import ACCIONES_BASE, CATEGORIAS_ACCIONES

VERBOS_OPERATIVOS = {
    "abrir", "buscar", "recordar", "crear", "enviar", "configurar", "ejecutar",
    "clima", "hora", "archivo", "archivos", "sistema", "hud", "luz", "luces",
    "cerrar", "guardar", "anotar", "eliminar", "borrar", "activar", "desactivar",
    "mostrar", "ocultar", "indexar", "leer", "escribir", "descansar", "avisar",
    "recordatorio", "recordatorios", "pendiente", "pendientes", "presentacion",
}
VERBOS_EJECUCION = {
    "abrir", "enviar", "crear", "ejecutar", "guardar", "borrar", "eliminar",
    "activar", "desactivar", "configurar", "indexar", "escribir", "leer",
    "mostrar", "ocultar", "descansar", "buscar",
}
MARCADORES_TEORIA = (
    "que es", "como funciona", "explica", "explicame", "teoria", "concepto",
    "por que", "diferencia entre", "significa", "como se calcula",
)
BLOQUE_MINIMO = "- ninguna (charla: no ejecutar acciones)"


def _normalizar(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def tiene_intencion_operativa(texto):
    """True solo si el mensaje pide una acción real, no charla o teoría."""
    norm = _normalizar(texto)
    palabras = set(re.findall(r"[a-z0-9]+", norm))
    if any(m in norm for m in MARCADORES_TEORIA) and not (palabras & VERBOS_EJECUCION):
        return False
    if palabras & VERBOS_OPERATIVOS:
        return True
    for keywords, _ in CATEGORIAS_ACCIONES.values():
        for k in keywords:
            if (" " in k and k in norm) or (" " not in k and k in palabras):
                return True
    return False


def catalogo_condicional(texto=None, modulo_acciones=None, incluir_base=True):
    """Catálogo completo ante intención operativa; bloque mínimo en charla/teoría."""
    if not tiene_intencion_operativa(texto):
        return BLOQUE_MINIMO
    if modulo_acciones is None:
        return BLOQUE_MINIMO

    todas = {}
    for n, (_, _, desc) in getattr(modulo_acciones, "ACCIONES", {}).items():
        todas[n] = desc
    for n, desc in getattr(modulo_acciones, "ESPECIALES", {}).items():
        todas[n] = desc
    for n, (_, desc) in getattr(modulo_acciones, "VIVAS", {}).items():
        todas[n] = desc

    norm = _normalizar(texto)
    elegidas = set(ACCIONES_BASE) if incluir_base else set()
    palabras = set(re.findall(r"[a-z0-9]+", norm))
    for _, (keywords, nombres) in CATEGORIAS_ACCIONES.items():
        coincide = any(
            (k in norm) if " " in k else (k in palabras) for k in keywords
        )
        if coincide:
            elegidas.update(nombres)

    lineas = []
    for nombre in sorted(elegidas):
        if nombre in todas:
            desc = todas[nombre].split("(")[0].strip().split(".")[0].strip()[:35]
            lineas.append(f"- {nombre}: {desc}")
    return "\n".join(lineas) or BLOQUE_MINIMO
