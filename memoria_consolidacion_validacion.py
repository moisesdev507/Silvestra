"""Detección conservadora de entidades y valores incompatibles."""
import re

TECNOLOGIAS = {"python", "rust", "java", "javascript", "typescript", "sqlite", "postgresql", "mysql", "mongodb", "pyside6", "whisper", "vosk"}
PREDICADOS = ("tiene como objetivo", "trabaja en", "depende de", "vive en", "utiliza", "prefiere", "estudia", "usa", "es")
MARCADORES = ("proyecto", "aplicacion", "empresa", "ciudad", "persona", "producto", "herramienta", "equipo")
PARADA = {"mi", "mis", "el", "la", "los", "las", "un", "una", "de", "del", "en", "que", "para", "con", "por", "su", "sus", "y", "es"}

# Criterio único de deduplicación compartido por memoria_sueno y memoria_consolidacion.
UMBRAL_DEDUP = 0.82
_PARADA_DEDUP = {"para", "como", "este", "esta", "estos", "estas", "pero", "sobre",
                 "entre", "tiene", "hace", "donde"}


def tokens_duplicacion(texto):
    """Tokens normalizados para comparar recuerdos (sin ruido funcional)."""
    palabras = re.findall(r"[a-záéíóúüñ0-9]{3,}", str(texto or "").casefold())
    return {p for p in palabras if p not in _PARADA_DEDUP}


def es_duplicado(a, b):
    """True si dos textos son el mismo recuerdo según el criterio compartido."""
    x, y = tokens_duplicacion(a), tokens_duplicacion(b)
    if not x or not y:
        return False
    return len(x & y) / len(x | y) >= UMBRAL_DEDUP


def tokens(texto):
    return set(re.findall(r"\w+", str(texto or "").casefold()))


def similitud(a, b):
    x, y = tokens(a), tokens(b)
    return len(x & y) / max(1, len(x | y))


def afirmacion(texto):
    bajo = texto.casefold()
    for verbo in PREDICADOS:
        m = re.search(r"\b(.{2,100}?)\s+" + re.escape(verbo) + r"\s+(.+)", bajo)
        if m:
            sujeto = " ".join(tokens(m.group(1)) - PARADA)
            objeto = set(re.findall(r"\w+", m.group(2))) - PARADA
            return sujeto, verbo, objeto
    return "", "", set()


def entidades(texto):
    salida = set()
    for marca in MARCADORES:
        m = re.search(r"\b" + marca + r"\s+([A-ZÁÉÍÓÚÑ][\w-]+)", texto, re.I)
        if m and m.group(1)[0].isupper():
            salida.add(m.group(1).casefold())
    return salida


def incompatibilidad(a, b):
    x, y = tokens(a), tokens(b)
    if not x & y:
        return ""
    if ("no" in x) != ("no" in y):
        return "polaridad"
    tx, ty = x & TECNOLOGIAS, y & TECNOLOGIAS
    if tx and ty and tx != ty:
        return "tecnologia"
    ex, ey = entidades(str(a)), entidades(str(b))
    if ex and ey and ex.isdisjoint(ey):
        return "entidad"
    sx, px, ox = afirmacion(str(a))
    sy, py, oy = afirmacion(str(b))
    if sx and sx == sy and px == py:
        if (tx | ex) and (ty | ey) and (tx | ex).isdisjoint(ty | ey):
            return "valor"
        nx = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", str(a)))
        ny = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", str(b)))
        if nx and ny and nx.isdisjoint(ny):
            return "valor"
    return ""
