"""Catálogo estructurado y consultable de herramientas del núcleo agéntico."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import acciones

# Palabras que elevan el riesgo de una acción (alineado con AGENTS.md).
RIESGO_ALTO = (
    "borrar", "eliminar", "destruir", "enviar", "mandar", "transferir",
    "pagar", "formatear", "confirmar_habilidad", "ejecutar_comando",
)
RIESGO_MEDIO = (
    "escribir", "crear", "modificar", "cambiar", "mover", "renombrar",
    "aprender", "activar", "desactivar", "subir_volumen", "bajar_volumen",
    "silenciar", "recordatorio",
)


@dataclass(frozen=True)
class Herramienta:
    """Descripción compacta y segura de una capacidad ya existente."""

    nombre: str
    descripcion: str
    parametros: tuple = ()
    precondiciones: tuple = ()
    postcondiciones: tuple = ()
    riesgo: str = "bajo"

    def a_dict(self):
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "parametros": list(self.parametros),
            "precondiciones": list(self.precondiciones),
            "postcondiciones": list(self.postcondiciones),
            "riesgo": self.riesgo,
        }


def clasificar_riesgo(nombre, descripcion=""):
    """Clasifica en bajo/medio/alto sin depender de otro módulo del agente."""
    texto = f"{nombre} {descripcion}".lower()
    if any(palabra in texto for palabra in RIESGO_ALTO):
        return "alto"
    if any(palabra in texto for palabra in RIESGO_MEDIO):
        return "medio"
    return "bajo"


def _crear(nombre, descripcion, necesita_texto=False):
    nombre = str(nombre or "").strip().lower()
    descripcion = str(descripcion or "").strip()
    pre = ("silvestra_activa",)
    post = ("respuesta_al_usuario",)
    if necesita_texto:
        pre += ("texto_no_vacio",)
        post += ("argumento_utilizado",)
    return Herramienta(
        nombre=nombre,
        descripcion=descripcion[:180],
        parametros=("texto",) if necesita_texto else (),
        precondiciones=pre,
        postcondiciones=post,
        riesgo=clasificar_riesgo(nombre, descripcion),
    )


def construir_catalogo():
    """Deriva el catálogo de acciones.py sin duplicar sus implementaciones."""
    salida = []
    for nombre, (_funcion, necesita_texto, descripcion) in acciones.ACCIONES.items():
        salida.append(_crear(nombre, descripcion, necesita_texto))
    for nombre, descripcion in acciones.ESPECIALES.items():
        salida.append(_crear(nombre, descripcion))
    for nombre, (_funcion, descripcion) in acciones.VIVAS.items():
        salida.append(_crear(nombre, descripcion, nombre in acciones.CON_TEXTO))
    return salida


_CATALOGO = None


def catalogo(actualizar=False):
    """Catálogo cacheado; se actualiza al registrar acciones vivas tardías."""
    global _CATALOGO
    if _CATALOGO is None or actualizar:
        _CATALOGO = construir_catalogo()
    return list(_CATALOGO)


def _normalizar(texto):
    s = str(texto or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return s


def obtener(nombre, catalogo=None):
    """Devuelve una herramienta por nombre o None."""
    objetivo = str(nombre or "").strip().lower()
    items = catalogo if catalogo is not None else globals()["catalogo"]()
    for herramienta in items:
        if herramienta.nombre == objetivo:
            return herramienta
    return None


def consultar(consulta, limite=6, catalogo=None):
    """Consulta filtrada por relevancia para no inflar el prompt del LLM."""
    items = catalogo if catalogo is not None else globals()["catalogo"]()
    limite = max(1, min(12, int(limite)))
    terminos = [t for t in re.findall(r"[a-z0-9_]+", _normalizar(consulta)) if len(t) > 2]
    if not terminos:
        return items[:limite]
    consulta_norm = _normalizar(consulta)
    puntuados = []
    for herramienta in items:
        texto = _normalizar(f"{herramienta.nombre} {herramienta.descripcion}")
        score = sum(1 for termino in terminos if termino in texto)
        if herramienta.nombre.replace("_", " ") in consulta_norm:
            score += 3
        if score:
            puntuados.append((score, herramienta.nombre, herramienta))
    puntuados.sort(key=lambda entry: (-entry[0], entry[1]))
    return [entry[2] for entry in puntuados[:limite]]


def describir(herramientas=None):
    """Texto compacto listo para inyectar en un prompt."""
    return "\n".join(
        f"- {h.nombre} [{h.riesgo}]: {h.descripcion}"
        for h in (herramientas if herramientas is not None else catalogo())
    )
