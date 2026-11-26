"""Embeddings de Gemini por REST con caché LRU y respaldo entre modelos.

Capa aislada para que memoria_semantica pueda permanecer por debajo de 10 KB.
La clave se lee de config (API histórica); GEMINI_API_KEY se decide arriba.
"""
import json
import urllib.request
from collections import OrderedDict

MODELOS_EMBEDDING = ("gemini-embedding-001", "text-embedding-004")
DIMENSION_DEFAULT = 768
MAX_CACHE = 32
_CACHE = OrderedDict()


def _clave():
    try:
        import config
        for nombre in ("CLAVE_GOOGLE", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
            valor = str(getattr(config, nombre, "") or "").strip()
            if valor:
                return valor
    except Exception:
        pass
    return ""


def obtener_embedding(texto, tipo_tarea="RETRIEVAL_DOCUMENT"):
    """Devuelve la lista de floats o None si no hay clave o falla la red."""
    t = " ".join(str(texto or "").split()).strip()
    if not t:
        return None
    clave_cache = (t, tipo_tarea)
    if clave_cache in _CACHE:
        _CACHE.move_to_end(clave_cache)
        return list(_CACHE[clave_cache])
    clave = _clave()
    if not clave:
        return None
    for mod in MODELOS_EMBEDDING:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{mod}"
               f":embedContent?key={clave}")
        payload = {"model": f"models/{mod}", "content": {"parts": [{"text": t}]},
                   "taskType": tipo_tarea, "outputDimensionality": DIMENSION_DEFAULT}
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
            vec = datos.get("embedding", {}).get("values")
            if vec and isinstance(vec, list):
                valores = [float(x) for x in vec]
                _CACHE[clave_cache] = valores
                if len(_CACHE) > MAX_CACHE:
                    _CACHE.popitem(last=False)
                return valores
        except Exception:
            continue
    return None


__all__ = ["obtener_embedding", "MODELOS_EMBEDDING", "DIMENSION_DEFAULT"]
