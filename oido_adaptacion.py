"""Capa de adaptación fonética y detección de transcripciones sospechosas para habla relajada."""
import json
import os
import re
import threading

RUTA_DICCIONARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diccionario_fonetico.json")

# Reglas fonéticas base: deformaciones comunes cuando el usuario habla rápido o relajado
PATRONES_FONETICOS = [
    # "revisa / puedes revisar estoy en mi compu/computador" -> "el estado de mi computador"
    (
        re.compile(
            r"\b(revisa|revisar|puedes revisar|mira|ver|como esta)\s+(?:que\s+)?estoy\s+en\s+mi\s+(compu|computador|computadora|laptop|pc)\b",
            re.IGNORECASE,
        ),
        r"\1 el estado de mi \2",
    ),
    # "¿Me puedes revisar? Estoy en mi computador..." -> "¿Puedes revisar el estado de mi computador..."
    (
        re.compile(
            r"\bme\s+puedes\s+revisar\s*[,?]?\s*estoy\s+en\s+mi\s+(compu|computador|computadora|laptop|pc)\b",
            re.IGNORECASE,
        ),
        r"puedes revisar el estado de mi \1",
    ),
    # "revisa en mi compu" -> "revisa mi compu"
    (
        re.compile(
            r"\b(revisa|mira|chequea)\s+en\s+mi\s+(compu|computador|computadora|laptop|pc)\b",
            re.IGNORECASE,
        ),
        r"\1 el estado de mi \2",
    ),
]

_bloqueo = threading.RLock()
_cache_diccionario = None


def cargar_diccionario_personal():
    """Carga diccionario JSON personal extensible si existe en disco."""
    global _cache_diccionario
    with _bloqueo:
        if _cache_diccionario is not None:
            return _cache_diccionario
        if os.path.exists(RUTA_DICCIONARIO):
            try:
                with open(RUTA_DICCIONARIO, "r", encoding="utf-8") as f:
                    _cache_diccionario = json.load(f)
                    return _cache_diccionario
            except Exception:
                pass
        _cache_diccionario = {}
        return _cache_diccionario


def adaptar_texto_fonetico(texto):
    """Aplica adaptaciones fonéticas inteligentes preservando frases casuales normales."""
    t = str(texto or "").strip()
    if not t:
        return ""

    # 1. Reglas regex contextuales
    for patron, reemplazo in PATRONES_FONETICOS:
        t = patron.sub(reemplazo, t)

    # 2. Diccionario personal extensible
    dic = cargar_diccionario_personal()
    if dic and isinstance(dic, dict):
        for origen, destino in dic.items():
            if origen and destino:
                p_exacta = re.compile(r"\b" + re.escape(origen) + r"\b", re.IGNORECASE)
                t = p_exacta.sub(destino, t)

    return " ".join(t.split())


def es_transcripcion_sospechosa(texto, confidence=1.0, duracion_seg=0.0):
    """Solo marca una transcripción Deepgram como sospechosa si no hay texto
    o la confianza es menor que 0.85.

    La duración y las frases incompletas ya no fuerzan Whisper: el streaming
    de Nova-3 resuelve esos casos sin el costo del respaldo (~2.5 s).
    ``duracion_seg`` se conserva por compatibilidad de firma.
    """
    txt = str(texto or "").strip()
    if not txt:
        return True
    try:
        conf = 1.0 if confidence is None else float(confidence)
    except (TypeError, ValueError):
        conf = 1.0
    return conf < 0.85
