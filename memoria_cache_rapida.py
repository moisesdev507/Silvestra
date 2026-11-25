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


def ejecutar_con_limite_tiempo(extractor_fn, timeout_seg=0.25):
    """Ejecuta una función en hilo daemon para evitar que bloquee el turno conversacional si se cuelga."""
    caja = [None]
    listo = threading.Event()

    def _tarea():
        try:
            caja[0] = extractor_fn()
        except Exception:
            pass
        finally:
            listo.set()

    hilo = threading.Thread(target=_tarea, daemon=True)
    hilo.start()
    if listo.wait(timeout=timeout_seg):
        return caja[0]
    return None


def obtener_contexto_rapido(consulta, extractor_fn, clave_tipo="mem_pers", timeout_seg=0.35):
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

    # Si no está o expiró, ejecuta extractor protegido por timeout
    resultado = ejecutar_con_limite_tiempo(extractor_fn, timeout_seg=timeout_seg)
    if resultado is not None:
        with _bloqueo:
            _cache_datos[clave] = (resultado, ahora + _TTL_SEGUNDOS, _version_recuerdos)
            if len(_cache_datos) > 120:
                _cache_datos.pop(next(iter(_cache_datos)))

    return resultado or ""


def es_seguimiento_o_frase_corta(texto):
    """Detecta frases cotidianas breves o de seguimiento que no requieren RAG ni búsqueda de recuerdos."""
    t = str(texto or "").strip().lower()
    if not t:
        return True
    try:
        import cerebro_perfil
        if cerebro_perfil.es_frase_ultrarrapida(t):
            return True
    except Exception:
        pass
    # Frases conversacionales cortas que son meros acuses de recibo
    acuses = {"ok", "vale", "listo", "gracias", "de acuerdo", "bien", "dale", "sipi", "nop"}
    if t in acuses:
        return True
    return False
