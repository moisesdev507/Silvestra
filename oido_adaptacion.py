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
    """Detecta si una transcripción de Deepgram parece rota, inconexa o tiene baja confianza.
    
    Permite gatillar el respaldo de Groq Whisper antes de despachar.
    """
    txt = str(texto or "").strip()
    if not txt:
        return True

    # 1. Confianza numérica baja reportada por Deepgram
    if confidence is not None and 0.0 < float(confidence) < 0.62:
        return True

    ps = txt.split()
    conf = float(confidence) if confidence is not None else 1.0

    # 2. Incoherencia de longitud: audio largo (> 3.5s) pero apenas 1-2 palabras transcritas.
    # Si la confianza es alta (>= 0.92) y no tiene tokens anómalos, se preserva para evitar ~2.5s de Whisper.
    if duracion_seg and duracion_seg >= 3.5 and len(ps) <= 2:
        if conf >= 0.92 and not any(len(p) == 1 and p not in ("y", "o", "a", "e", "u") for p in ps):
            pass
        else:
            return True

    # 3. Preguntas rotas o truncadas que terminan en preposición / conector sin sentido
    t_low = txt.lower().rstrip("?.!,:;")
    if any(t_low.endswith(x) for x in (" en", " de", " mi", " por", " para", " con", " el", " la")):
        return True

    return False
