"""Memoria semántica: Gemini con clave y NumPy 100 % offline.

Mantiene la API histórica (memoria_vectores / memoria_jarvis.db) y añade
kaya_embeddings en la DB canónica `silvestra_memoria.db` con indexado en cola daemon.
"""
import array, hashlib, math, os, queue, re, sqlite3, threading, time
from contextlib import closing

import embeddings_gemini_rest as gemini_rest

RUTA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra_memoria.db")
_bloqueo = threading.RLock()
DIM_OFFLINE = 256
_DDL_VECTORES = """CREATE TABLE IF NOT EXISTS memoria_vectores (
    id_recuerdo TEXT PRIMARY KEY, texto TEXT, vector BLOB,
    modelo TEXT, actualizado_en TEXT)"""
_DDL_KAYA = ("CREATE TABLE IF NOT EXISTS kaya_embeddings ("
             "recuerdo_id TEXT PRIMARY KEY, usuario_id TEXT, vector_blob BLOB, "
             "dim INTEGER, actualizado_en REAL)")
_COLA = queue.Queue()
_trabajador_iniciado = False


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


def _conectar_kaya(ruta_db=None):
    ruta = ruta_db or RUTA_DB
    carpeta = os.path.dirname(os.path.abspath(ruta))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=5.0, check_same_thread=False)
    con.execute(_DDL_KAYA)
    return con


def _empacar_vector(vec):
    return array.array("f", vec).tobytes()


def _desempacar_vector(blob):
    arr = array.array("f")
    arr.frombytes(blob)
    return arr.tolist()


