"""Filtro de calidad, privacidad y desduplicación para la memoria permanente."""
import re
import unicodedata

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "con",
    "por", "para", "que", "se", "su", "sus", "es", "son", "fue", "y", "o", "pero", "como", "le",
    "les", "lo", "me", "te", "nos", "mi", "mis", "tu", "tus", "suya", "suyo", "este", "esta",
    "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella", "usuario", "moises",
    "silvestra", "asistente", "esta", "estan", "estudiando", "repasando", "tiene", "tienen",
    "gusta", "interesa", "tambien"
}

PALABRAS_PRIVADAS = (
    "clave", "password", "contraseñ", "contrasena", "token", "api_key",
    "apikey", "secret", "cvv", "tarjeta de credito", "pin "
)

PATRONES_META_NORMALIZADOS = [
    r"^\s*none\s*$",
    r"^\s*null\s*$",
    r"^\s*ningun[oa]\s*$",
    r"recordatorio\s*\|",
    r"accion\s*:\s*",
    r"respuesta\s*:\s*",
    r"\bhud\b",
    r"asistente\s+virtual",
    r"interfaz\s+de\s+usuario",
    r"proveedor(es)?(\s+de\s+ia)?",
    r"camara\s+(de\s+su\s+dispositivo|del\s+dispositivo)",
    r"desactivar\s+la\s+camara",
    r"tomar\s+una\s+foto",
    r"pedir\s+una\s+foto|pidio\s+una\s+foto",
    r"se\s+trabo\s+o\s+fallo",
    r"herramientas\s+virtuales",
    r"interactuo\s+con\s+(un[a]?\s+)?asistente",
    r"parece\s+tener\s+interes",
    r"parece\s+tener\s+una\s+rutina",
    r"lo\s+que\s+(sugiere|indica|podria\s+indicar)",
    r"muestra\s+resistencia",
    r"100\s+meses\s+y\s+necesita",
    r"niega\s+haber\s+pedido",
    r"\b(?:esta|estoy)\s+usando\s+(?:visual\s+studio\s+code|vs\s+code|vscode|antigravity\s+ide|chrome|google\s+chrome|microsoft\s+edge|edge|chatgpt|claude)\b",
    r"\b(?:tiene|tengo)\s+(?:abierto|abierta)\s+(?:el\s+|la\s+)?(?:archivo|ventana|aplicacion|app)\b",
    r"\b(?:archivo|ventana)\s+[\w.-]+\s+(?:abierto|abierta)\b",
    r"registre\s+el\s+tiempo\s+de\s+inicio",
    r"cerrar\s+programas",
    r"mejorar\s+mi\s+codigo",
    r"^\s*el\s+usuario\s+se\s+llama\s+moises\.?\s*$",
    r"\b(y|de|con|en|llamado|llamada)\s*$"
]


def normalizar_para_filtro(texto):
    """Convierte a minúsculas y remueve acentos para comparación tolerante."""
    if not texto:
        return ""
    t = re.sub(r"^\[[^\]]+\]\s*", "", texto).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def palabras_clave(texto):
    """Extrae conjunto de palabras significativas para comparar similitud."""
    t_norm = normalizar_para_filtro(texto)
    palabras = set(re.findall(r"\b[a-z]{3,}\b", t_norm))
    return palabras - STOPWORDS


def es_recuerdo_valido(hecho):
    """Valida que el hecho sea un dato concreto sobre el dueño y no basura meta ni privada."""
    if not hecho or not isinstance(hecho, str):
        return False, "vacío"

    limpio = re.sub(r"^\[[^\]]+\]\s*", "", hecho).strip()
    if len(limpio) < 12:
        return False, "demasiado corto"

    limpio_low = limpio.lower()
    for p in PALABRAS_PRIVADAS:
        if p in limpio_low:
            return False, f"privacidad: {p}"

    norm = normalizar_para_filtro(limpio)
    for pat in PATRONES_META_NORMALIZADOS:
        if re.search(pat, norm):
            return False, f"patrón meta: {pat}"

    return True, ""


def es_duplicado(nuevo_hecho, hechos_existentes):
    """Detecta duplicados exactos o semánticamente casi idénticos con alta coincidencia de palabras."""
    if not nuevo_hecho or not hechos_existentes:
        return False

    norm_nuevo = normalizar_para_filtro(nuevo_hecho)
    pk_nuevo = palabras_clave(nuevo_hecho)

    for existente in hechos_existentes:
        norm_existente = normalizar_para_filtro(existente)
        if norm_nuevo == norm_existente:
            return True

        pk_existente = palabras_clave(existente)
        if not pk_nuevo or not pk_existente:
            continue

        inter = len(pk_nuevo & pk_existente)
        union = len(pk_nuevo | pk_existente)
        sim_jaccard = inter / union
        sim_min = inter / min(len(pk_nuevo), len(pk_existente))

        # Coincidencia semántica por vocabulario
        if sim_jaccard >= 0.40 or (sim_min >= 0.50 and inter >= 3) or inter >= 4:
            return True

    return False
