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
    "pon", "ponme", "pone", "reproduce", "reproducir", "toca", "coloca",
    "minimiza", "minimaliza", "minimizar", "maximiza", "maximizar", "sube",
    "baja", "pausa", "pausar", "quita", "quitar", "hazlo",
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

# Erratas típicas de Whisper: las canonicalizamos antes de comparar keywords.
_ERRATAS = (
    (r"\bminimaliz(?:a|ar|e|o|ame)\b", "minimizar"),
    (r"\bminimic(?:e|ame|aste)\b", "minimizar"),
    (r"\bminimiza(?:r|s)?\b", "minimizar"),
    (r"\bventanas\b", "ventana"),
)
AFIRMACIONES = {"si", "claro", "dale", "vale", "adelante", "hazlo", "ok", "supuesto"}
OFERTAS_ACCION = (
    "te pongo", "te preparo", "te reproduzco", "te abro", "te cierro",
    "te escribo", "te envio", "te hago", "quieres que", "te gustaria",
)


def _normalizar(texto):
    norm = "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    for patron, sustituto in _ERRATAS:
        norm = re.sub(patron, sustituto, norm)
    return norm


def oferta_accionable(historial_reciente):
    """Texto de la última oferta accionable de Lyris, si la hay."""
    for mensaje in reversed(list(historial_reciente or [])):
        if not isinstance(mensaje, dict):
            continue
        if mensaje.get("role") not in ("assistant", "lyris"):
            continue
        contenido = _normalizar(mensaje.get("content", ""))
        if any(m in contenido for m in OFERTAS_ACCION):
            return contenido
    return ""


def es_afirmacion_breve(texto, oferta):
    """True si el usuario acepta una oferta previa con un sí/dale corto."""
    if not oferta:
        return False
    palabras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return bool(palabras) and palabras[0] in AFIRMACIONES and len(palabras) <= 10


def tiene_intencion_operativa(texto, historial_reciente=None):
    """True solo si el mensaje pide una acción real, no charla o teoría."""
    norm = _normalizar(texto)
    palabras = set(re.findall(r"[a-z0-9]+", norm))
    if any(m in norm for m in MARCADORES_TEORIA) and not (palabras & VERBOS_EJECUCION):
        return False
    if palabras & VERBOS_OPERATIVOS:
        return True
    if es_afirmacion_breve(texto, oferta_accionable(historial_reciente)):
        return True
    for keywords, _ in CATEGORIAS_ACCIONES.values():
        for k in keywords:
            if (" " in k and k in norm) or (" " not in k and k in palabras):
                return True
    return False


def catalogo_condicional(texto=None, modulo_acciones=None, incluir_base=True,
                         historial_reciente=None):
    """Catálogo completo ante intención operativa; bloque mínimo en charla/teoría."""
    if not tiene_intencion_operativa(texto, historial_reciente):
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

    oferta = oferta_accionable(historial_reciente)
    efectivo = f"{oferta} {texto or ''}" if oferta else texto
    norm = _normalizar(efectivo)
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
