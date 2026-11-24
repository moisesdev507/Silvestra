"""Enrutador de Cerebro Dual y Cartuchos de Especialistas modulares para Lyris.

Clasifica consultas en < 10 ms (léxico/regex puro) a carril 'rapido' o 'pesado',
e inyecta cartuchos especializados de programación o matemáticas solo cuando corresponde.
"""
import re
import unicodedata
from expertos import obtener_cartucho

# Patrones para programación / arquitectura / software
# Notar límites especiales (?<!\w) y (?!\w) para lenguajes con símbolos como C++ y C#
_PATRON_PROGRAMACION = re.compile(
    r"(?<!\w)(?:c\+\+|c#)(?!\w)|\b("
    r"def|class|import|function|const|var|let|select|from|where|"
    r"```|<html>|<\?php|==|!=|=>|->|\.py|\.js|\.html|\.json|"
    r"error|traceback|excepcion|excepci[oó]n|exception|bug|debugging|debug|"
    r"refactorizar|optimizacion|optimizaci[oó]n|optimizar|optimizo|"
    r"algoritmo|algoritmos|codigo|c[oó]digo|script|python|javascript|typescript|"
    r"rust|sql|base de datos|diccionario|array|bucle|quicksort|mergesort|"
    r"complejidad|compilacion|compilaci[oó]n|compilar|compilador|"
    r"backend|frontend|endpoint|docker|pull request|git status|commit|"
    r"concurrencia|asincrono|as[ií]ncrono|"
    r"puntero|punteros|referencia|arreglo|arreglos|vector|vectores|struct|"
    r"scanf|printf|malloc|segfault|recursividad|recursivo|herencia|repositorio|"
    r"git|consulta sql|supabase|api|variable|funcion|funci[oó]n)\b",
    re.I,
)

# Patrones para matemáticas / cálculo / álgebra
_PATRON_MATEMATICAS = re.compile(
    r"\b(derivada\b|derivadas\b|integral\b|integrales\b|matriz\b|matrices\b|"
    r"vector\b|vectores\b|[aá]lgebra\b|calculo\b|c[aá]lculo\b|teorema\b|"
    r"probabilidad\b|estadistica\b|estad[ií]stica\b|demuestra\b|demostracion\b|"
    r"demostraci[oó]n\b|ecuacion\b|ecuaci[oó]n\b|polinomio\b|limite\b|l[ií]mite\b|"
    r"trigonometr[ií]a\b|logaritmo\b|seno\b|coseno\b|tangente\b|eigenvalor\b|"
    r"eigenvector\b|determinante\b|fraccion\b|fracci[oó]n\b)",
    re.I,
)

# Patrones de razonamiento pesado
_PATRON_RAZONAMIENTO_PESADO = re.compile(
    r"\b(analiza a fondo\b|paso a paso\b|compara a fondo\b|demuestra que\b|"
    r"analisis profundo\b|an[aá]lisis detallado\b|razona a fondo\b|explica a profundidad\b)",
    re.I,
)

MODELOS_PESADOS_DEFAULT = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]

MODELO_RAPIDO_DEFAULT = "llama-3.1-8b-instant"


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def clasificar_consulta(texto: str) -> dict:
    """Clasifica en < 10ms la consulta para determinar área, carril y prompt experto."""
    t_orig = str(texto or "").strip()
    if not t_orig:
        return {"area": "general", "carril": "rapido", "prompt_experto": ""}

    t_norm = _norm(t_orig)

    es_prog = bool(_PATRON_PROGRAMACION.search(t_orig) or _PATRON_PROGRAMACION.search(t_norm))
    es_mat = bool(_PATRON_MATEMATICAS.search(t_orig) or _PATRON_MATEMATICAS.search(t_norm))

    # 1. Si hay términos explícitos de cálculo o álgebra (derivada, integral, matriz, ecuación),
    # o si es puramente matemática, clasificar en matemáticas
    if es_mat and not (
        re.search(r"(?<!\w)(?:c\+\+|c#)(?!\w)|\b(python|javascript|typescript|c[oó]digo|codigo|script|sql|scanf|printf|malloc|struct|puntero|punteros|def|class|git)\b", t_orig, re.I)
    ):
        return {
            "area": "matematicas",
            "carril": "pesado",
            "prompt_experto": obtener_cartucho("matematicas"),
        }

    # 2. Si contiene términos de programación, clasificar en programación
    if es_prog:
        return {
            "area": "programacion",
            "carril": "pesado",
            "prompt_experto": obtener_cartucho("programacion"),
        }

    # 3. Resto de casos matemáticos
    if es_mat:
        return {
            "area": "matematicas",
            "carril": "pesado",
            "prompt_experto": obtener_cartucho("matematicas"),
        }

    # 3. Razonamiento analítico pesado general
    if _PATRON_RAZONAMIENTO_PESADO.search(t_orig) or _PATRON_RAZONAMIENTO_PESADO.search(t_norm):
        return {
            "area": "general",
            "carril": "pesado",
            "prompt_experto": "",
        }

    return {
        "area": "general",
        "carril": "rapido",
        "prompt_experto": "",
    }


def seleccionar_modelo_experto(config_mod, carril: str) -> list[str]:
    """Retorna la cadena ordenada de modelos según el carril (pesado vs rápido)."""
    # Modelo rápido base
    rapido = getattr(config_mod, "MODELO_RAPIDO", "") or MODELO_RAPIDO_DEFAULT

    if carril != "pesado":
        return [rapido]

    candidatos = []
    # Revisar configuraciones personalizadas en config
    cfg_pesado = getattr(config_mod, "MODELO_PESADO", "")
    if cfg_pesado and isinstance(cfg_pesado, str) and cfg_pesado not in candidatos:
        candidatos.append(cfg_pesado)

    cfg_expertos = getattr(config_mod, "MODELOS_EXPERTO", None)
    if isinstance(cfg_expertos, (list, tuple)):
        for m in cfg_expertos:
            if isinstance(m, str) and m not in candidatos:
                candidatos.append(m)

    for m_def in MODELOS_PESADOS_DEFAULT:
        if m_def not in candidatos:
            candidatos.append(m_def)

    # El modelo rápido siempre queda al final como fallback de seguridad
    if rapido not in candidatos:
        candidatos.append(rapido)

    return candidatos


__all__ = ["clasificar_consulta", "seleccionar_modelo_experto", "MODELOS_PESADOS_DEFAULT", "MODELO_RAPIDO_DEFAULT"]
