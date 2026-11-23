"""Fuente única de verdad para clasificar dificultad y decidir carril (rápido vs pro)."""
import re
import unicodedata

FRASES_EXPLICITAS_PRO = (
    "piensalo bien",
    "piensa bien",
    "analiza a fondo",
    "modo pro",
    "en detalle",
    "explica a profundidad",
    "a profundidad",
    "profundidad",
    "analisis detallado",
    "analisis profundo",
    "razona a fondo",
    "piensa con calma",
)

PALABRAS_TECNICAS_PRO = {
    "codigo", "algoritmo", "arquitectura", "debugging", "debug",
    "refactorizar", "optimizacion", "base de datos", "sql", "backend",
    "frontend", "excepcion", "traceback", "concurrencia", "asincrono",
    "rendimiento", "negocio", "estrategia", "comparativa", "complejidad",
    "patron de diseno", "unit test", "endpoint", "pull request",
}

_PATRON_RAZONAMIENTO = re.compile(
    r"\b(piensa|razona|analiza|reflexiona|detalla|explica a fondo|paso a paso|"
    r"por qu[eé]|diferencia entre|compara|resuelve|calcula|algoritmo|complejidad|optimiza)\b",
    re.I,
)

_PATRON_CODIGO = re.compile(
    r"(\bdef\b|\bclass\b|\bimport\b|\bfunction\b|\bconst\b|\bvar\b|\blet\b|\bselect\b|\bfrom\b|"
    r"\bwhere\b|```|<html>|<\?php|==|!=|=>|->|\.py\b|\.js\b|\.html\b|\.json\b|\berror\b|"
    r"\btraceback\b|\bexcepci[oó]n\b|\bexception\b|\bbug\b)",
    re.I,
)

_PATRON_ENLACE = re.compile(r"https?://", re.I)


def normalizar_texto(texto):
    """Quita tildes y convierte a minúsculas para comparaciones semánticas."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def clasificar_dificultad(texto):
    """Clasifica el mensaje en 'charla' o 'razonamiento' sin llamadas de red."""
    if not texto or not isinstance(texto, str):
        return "charla"
    t = texto.strip()
    if not t:
        return "charla"
    if (
        _PATRON_ENLACE.search(t)
        or _PATRON_CODIGO.search(t)
        or _PATRON_RAZONAMIENTO.search(t)
        or len(t) > 140
    ):
        return "razonamiento"
    return "charla"


def decidir_carril(texto, modo_activo="normal", pro_disponible=False):
    """Decide 'rapido' o 'pro' de forma determinista (< 1 ms).

    Retorna (carril, motivo) para telemetría. Sin proveedor Pro configurado
    siempre devuelve 'rapido' con motivo 'sin_pro_configurado'.
    """
    if not pro_disponible:
        return "rapido", "sin_pro_configurado"

    txt = normalizar_texto(texto)
    if not txt:
        return "rapido", "texto_vacio"

    for frase in FRASES_EXPLICITAS_PRO:
        if frase in txt:
            return "pro", "solicitud_explicita_usuario"

    longitud = len(txt)
    modo_tecnico = modo_activo in ("programacion", "estudio")

    if longitud < 80 and not modo_tecnico:
        return "rapido", "cotidiano_o_comando"

    palabras = set(re.findall(r"\b[a-z0-9_]{3,}\b", txt))
    tecnico = any(
        (t in txt if " " in t else t in palabras) for t in PALABRAS_TECNICAS_PRO
    )

    if _PATRON_CODIGO.search(txt) and longitud >= 60:
        return "pro", "codigo_detectado"

    if tecnico and longitud >= 120:
        return "pro", "consulta_compleja_tecnica"

    if clasificar_dificultad(txt) == "razonamiento" and longitud >= 140:
        return "pro", "consulta_extensa"

    if modo_tecnico and longitud >= 50 and tecnico:
        return "pro", f"modo_{modo_activo}_tecnico"

    return "rapido", "general_o_cotidiano"


def es_prompt_complejo(texto, modo_activo="normal"):
    """True si el texto merece carril pro, exista o no una clave configurada."""
    carril, _ = decidir_carril(texto, modo_activo=modo_activo, pro_disponible=True)
    return carril == "pro"
