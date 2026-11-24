"""Caché ligera en memoria para acelerar el tramo de memoria pre-LLM (< 80 ms)."""
import threading
import time

_TTL_SEGUNDOS = 30.0
_bloqueo = threading.RLock()
_cache_datos = {}
_version_recuerdos = 0


def invalidar_recuerdos():
    """Se llama cada vez que se escribe, modifica o elimina un recuerdo."""
    global _version_recuerdos
    with _bloqueo:
        _version_recuerdos += 1
        _cache_datos.clear()


def obtener_contexto_rapido(consulta, extractor_fn, clave_tipo="mem_pers"):
    """Devuelve resultado en caché si no ha expirado y no se han escrito recuerdos nuevos."""
    c_limpia = str(consulta or "").strip().lower()
    clave = (clave_tipo, c_limpia)
    ahora = time.monotonic()

    with _bloqueo:
        item = _cache_datos.get(clave)
        if item:
            val, exp, ver = item
            if ahora < exp and ver == _version_recuerdos:
                return val

    # Si no está o expiró, ejecuta extractor
    resultado = extractor_fn()
    with _bloqueo:
        _cache_datos[clave] = (resultado, ahora + _TTL_SEGUNDOS, _version_recuerdos)
        # Limpieza simple si la caché supera 120 elementos
        if len(_cache_datos) > 120:
            _cache_datos.pop(next(iter(_cache_datos)))

    return resultado


def es_seguimiento_o_frase_corta(texto):
    """Detecta frases de seguimiento o acuses cotidianos que no piden buscar en el pasado."""
    t = str(texto or "").strip().lower()
    if not t or len(t) <= 28:
        # Palabras que explícitamente piden indagar en memoria pasada o tareas
        palabras_historia = (
            "recuerda", "recuerdas", "guarda", "anota", "que sabes",
            "que tengo", "cuando", "donde", "quien", "ayer", "semana pasada"
        )
        if not any(p in t for p in palabras_historia):
            return True
    return False
