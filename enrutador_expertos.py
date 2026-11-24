"""Enrutador de Cerebro Dual y Cartuchos de Especialistas modulares para Lyris.

Clasifica consultas en < 10 ms (léxico/regex puro) a carril 'rapido' o 'pesado',
e inyecta cartuchos especializados de programación o matemáticas solo cuando corresponde.
"""
import re
import unicodedata
from expertos import obtener_cartucho

# Patrones para programación / arquitectura / software
_PATRON_PROGRAMACION = re.compile(
    r"\b(def\b|class\b|import\b|function\b|const\b|var\b|let\b|select\b|from\b|"
    r"where\b|```|<html>|<\?php|==|!=|=>|->|\.py\b|\.js\b|\.html\b|\.json\b|"
    r"error\b|traceback\b|excepcion\b|exception\b|bug\b|debugging\b|debug\b|"
    r"refactorizar\b|optimizacion\b|optimizaci[oó]n\b|optimizar\b|optimizo\b|"
    r"algoritmo\b|algoritmos\b|codigo\b|c[oó]digo\b|script\b|python\b|javascript\b|typescript\b|"
    r"c\+\+\b|rust\b|sql\b|base de datos\b|diccionario\b|array\b|bucle\b|quicksort\b|mergesort\b|"
    r"complejidad\b|compilacion\b|compilar\b|backend\b|frontend\b|endpoint\b|docker\b|"
    r"pull request\b|git status\b|commit\b|concurrencia\b|asincrono\b|as[ií]ncrono\b)",
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
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
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

    # 1. Chequeo de Matemáticas
    if _PATRON_MATEMATICAS.search(t_orig) or _PATRON_MATEMATICAS.search(t_norm):
        return {
            "area": "matematicas",
            "carril": "pesado",
            "prompt_experto": obtener_cartucho("matematicas"),
        }

    # 2. Chequeo de Programación
    if _PATRON_PROGRAMACION.search(t_orig) or _PATRON_PROGRAMACION.search(t_norm):
        return {
            "area": "programacion",
            "carril": "pesado",
            "prompt_experto": obtener_cartucho("programacion"),
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
