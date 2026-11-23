"""Calidad de recuerdos: ruido, autorreferencias de IA y dedup semántico."""
import re
import unicodedata

import memoria_embeddings as me


AUTORREF = (
    r"fui desarrollad[ao] por primera vez",
    r"fui desarrollad[ao] por",
    r"fui cread[ao] por",
    r"fui programad[ao] por",
    r"fui entrenad[ao] por",
    r"la personalidad de lyris",
    r"soy (un |una )?asistente virtual",
    r"como modelo de lenguaje",
    r"mi creador(es)?",
    r"no tengo (sentimientos|emociones)",
    r"arquitectura de (lyris|silvestra)",
    r"me llamo lyris",
)

RUIDO = {
    "hola", "gracias", "buenos dias", "buenas noches", "ok", "de acuerdo",
    "entiendo", "adios", "nos vemos", "como estas", "que tal", "oye",
    "por favor", "listo", "vale", "genial", "claro",
}


def normalizar(texto):
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def es_autorreferencia_ia(texto):
    """Detecta texto sobre la propia IA, no sobre el usuario."""
    t = normalizar(texto)
    if not t:
        return False
    return any(re.search(pat, t) for pat in AUTORREF)


def es_ruido_conversacional(texto):
    """Descarta interjecciones y frases conversacionales sin contenido."""
    t = normalizar(texto).strip(" .!?¿¡,")
    if not t:
        return True
    if t in RUIDO:
        return True
    palabras = t.split()
    if len(palabras) <= 3 and any(t.startswith(x + " ") or t == x for x in RUIDO):
        return True
    return len(t) < 12 and len(palabras) <= 3


def es_duplicado_semantico(nuevo, existentes, umbral=0.92, vector_fn=None):
    """Dedup por coseno; por defecto usa el fallback determinista ligero."""
    if not nuevo or not existentes:
        return False
    fn = vector_fn or (lambda t: me.vector(t, "documento", False))
    try:
        objetivo = fn(nuevo)
    except Exception:
        return False
    if objetivo is None:
        return False
    for texto in existentes:
        if not texto:
            continue
        try:
            otro = fn(texto)
        except Exception:
            continue
        if me.coseno(objetivo, otro) > umbral:
            return True
    return False


def evaluar(texto, existentes=None, umbral=0.92, vector_fn=None):
    """Política única de calidad. Devuelve (aceptable, motivo)."""
    if es_autorreferencia_ia(texto):
        return False, "autorreferencia_ia"
    if es_ruido_conversacional(texto):
        return False, "ruido_conversacional"
    if existentes and es_duplicado_semantico(texto, existentes, umbral, vector_fn):
        return False, "duplicado_semantico"
    return True, ""
