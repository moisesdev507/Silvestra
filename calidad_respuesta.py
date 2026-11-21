"""Control de calidad y validación lingüística de respuestas en español."""
import re
import unicodedata

# Palabras funcionales y gramaticales esenciales del español
PALABRAS_ESENCIALES_ESPANOL = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "al", "del",
    "de", "en", "a", "para", "por", "con", "sin", "sobre", "hacia", "hasta",
    "y", "e", "ni", "o", "u", "pero", "sino", "aunque", "que", "si", "ya",
    "no", "bien", "mal", "muy", "mas", "menos", "tan", "tanto", "asi",
    "yo", "tu", "el", "ella", "nosotros", "nosotras", "usted", "ustedes", "ellos", "ellas",
    "me", "te", "se", "nos", "le", "les", "mi", "su", "sus", "nuestro", "nuestra",
    "es", "son", "era", "fue", "ser", "esta", "estan", "estoy", "ha", "hay", "he", "hemos", "han",
    "aqui", "ahi", "alli", "alla", "como", "donde", "cuando", "cual", "quien",
    "hola", "buenos", "dias", "tardes", "noches", "gracias", "adios", "chao",
    "papi", "mami", "amigo", "amiga", "moises", "silvestra", "listo", "lista", "claro",
    "solo", "todo", "toda", "todos", "todas", "nada", "poco", "mucho", "mucha", "bueno", "buena",
    "python", "whisper", "youtube", "laptop", "pc", "script", "ia", "app", "codigo", "modelo",
}

_PATRONES_CORRUPTOS = (
    re.compile(r"q[^ueei]", re.I),
    re.compile(r"mpun$", re.I),
    re.compile(r"ncoy$", re.I),
    re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}", re.I),
)

_CONECTORES_COLGANTES = {
    "de", "del", "en", "que", "y", "e", "o", "u", "a", "al", "con", "por",
    "para", "el", "la", "los", "las", "un", "una", "unos", "unas", "su", "sus",
    "mi", "mis", "tu", "tus", "sin", "sobre", "tras", "hacia", "hasta", "como",
}


def _normalizar_token(token):
    limpio = token.lower().strip("¿?¡!.,;:\"'()[]{}«»*`-_")
    if not limpio:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", limpio) if unicodedata.category(c) != "Mn")


def es_token_corrupto(token):
    """Detecta tokens con secuencias alfabéticas que violan la fonotáctica del español."""
    norm = _normalizar_token(token)
    if not norm or norm.isdigit() or len(norm) <= 2:
        return False
    if norm in PALABRAS_ESENCIALES_ESPANOL:
        return False
    # Una palabra de más de 2 letras en español debe contener al menos una vocal
    if not any(c in "aeiouy" for c in norm):
        return True
    for pat in _PATRONES_CORRUPTOS:
        if pat.search(norm):
            return True
    return False


def _tokens_contexto_windows(contexto):
    if isinstance(contexto, (list, tuple)):
        textos = [str(m.get("content", "")) for m in contexto
            if isinstance(m, dict) and m.get("role") == "system"]
    else:
        textos = [str(contexto or "")]
    tokens = set()
    for texto in textos:
        for inicio in re.finditer(r"(?im)^Aplicación activa en Windows:", texto):
            resto = texto[inicio.start():]
            fin = re.search(r"(?im)^\s*(?:Perfil del usuario|Correcciones aplicadas):", resto)
            bloque = resto[:fin.start()] if fin else resto
            tokens.update(_normalizar_token(p) for p in
                re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+", bloque))
    return tokens


def _es_fuga_identidad(texto):
    normal = " ".join(_normalizar_token(p) for p in
        re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+", texto))
    marcas = r"chatgpt|claude|openai|anthropic|gemini"
    return bool(re.search(rf"\bsoy\s+(?:(?:un|una|el|la)\s+)?(?:(?:modelo|asistente)\s+de\s+)?(?:{marcas})\b", normal)
        or re.search(rf"\bcomo\s+(?:un\s+)?modelo\s+de\s+(?:{marcas})\b", normal))


def analizar_calidad_texto(texto, contexto_windows=None):
    """Evalúa la completitud, ausencia de texto cortado y coherencia en español.

    Devuelve: (es_valido, motivo)
    """
    if not texto or not isinstance(texto, str):
        return False, "texto_vacio"

    t = texto.strip()
    if _es_fuga_identidad(t):
        return False, "identidad_proveedor_modelo"
    if len(t) < 4:
        return False, "demasiado_corto"

    palabras = [w for w in re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9]+", t) if len(w) > 0]
    if not palabras:
        return False, "sin_palabras"

    # Verificar si quedó truncado con un conector colgante al final sin puntuación
    ultima_palabra = palabras[-1].lower()
    ultimo_char = t[-1]
    if ultimo_char not in ".!?…\"'»)" and ultima_palabra in _CONECTORES_COLGANTES:
        return False, f"truncado_en_conector('{ultima_palabra}')"

    # Detección de palabras fonotácticamente corruptas o imposibles en español
    permitidas = _tokens_contexto_windows(contexto_windows)
    corruptas = [p for p in palabras if _normalizar_token(p) not in permitidas
                 and es_token_corrupto(p)]
    if corruptas:
        return False, f"token_corrupto({corruptas[:2]})"

    # Una frase o respuesta en español de 4 o más palabras debe tener conectores/palabras gramaticales
    norm_palabras = [_normalizar_token(p) for p in palabras]
    n_esenciales = sum(1 for p in norm_palabras if p in PALABRAS_ESENCIALES_ESPANOL)
    if len(palabras) >= 4 and n_esenciales == 0:
        return False, "sin_palabras_gramaticales_espanol"

    return True, "ok"


def es_frase_valida(frase):
    """Validador ágil de cada frase individual durante el streaming."""
    if not frase or len(frase.strip()) < 3:
        return False
    ok, _ = analizar_calidad_texto(frase)
    return ok


def es_respuesta_valida(respuesta):
    """Validador final de la respuesta completa devuelta por el modelo."""
    ok, _ = analizar_calidad_texto(respuesta)
    return ok
