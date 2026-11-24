"""Memoria semántica por embeddings con Gemini REST y persistencia SQLite.

Genera vectores float32 en tabla memoria_vectores y calcula similitud coseno pura.
Reutiliza config.CLAVE_GOOGLE y memoria_jarvis.db sin alterar tablas existentes.
"""
import array
import json
import math
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from contextlib import closing

_bloqueo = threading.RLock()
_cache_bloqueo = threading.Lock()
_CACHE_EMBEDDINGS = OrderedDict()
MAX_CACHE = 32

MODELOS_EMBEDDING = ("gemini-embedding-001", "text-embedding-004")
DIMENSION_DEFAULT = 768

_DDL_VECTORES = """CREATE TABLE IF NOT EXISTS memoria_vectores (
    id_recuerdo TEXT PRIMARY KEY,
    texto TEXT,
    vector BLOB,
    modelo TEXT,
    actualizado_en TEXT
)"""


def _conectar(ruta_db=None):
    if ruta_db is None:
        try:
            import memoria_persistente
            ruta_db = memoria_persistente.RUTA_DB
        except Exception:
            ruta_db = "memoria_jarvis.db"
    con = sqlite3.connect(ruta_db, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_DDL_VECTORES)
    return con


def _empacar_vector(vec: list[float]) -> bytes:
    arr = array.array("f", vec)
    return arr.tobytes()


def _desempacar_vector(blob: bytes) -> list[float]:
    arr = array.array("f")
    arr.frombytes(blob)
    return arr.tolist()


def _similitud_coseno(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def _obtener_clave_google() -> str:
    try:
        import config
        return getattr(config, "CLAVE_GOOGLE", "") or ""
    except Exception:
        return ""


def obtener_embedding(texto: str, tipo_tarea: str = "RETRIEVAL_DOCUMENT") -> list[float] | None:
    """Calcula embedding vía Gemini REST API (768 dims) con caché LRU de 32 elementos."""
    t = " ".join(str(texto or "").split()).strip()
    if not t:
        return None

    clave_cache = (t, tipo_tarea)
    with _cache_bloqueo:
        if clave_cache in _CACHE_EMBEDDINGS:
            _CACHE_EMBEDDINGS.move_to_end(clave_cache)
            return list(_CACHE_EMBEDDINGS[clave_cache])

    clave = _obtener_clave_google()
    if not clave:
        return None

    for mod in MODELOS_EMBEDDING:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:embedContent?key={clave}"
        payload = {
            "model": f"models/{mod}",
            "content": {"parts": [{"text": t}]},
            "taskType": tipo_tarea,
            "outputDimensionality": DIMENSION_DEFAULT,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vec = data.get("embedding", {}).get("values")
            if vec and isinstance(vec, list):
                vec_float = [float(x) for x in vec]
                with _cache_bloqueo:
                    _CACHE_EMBEDDINGS[clave_cache] = vec_float
                    if len(_CACHE_EMBEDDINGS) > MAX_CACHE:
                        _CACHE_EMBEDDINGS.popitem(last=False)
                return vec_float
        except urllib.error.HTTPError as e:
            continue
        except (urllib.error.URLError, TimeoutError):
            continue
        except Exception:
            continue
    return None


def indexar_recuerdo(id_recuerdo: str, texto: str, ruta_db=None) -> bool:
    """Calcula y almacena vector en memoria_vectores. Omite si texto no cambió."""
    rid = str(id_recuerdo or "").strip()
    txt = " ".join(str(texto or "").split()).strip()
    if not rid or not txt:
        return False

    with _bloqueo, closing(_conectar(ruta_db)) as con:
        existente = con.execute("SELECT texto FROM memoria_vectores WHERE id_recuerdo=?", (rid,)).fetchone()
        if existente and existente["texto"] == txt:
            return True

    vec = obtener_embedding(txt, tipo_tarea="RETRIEVAL_DOCUMENT")
    if not vec:
        return False

    blob = _empacar_vector(vec)
    import datetime
    ahora_iso = datetime.datetime.now().isoformat()
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        con.execute(
            """INSERT INTO memoria_vectores(id_recuerdo, texto, vector, modelo, actualizado_en)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(id_recuerdo) DO UPDATE SET
                   texto=excluded.texto,
                   vector=excluded.vector,
                   modelo=excluded.modelo,
                   actualizado_en=excluded.actualizado_en""",
            (rid, txt, blob, MODELOS_EMBEDDING[0], ahora_iso),
        )
        con.commit()
    return True


def indexar_en_segundo_plano(id_recuerdo: str, texto: str, ruta_db=None):
    """Ejecuta indexar_recuerdo en hilo daemon sin agregar latencia a Lyris."""
    if not _obtener_clave_google():
        return
    t = threading.Thread(
        target=indexar_recuerdo,
        args=(id_recuerdo, texto, ruta_db),
        daemon=True,
        name=f"EmbeddingIndex-{id_recuerdo[:12]}",
    )
    t.start()


def buscar_semantico(consulta: str, limite: int = 5, umbral: float = 0.55, ruta_db=None) -> list[tuple[str, str, float]]:
    """Calcula similitud coseno contra vectores guardados y devuelve (id, texto, score)."""
    q = " ".join(str(consulta or "").split()).strip()
    if not q:
        return []

    q_vec = obtener_embedding(q, tipo_tarea="RETRIEVAL_QUERY")
    if not q_vec:
        return []

    with _bloqueo, closing(_conectar(ruta_db)) as con:
        filas = con.execute("SELECT id_recuerdo, texto, vector FROM memoria_vectores").fetchall()

    resultados = []
    for fila in filas:
        blob = fila["vector"]
        if not blob:
            continue
        try:
            vec = _desempacar_vector(blob)
            score = _similitud_coseno(q_vec, vec)
            if score >= umbral:
                resultados.append((fila["id_recuerdo"], fila["texto"], float(score)))
        except Exception:
            continue

    resultados.sort(key=lambda x: x[2], reverse=True)
    return resultados[:max(1, int(limite or 5))]


def backfill_pendientes(pares_id_texto: list[tuple[str, str]], max_lote: int = 15, ruta_db=None) -> int:
    """Indexa de forma gradual recuerdos previos que aún no tengan vector."""
    if not pares_id_texto:
        return 0

    with _bloqueo, closing(_conectar(ruta_db)) as con:
        indexados = {row["id_recuerdo"] for row in con.execute("SELECT id_recuerdo FROM memoria_vectores").fetchall()}

    pendientes = [(rid, txt) for rid, txt in pares_id_texto if rid not in indexados and str(txt).strip()]
    procesados = 0
    for rid, txt in pendientes[:max_lote]:
        if indexar_recuerdo(rid, txt, ruta_db=ruta_db):
            procesados += 1
    return procesados


__all__ = [
    "obtener_embedding",
    "indexar_recuerdo",
    "indexar_en_segundo_plano",
    "buscar_semantico",
    "backfill_pendientes",
    "_similitud_coseno",
    "_empacar_vector",
    "_desempacar_vector",
    "_DDL_VECTORES",
]
