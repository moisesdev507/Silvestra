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
    "autenticacion", "refresh token", "refresh tokens", "python",
    "javascript", "typescript", "api", "contrato", "seguridad",
}

# Señales semánticas fuertes. Se evalúan ANTES del atajo "comando cotidiano"
# para que un análisis/diseño/comparación corto no sea capturado como charla.
_TERMINOS_SEMANTICOS = (
    r"analiz(?:a|ar|ando|is|isis)",
    r"disen[ao]|dise[ñn](?:a|ar|o)",
    r"arquitectura",
    r"compar(?:a|ar|acion|acion)",
    r"pros\s+y\s+contras|ventajas\s+y\s+desventajas|diferencia\s+entre",
    r"depur(?:a|ar|acion)|debugg(?:ing|eo)?|debug(?:ging|ueo)?",
    r"program(?:a|ar|acion)|codig(?:o|os)|\bcode\b",
    r"python|javascript|typescript|\bsql\b|backend|frontend|algoritm(?:o|os)",
    r"refactoriz(?:a|ar|acion)|optimiz(?:a|ar|acion)",
    r"autenticac[ió]on|refresh\s+token",
    r"paso\s+a\s+paso|a\s+fondo|profundidad",
    r"razon(?:a|ar|amiento)|reflexion(?:a|ar)",
    r"\bdef\b|\bclass\b|\bimport\b|\bfunction\b|```|->|=>|==|!=",
    r"base\s+de\s+datos|concurrencia|asincrono|excepcion|traceback",
)
_PATRON_PRO_SEMANTICO = re.compile(
    r"(?<!\w)(?:" + "|".join(_TERMINOS_SEMANTICOS) + r")(?!\w)", re.I
)

_PATRON_RAZONAMIENTO = re.compile(
    r"\b(piensa|razona|analiza|reflexiona|detalla|explica a fondo|paso a paso|"
    r"por que|diferencia entre|compara|resuelve|calcula|algoritmo|complejidad|optimiza)\b",
    re.I,
)

_PATRON_CODIGO = re.compile(
    r"(\bdef\b|\bclass\b|\bimport\b|\bfunction\b|\bconst\b|\bvar\b|\blet\b|\bselect\b|\bfrom\b|"
    r"\bwhere\b|```|<html>|<\?php|==|!=|=>|->|\.py\b|\.js\b|\.html\b|\.json\b|\berror\b|"
    r"\btraceback\b|\bexcepcion\b|\bexception\b|\bbug\b)",
    re.I,
)

_PATRON_ENLACE = re.compile(r"https?://", re.I)


def normalizar_texto(texto):
    """Quita tildes y convierte a minúsculas antes de aplicar cualquier regla."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def clasificar_dificultad(texto):
    """Clasifica el mensaje en 'charla' o 'razonamiento' sin llamadas de red."""
    t = normalizar_texto(texto)
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

    # Análisis, diseño, arquitectura, comparación, depuración y código se
    # detectan por señal semántica, sin depender de la longitud del mensaje.
    if _PATRON_PRO_SEMANTICO.search(txt):
        return "pro", "consulta_compleja_tecnica"

    modo_tecnico = modo_activo in ("programacion", "estudio")
    if len(txt) < 80 and not modo_tecnico:
        return "rapido", "cotidiano_o_comando"

    if _PATRON_CODIGO.search(txt):
        return "pro", "codigo_detectado"

    palabras = set(re.findall(r"\b[a-z0-9_]{3,}\b", txt))
    tecnico = any(
        (t in txt if " " in t else t in palabras) for t in PALABRAS_TECNICAS_PRO
    )

    if tecnico and len(txt) >= 100:
        return "pro", "consulta_tecnica_detallada"

    if clasificar_dificultad(txt) == "razonamiento" and len(txt) >= 140:
        return "pro", "consulta_extensa"

    if modo_tecnico and len(txt) >= 50 and tecnico:
        return "pro", f"modo_{modo_activo}_tecnico"

    return "rapido", "general_o_cotidiano"


def es_prompt_complejo(texto, modo_activo="normal"):
    """True si el texto merece carril pro, exista o no una clave configurada."""
    carril, _ = decidir_carril(texto, modo_activo=modo_activo, pro_disponible=True)
    return carril == "pro"
