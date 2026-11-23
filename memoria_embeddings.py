"""Embeddings ligeros: Cohere online, feature-hashing offline y caché LRU.

Nunca imprime claves ni respuestas. El fallback es determinista (BLAKE2b)
para que los tests sean reproducibles sin red.
"""
import hashlib
import os
import re
import struct
import threading
import unicodedata
from collections import OrderedDict

import numpy as np

try:
    import config as _config
except Exception:
    _config = None

try:
    import requests as _requests
except Exception:
    _requests = None


MODELO = "embed-english-v3.0"
URL = "https://api.cohere.ai/v1/embed"
DIM_FALLBACK = 64
MAX_CACHE = 512
TIMEOUT = 1.0
TIPO_FALLBACK = 0
TIPO_API = 1

SINONIMOS = {
    "arreglar": ("solucionar", "reparar", "corregir"),
    "solucion": ("arreglo", "reparacion", "solucionar"),
    "error": ("problema", "falla", "fallo", "averia"),
    "averia": ("error", "fallo", "problema"),
    "trabajo": ("empleo", "labor", "proyecto"),
    "gustar": ("preferir", "encantar"),
    "decidir": ("acordar", "resolver", "elegir"),
    "problema": ("error", "fallo", "incidente"),
    "meta": ("objetivo", "plan", "proposito"),
    "comida": ("alimento", "plato", "comer"),
    "comprar": ("adquirir", "pedido"),
    "estudiar": ("aprender", "curso", "estudio"),
    "despliegue": ("desplegado", "desplegar", "deploy", "implementacion"),
    "desplegado": ("despliegue", "desplegar", "deploy", "implementacion"),
    "desplegar": ("despliegue", "desplegado", "deploy"),
    "deploy": ("despliegue", "desplegado", "desplegar", "implementacion"),
    "implementacion": ("despliegue", "desplegado", "deploy"),
}

_CACHE = OrderedDict()
_BLOQUEO = threading.RLock()


def normalizar(texto):
    """Minúsculas sin acentos y solo palabras; estable entre procesos."""
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", t, re.UNICODE))


def expandir(terminos):
    """Añade sinónimos declarados sin depender de memoria_recuperacion."""
    salida = set(terminos)
    for termino in tuple(salida):
        salida.update(SINONIMOS.get(termino, ()))
    return salida


def texto_para_indice(texto):
    """Texto canónico indexado: original + sinónimos que no ya están."""
    base = normalizar(texto)
    tokens = set(base.split())
    extra = sorted(expandir(tokens) - tokens)
    return (base + " " + " ".join(extra)).strip()


def vector_fallback(texto):
    """Feature hashing con bigramas; 64 dims, determinista y sin red."""
    vector = np.zeros(DIM_FALLBACK, dtype=np.float32)
    tokens = normalizar(texto).split()
    for i, token in enumerate(tokens):
        h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        vector[int.from_bytes(h, "little") % DIM_FALLBACK] += 1.0
        if i + 1 < len(tokens):
            par = token + "_" + tokens[i + 1]
            h2 = hashlib.blake2b(par.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(h2, "little") % DIM_FALLBACK] += 0.6
    norma = float(np.linalg.norm(vector))
    if norma:
        vector /= norma
    return vector


def _offline():
    valor = os.environ.get("SILVESTRA_EMBEDDINGS_OFFLINE", "").strip().lower()
    return valor in ("1", "true", "si", "yes")


def _vector_api(texto, modo):
    """Devuelve vector o None. Caller nunca ve secretos ni cuerpos de error."""
    clave = getattr(_config, "CLAVE_COHERE", "") if _config else ""
    if not clave or _requests is None or _offline():
        return None
    try:
        respuesta = _requests.post(
            URL,
            json={"texts": [texto], "model": MODELO,
                  "input_type": "search_query" if modo == "consulta" else "search_document",
                  "truncate": "END"},
            headers={"Authorization": "Bearer " + clave},
            timeout=TIMEOUT,
        )
        if respuesta.status_code != 200:
            return None
        vector = np.asarray(respuesta.json()["embeddings"][0], dtype=np.float32)
        if not vector.size:
            return None
        norma = float(np.linalg.norm(vector))
        return vector / norma if norma else None
    except Exception:
        return None


def vector_con_tipo(texto, modo="documento", usar_api=True):
    """Devuelve (vector, tipo). El tipo permite comparar espacios iguales."""
    modo = "consulta" if modo == "consulta" else "documento"
    usar_api = bool(usar_api) and not _offline()
    clave = (modo, usar_api, normalizar(texto))
    with _BLOQUEO:
        if clave in _CACHE:
            _CACHE.move_to_end(clave)
            guardado = _CACHE[clave]
            return guardado[0].copy(), guardado[1]

    api = _vector_api(texto, modo) if usar_api else None
    if api is not None:
        vector, tipo = api, TIPO_API
    else:
        vector, tipo = vector_fallback(texto), TIPO_FALLBACK

    with _BLOQUEO:
        _CACHE[clave] = (vector.copy(), tipo)
        _CACHE.move_to_end(clave)
        while len(_CACHE) > MAX_CACHE:
            _CACHE.popitem(last=False)
    return vector.copy(), tipo


def vector(texto, modo="documento", usar_api=True):
    return vector_con_tipo(texto, modo, usar_api)[0]


def vector_consulta(texto, terminos=(), usar_api=True):
    """Consulta enriquecida con sinónimos para acercarla al documento."""
    extra = " ".join(sorted(expandir(terminos)))
    return vector_con_tipo((str(texto or "") + " " + extra).strip(), "consulta", usar_api)


def cuantizar(vector, tipo=TIPO_FALLBACK):
    """int8 escalado: 7 bytes de cabecera + 1 byte por dimensión."""
    v = np.asarray(vector, dtype=np.float32)
    escala = float(np.max(np.abs(v))) if v.size else 0.0
    if escala <= 0.0:
        escala = 1.0
    q = np.clip(np.rint(v / escala * 127.0), -127, 127).astype(np.int8)
    cabecera = struct.pack("<BHf", int(tipo) & 0xFF, min(v.size, 65535), escala)
    return cabecera + q.tobytes()


def desquantizar(blob):
    """Devuelve (vector, tipo) o None si el BLOB no es válido."""
    try:
        datos = bytes(blob)
        if len(datos) < 7:
            return None
        tipo, dim, escala = struct.unpack("<BHf", datos[:7])
        q = np.frombuffer(datos[7:7 + dim], dtype=np.int8)
        if q.size != dim or dim == 0:
            return None
        return q.astype(np.float32) * (escala / 127.0), int(tipo)
    except Exception:
        return None


def tipo_de_blob(blob):
    try:
        datos = bytes(blob)
        return int(datos[0]) if datos else None
    except Exception:
        return None


def coseno(a, b):
    """Coseno tolerante a vectores de distinta dimensión (recorta al mínimo)."""
    if a is None or b is None:
        return 0.0
    try:
        va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
        n = min(va.size, vb.size)
        if n == 0:
            return 0.0
        va, vb = va[:n], vb[:n]
        den = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if den <= 0.0:
            return 0.0
        return float(np.clip(np.dot(va, vb) / den, -1.0, 1.0))
    except Exception:
        return 0.0