def _similitud_coseno(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = n1 = n2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        n1 += a * a
        n2 += b * b
    return 0.0 if n1 <= 0 or n2 <= 0 else dot / (math.sqrt(n1) * math.sqrt(n2))


def obtener_embedding(texto, tipo_tarea="RETRIEVAL_DOCUMENT"):
    """Compatibilidad con la API histórica (REST en el submódulo dedicado)."""
    return gemini_rest.obtener_embedding(texto, tipo_tarea)


def _clave_explicita():
    """GEMINI_API_KEY declara embeddings online; sin ella todo es offline."""
    valor = os.environ.get("GEMINI_API_KEY", "").strip()
    if valor:
        return valor
    try:
        import claves_dinamicas
        return claves_dinamicas.valor("GEMINI_API_KEY", "GOOGLE_API_KEY")
    except Exception:
        return ""


def _vector_offline(texto):
    """N-gramas de caracteres y palabras normalizadas, determinista (NumPy)."""
    try:
        import numpy as np
        t = "".join(c for c in " ".join(str(texto or "").casefold().split())
                    if c.isalnum() or c.isspace())
        palabras = re.findall(r"\w+", t)
        grams = [t[i:i + n] for n in (3, 4) for i in range(max(0, len(t) - n + 1))]
        grams += [palabras[i] + " " + palabras[i + 1] for i in range(len(palabras) - 1)]
        vec = np.zeros(DIM_OFFLINE, dtype=np.float32)
        for gram in grams:
            h = hashlib.blake2b(gram.encode(), digest_size=4).digest()
            vec[int.from_bytes(h, "big") % DIM_OFFLINE] += 1.0
        norma = float(np.linalg.norm(vec))
        return (vec / norma).tolist() if norma else []
    except Exception:
        return []


def vectorizar(texto, permitir_online=True):
    """Online con GEMINI_API_KEY; respaldo offline siempre disponible."""
    if permitir_online and _clave_explicita():
        vec = obtener_embedding(texto)
        if vec:
            return vec
    return _vector_offline(texto)


def indexar_recuerdo(id_recuerdo, texto, ruta_db=None):
    """API histórica: vector Gemini en memoria_vectores."""
    rid, txt = str(id_recuerdo or "").strip(), " ".join(str(texto or "").split()).strip()
    if not rid or not txt:
        return False
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        previo = con.execute("SELECT texto FROM memoria_vectores WHERE id_recuerdo=?", (rid,)).fetchone()
        if previo and previo["texto"] == txt:
            return True
    vec = obtener_embedding(txt)
    if not vec:
        return False
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        con.execute(
            "INSERT INTO memoria_vectores VALUES(?,?,?,?,?) ON CONFLICT(id_recuerdo) "
            "DO UPDATE SET texto=excluded.texto,vector=excluded.vector,"
            "modelo=excluded.modelo,actualizado_en=excluded.actualizado_en",
            (rid, txt, _empacar_vector(vec), gemini_rest.MODELOS_EMBEDDING[0], time.time()))
        con.commit()
    return True


def indexar_en_segundo_plano(id_recuerdo, texto, ruta_db=None):
    """Indexado histórico en daemon, sin latencia para la voz."""
    if not gemini_rest._clave():
        return
    threading.Thread(target=indexar_recuerdo, args=(id_recuerdo, texto, ruta_db),
                     daemon=True, name="EmbeddingIndex-" + str(id_recuerdo)[:12]).start()


def indexar_recuerdo_kaya(recuerdo_id, texto, usuario_id="local", ruta_db=None):
    """Guarda el vector en kaya_embeddings con su dim para no mezclar modelos."""
    rid, txt = str(recuerdo_id or "").strip(), " ".join(str(texto or "").split()).strip()
    if not rid or not txt:
        return False
    vec = vectorizar(txt)
    if not vec:
        return False
    with _bloqueo, closing(_conectar_kaya(ruta_db)) as con:
        con.execute(
            "INSERT INTO kaya_embeddings VALUES(?,?,?,?,?) ON CONFLICT(recuerdo_id) "
            "DO UPDATE SET usuario_id=excluded.usuario_id,vector_blob=excluded.vector_blob,"
            "dim=excluded.dim,actualizado_en=excluded.actualizado_en",
            (rid, str(usuario_id or "local"), _empacar_vector(vec), len(vec), time.time()))
        con.commit()
    return True


def encolar_indexado(recuerdo_id, texto, usuario_id="local", ruta_db=None):
    """Encola el recuerdo recién guardado; retorno inmediato (0 ms en audio/UI)."""
    global _trabajador_iniciado
    if not str(recuerdo_id or "").strip():
        return False
    _COLA.put((str(recuerdo_id), str(texto or ""), str(usuario_id or "local"), ruta_db))
    with _bloqueo:
        if not _trabajador_iniciado:
            _trabajador_iniciado = True
            threading.Thread(target=_trabajador_cola, daemon=True,
                             name="kaya-embeddings").start()
    return True


def _trabajador_cola():
    while True:
        rid, texto, uid, ruta = _COLA.get()
        try:
            indexar_recuerdo_kaya(rid, texto, uid, ruta)
        except Exception:
            pass
        finally:
            _COLA.task_done()


def buscar_semantico_kaya(consulta, usuario_id="local", limite=5, ruta_db=None):
    """Recupera por significado: devuelve (recuerdo_id, contenido, score)."""
    q = " ".join(str(consulta or "").split()).strip()
    if not q:
        return []
    q_off = _vector_offline(q)
    with _bloqueo, closing(_conectar_kaya(ruta_db)) as con:
        filas = con.execute(
            "SELECT e.recuerdo_id,r.contenido,e.vector_blob,e.dim FROM kaya_embeddings e "
            "JOIN recuerdos r ON r.id=CAST(e.recuerdo_id AS INTEGER) "
            "WHERE e.usuario_id=? AND r.estado='activo'", (str(usuario_id or "local"),)
        ).fetchall()
    if not filas or not q_off:
        return []
    q_on = None
    if any(int(f[3]) != len(q_off) for f in filas) and _clave_explicita():
        try:
            q_on = obtener_embedding(q, "RETRIEVAL_QUERY")
        except Exception:
            pass
    resultados, vistos = [], set()
    for rid, texto, blob, dim in filas:
        dim = int(dim or 0)
        qv = q_off if dim == len(q_off) else (q_on if q_on and dim == len(q_on) else None)
        score = _similitud_coseno(qv, _desempacar_vector(blob)) if qv else 0.0
        clave = " ".join(str(texto or "").split()).casefold()[:60]
        if score > 0.12 and clave not in vistos:
            vistos.add(clave)
            resultados.append((rid, texto, float(score)))
    resultados.sort(key=lambda x: x[2], reverse=True)
    return resultados[:max(1, int(limite or 5))]


def buscar_semantico(consulta, usuario_id="local", limite=5, umbral=0.72, ruta_db=None):
    """API pública: kaya_embeddings por significado; legado como respaldo."""
    try:
        nuevos = buscar_semantico_kaya(consulta, usuario_id, limite, ruta_db)
        if nuevos:
            return nuevos
    except Exception:
        pass
    q = " ".join(str(consulta or "").split()).strip()
    q_vec = obtener_embedding(q, "RETRIEVAL_QUERY") if q else None
    if not q_vec:
        return []
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        filas = con.execute("SELECT id_recuerdo,texto,vector FROM memoria_vectores").fetchall()
    salida = []
    for fila in filas:
        try:
            score = _similitud_coseno(q_vec, _desempacar_vector(fila["vector"]))
            if score >= umbral:
                salida.append((fila["id_recuerdo"], fila["texto"], float(score)))
        except Exception:
            pass
    salida.sort(key=lambda x: x[2], reverse=True)
    return salida[:max(1, int(limite or 5))]


def backfill_pendientes(pares_id_texto, max_lote=15, ruta_db=None):
    """Indexa gradualmente recuerdos previos sin vector."""
    if not pares_id_texto:
        return 0
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        indexados = {r["id_recuerdo"] for r in con.execute("SELECT id_recuerdo FROM memoria_vectores")}
    pendientes = [(r, t) for r, t in pares_id_texto if r not in indexados and str(t).strip()]
    return sum(1 for r, t in pendientes[:max_lote] if indexar_recuerdo(r, t, ruta_db=ruta_db))


__all__ = [
    "obtener_embedding", "vectorizar", "indexar_recuerdo", "indexar_en_segundo_plano",
    "indexar_recuerdo_kaya", "encolar_indexado", "buscar_semantico",
    "buscar_semantico_kaya", "backfill_pendientes", "_similitud_coseno",
    "_empacar_vector", "_desempacar_vector", "_DDL_VECTORES", "_DDL_KAYA", "RUTA_DB",
]
