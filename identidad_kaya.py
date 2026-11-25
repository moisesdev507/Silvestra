"""Identidad oficial, wake-word y fonética para Kaya."""
import re
import unicodedata

NOMBRE_OFICIAL = "Kaya"
NOMBRE_LOWER = "kaya"

# Keyterm priorizado para Deepgram Nova-3 y prompt base para Groq Whisper
KEYTERM_DEEPGRAM = "Kaya:5,Kaia:3,Caya:2"
PROMPT_WHISPER = (
    "Conversación en español latinoamericano con la asistente Kaya. "
    "Órdenes comunes: Kaya, preséntate, baila, para de bailar, mira mi pantalla, "
    "Visual Studio Code, qué hora es, busca en internet."
)

# Variantes fonéticas aceptadas en cualquier posición de la transcripción
ALIAS_DIRECTOS = {"kaya", "kaia", "caya", "kalla"}

# Alias secundarios / anteriores reconocidos
ALIAS_SECUNDARIOS = {
    "lyris", "liris", "lirys", "iris", "lyra", "liria", "viris", "silvestra", "silvestre"
}

# Palabras que invalidan "calla" o "calle" cuando se usan como forma verbal o sustantivo ("la calle", "en la calle")
_PREFIJOS_CALLA_VERBAL = {
    "se", "no", "te", "me", "que", "ni", "le", "nos", "os", "la", "lo", "si", "en", "por", "de", "una", "esa", "esta", "otra"
}

_PATRON_VOCATIVO_CALLA = re.compile(
    r"(?:^|\b(?:oye|hey|ey|hola|por\s+favor)\s+)(?:calla|calle)\b", re.IGNORECASE
)

_PATRON_ORDEN_TRAS_CALLA = re.compile(
    r"\b(?:calla|calle)\s*[,:]?\s*(?:que|dime|como|cuando|donde|cuanto|pon|abre|busca|para|reproduce|activa|desactiva|ayuda|cuenta|explica|puedes|revisa)\b",
    re.IGNORECASE,
)

_SEPARADOR = re.compile(r"[^\wáéíóúñü]+", re.UNICODE)


def normalizar_palabra(palabra):
    txt = unicodedata.normalize("NFKD", str(palabra or "").strip().lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


def palabras(texto):
    return [p for p in _SEPARADOR.split(str(texto or "").lower()) if p]


def es_calla_vocativo(texto, indice_palabra=None, lista_palabras=None):
    """Determina si 'calla' o 'calle' se usa como vocativo y no como verbo o sustantivo."""
    raw = str(texto or "").strip()
    ps = lista_palabras if lista_palabras is not None else palabras(raw)
    if not ps:
        return False

    indices = [i for i, p in enumerate(ps) if normalizar_palabra(p) in {"calla", "calle"}]
    if not indices:
        return False

    idx = indice_palabra if indice_palabra is not None else indices[0]
    if idx >= len(ps) or normalizar_palabra(ps[idx]) not in {"calla", "calle"}:
        return False

    # Si está precedido por artículos, preposiciones o pronombres ("la calle", "en la calle", "se calla") -> rechazar
    if idx > 0:
        prev = normalizar_palabra(ps[idx - 1])
        if prev in _PREFIJOS_CALLA_VERBAL:
            return False

    # Si es la única palabra ("Calla." / "Calle.") -> vocativo válido
    if len(ps) == 1:
        return True

    # Si está al inicio ("Calla, qué hora es" / "Calle, ¿puedes revisar...")
    if idx == 0:
        return True

    # Si está precedido por saludo/llamado ("Oye calla", "Oye calle", "Hey calle")
    if idx > 0 and normalizar_palabra(ps[idx - 1]) in {"oye", "hey", "ey", "hola"}:
        return True

    # Si sigue una orden explícita o interrogación
    if _PATRON_ORDEN_TRAS_CALLA.search(raw):
        return True

    return False


def detectar_invocacion(texto):
    """Detecta si el texto invoca a Kaya, devolviendo (detectado, alias_encontrado, orden_extraida)."""
    raw = str(texto or "").strip()
    if not raw:
        return False, "", ""

    ps = palabras(raw)
    if not ps:
        return False, "", ""

    # 1. Alias directos de Kaya en cualquier parte
    for i, p in enumerate(ps):
        p_norm = normalizar_palabra(p)
        if p_norm in ALIAS_DIRECTOS:
            orden = _extraer_orden(ps, i)
            return True, p_norm, orden

    # 2. 'calla' o 'calle' SOLO como vocativo
    for i, p in enumerate(ps):
        p_norm = normalizar_palabra(p)
        if p_norm in {"calla", "calle"} and es_calla_vocativo(raw, i, ps):
            orden = _extraer_orden(ps, i)
            return True, p_norm, orden

    # 3. Alias secundarios / legado
    for i, p in enumerate(ps):
        p_norm = normalizar_palabra(p)
        if p_norm in ALIAS_SECUNDARIOS:
            orden = _extraer_orden(ps, i)
            return True, p_norm, orden

    return False, "", ""


# Palabras finales colgantes que evidencian una frase cortada o incompleta
TERMINACIONES_TRUNCADAS = {
    "mi", "tu", "su", "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "con", "por", "para", "a", "al", "que", "y", "o"
}


def es_frase_truncada(texto):
    """Devuelve True si la frase termina abruptamente en posesivo, artículo o preposición."""
    txt = str(texto or "").strip().rstrip(".?!,:;")
    if not txt:
        return False
    ps = [p for p in re.split(r"[^\wáéíóúñü]+", txt.lower()) if p]
    if not ps:
        return False
    ultima = normalizar_palabra(ps[-1])
    return ultima in TERMINACIONES_TRUNCADAS


def _extraer_orden(ps, indice):
    relleno = {"oye", "oiga", "hola", "hey", "ey", "bueno", "pues", "entonces", "por", "favor"}
    todos_alias = ALIAS_DIRECTOS | ALIAS_SECUNDARIOS | {"calla", "calle"}
    antes = [p for p in ps[:indice] if normalizar_palabra(p) not in todos_alias]
    despues = [p for p in ps[indice + 1:] if normalizar_palabra(p) not in todos_alias]
    while antes and normalizar_palabra(antes[0]) in relleno:
        antes.pop(0)
    while despues and normalizar_palabra(despues[0]) in relleno:
        despues.pop(0)
    return " ".join(despues if despues else antes).strip()


# Candidatas para Vosk (small-es vocabulario real)
CANDIDATAS_VOSK_KAYA = [
    "calla", "calle", "caia", "callas", "callar",
    "iris", "lira", "liras", "lirio", "lirios", "liria", "lyra",
    "silvestre", "silvia", "silvio", "silba", "sil", "estra"
]
