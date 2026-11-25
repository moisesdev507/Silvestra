"""Memoria persistente ligera en SQLite (``memoria_jarvis.db``).

Guarda órdenes explícitas del usuario ("recuerda que…") y las devuelve como
un bloque compacto para inyectar en el prompt. Es independiente del esquema
cognitivo grande y usa su propio archivo, ignorado por Git.
"""
import os
import re
import sqlite3
import threading
import time
from contextlib import closing
import unicodedata

RUTA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "memoria_jarvis.db")
LIMITE_CONTEXTO = 550
_bloqueo = threading.RLock()

# Caché en RAM de los recuerdos cargados e índice para búsqueda instantánea (< 15 ms)
_cache_filas_ram = None
_cache_busquedas_ram = {}
_cache_version = 0


def _invalidar_cache_ram():
    global _cache_filas_ram, _cache_busquedas_ram, _cache_version
    with _bloqueo:
        _cache_filas_ram = None
        _cache_busquedas_ram.clear()
        _cache_version += 1

_DDL = """CREATE TABLE IF NOT EXISTS recuerdos (
    id INTEGER PRIMARY KEY,
    categoria TEXT,
    clave TEXT UNIQUE,
    valor TEXT,
    actualizado_en REAL
)"""

# "no olvides que" también cuenta; a diferencia del extractor cognitivo,
# aquí NO se descartan referencias temporales como "mañana".
_PATRON = re.compile(
    r"\b(?:recuerda(?:me)?|anota|apunta|guarda|no\s+olvides)\s*(?:que)?\s*[:,\-]?\s*(.+)",
    re.IGNORECASE)
_NO_GUARDAR = re.compile(
    r"\b(?:no\s+(?:guardes|recuerdes|almacenes|memorices|lo\s+guardes|lo\s+recuerdes))\b",
    re.IGNORECASE)
_TEMPORALES = ("mañana", "entrega", "reunion", "reunión", "cita", "plazo",
               "tarea", "pendiente", "recordatorio")


def _conectar(ruta_db=None):
    """Abre la BD y garantiza el esquema exacto solicitado."""
    con = sqlite3.connect(ruta_db or RUTA_DB, timeout=5.0,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_DDL)
    return con


def _fila(row):
    return {
        "id": row["id"], "categoria": row["categoria"],
        "clave": row["clave"], "valor": row["valor"],
        "actualizado_en": row["actualizado_en"],
    }


def _seguro(valor):
    """Rechaza secretos usando el filtro existente, sin duplicar patrones."""
    try:
        import memoria_filtro
        return not memoria_filtro._contiene_secreto(str(valor))
    except Exception:
        return True


def guardar_recuerdo(categoria, clave, valor, ruta_db=None):
    """Inserta o actualiza un recuerdo por ``clave``. Devuelve la fila o None."""
    clave = " ".join(str(clave or "").split())[:120].strip()
    texto = " ".join(str(valor or "").split())[:500].strip()
    if not clave or not texto or not _seguro(texto):
        return None
    cat = " ".join(str(categoria or "general").split())[:40] or "general"
    ahora = time.time()
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        cur = con.execute(
            "UPDATE recuerdos SET categoria=?, valor=?, actualizado_en=? WHERE clave=?",
            (cat, texto, ahora, clave))
        if not cur.rowcount:
            con.execute(
                "INSERT INTO recuerdos(categoria, clave, valor, actualizado_en) "
                "VALUES(?,?,?,?)", (cat, clave, texto, ahora))
        con.commit()
        fila = con.execute("SELECT * FROM recuerdos WHERE clave=?", (clave,)).fetchone()
    _invalidar_cache_ram()
    res = _fila(fila) if fila else None
    if res:
        try:
            import memoria_cache_rapida
            memoria_cache_rapida.invalidar_recuerdos()
        except Exception:
            pass
    if res and not os.environ.get("DESACTIVAR_EMBEDDINGS"):
        try:
            import memoria_semantica
            memoria_semantica.indexar_en_segundo_plano(f"rec_{res['id']}", res["valor"], ruta_db=ruta_db)
        except Exception:
            pass
    return res


def _cargar_todas_filas(ruta_db=None):
    """Carga y cachea en RAM todos los recuerdos activos."""
    global _cache_filas_ram
    if _cache_filas_ram is not None and not ruta_db:
        return _cache_filas_ram
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        filas = con.execute("SELECT * FROM recuerdos ORDER BY actualizado_en DESC").fetchall()
    resultado = [_fila(f) for f in filas]
    if not ruta_db:
        with _bloqueo:
            _cache_filas_ram = resultado
    return resultado


def buscar_recuerdos(consulta, limite=6, ruta_db=None):
    """Recuerdos ordenados por relevancia al texto y, después, por antigüedad."""
    consulta = str(consulta or "")
    lim = max(0, int(limite or 6))
    clave_cache = (consulta.strip().lower(), lim)
    if not ruta_db:
        with _bloqueo:
            if clave_cache in _cache_busquedas_ram:
                return list(_cache_busquedas_ram[clave_cache])
    terminos = [t for t in re.findall(r"\w+", unicodedata.normalize(
        "NFKD", consulta.lower()).encode("ascii", "ignore").decode("ascii"))
        if len(t) >= 3]
    filas = list(_cargar_todas_filas(ruta_db=ruta_db))

    def peso(fila):
        texto = unicodedata.normalize("NFKD", (fila["clave"] + " " + fila["valor"]).lower())
        texto = texto.encode("ascii", "ignore").decode("ascii")
        return sum(1 for t in terminos if t in texto)

    if terminos:
        filas = [f for f in filas if peso(f) > 0]
        filas.sort(key=lambda f: (-peso(f), -f["actualizado_en"]))

    # Búsqueda semántica complementaria: se omite en frases de seguimiento o cortas sin petición explícita
    try:
        import memoria_cache_rapida
        omitir_semantica = memoria_cache_rapida.es_seguimiento_o_frase_corta(consulta)
    except Exception:
        omitir_semantica = False

    if not omitir_semantica:
        try:
            import memoria_semantica
            sem = memoria_semantica.buscar_semantico(consulta, limite=limite, umbral=0.72, ruta_db=ruta_db)
            if sem:
                sem_map = {int(s[0].replace("rec_", "")): s[2] for s in sem if s[0].startswith("rec_") and s[0][4:].isdigit()}
                if sem_map:
                    with _bloqueo, closing(_conectar(ruta_db)) as con:
                        q_ids = ",".join(str(i) for i in sem_map.keys())
                        f_sem = con.execute(f"SELECT * FROM recuerdos WHERE id IN ({q_ids})").fetchall()
                        filas_sem = [_fila(f) for f in f_sem]
                    # Unir sin duplicados: primero los de coincidencia exacta/lexical, luego semánticos
                    ids_existentes = {f["id"] for f in filas}
                    for fs in filas_sem:
                        if fs["id"] not in ids_existentes:
                            filas.append(fs)
                            ids_existentes.add(fs["id"])
        except Exception:
            pass

    res = filas[:lim]
    if not ruta_db:
        with _bloqueo:
            _cache_busquedas_ram[clave_cache] = list(res)
            if len(_cache_busquedas_ram) > 200:
                _cache_busquedas_ram.pop(next(iter(_cache_busquedas_ram)))
    return res


def listar_recuerdos(limite=15, ruta_db=None):
    """Recuerdos más recientes usando la caché en RAM."""
    filas = _cargar_todas_filas(ruta_db=ruta_db)
    return filas[:max(0, int(limite or 15))]


def eliminar_recuerdo(clave, ruta_db=None):
    """Elimina un recuerdo por clave. Devuelve True si existía."""
    clave = " ".join(str(clave or "").split())[:120].strip()
    if not clave:
        return False
    with _bloqueo, closing(_conectar(ruta_db)) as con:
        cur = con.execute("DELETE FROM recuerdos WHERE clave=?", (clave,))
        con.commit()
        ok = bool(cur.rowcount)
        if ok:
            _invalidar_cache_ram()
            try:
                import memoria_cache_rapida
                memoria_cache_rapida.invalidar_recuerdos()
            except Exception:
                pass
        return ok


def extraer_y_guardar_automatico(texto_usuario, ruta_db=None):
    """Detecta órdenes de memoria y las guarda. Devuelve las filas guardadas."""
    texto = " ".join(str(texto_usuario or "").split())
    if not texto or _NO_GUARDAR.search(texto):
        return []
    guardados = []
    for coincidencia in _PATRON.finditer(texto):
        valor = coincidencia.group(1).strip(" \t:;,-¿?¡!\"'")
        if len(valor) < 8 or not _seguro(valor):
            continue
        normal = unicodedata.normalize("NFKD", valor.lower())
        normal = "".join(c for c in normal if not unicodedata.combining(c))
        clave = re.sub(r"[^a-z0-9]+", "_", normal).strip("_")[:100]
        if not clave:
            continue
        categoria = "tarea" if any(t in normal for t in _TEMPORALES) else "general"
        fila = guardar_recuerdo(categoria, clave, valor, ruta_db=ruta_db)
        if fila:
            guardados.append(fila)
    return guardados


def contexto_para_prompt(consulta="", limite=6, ruta_db=None):
    """Bloque compacto (<=550 caracteres) para inyectar en el prompt."""
    consulta = str(consulta or "")
    recuerdos = (buscar_recuerdos(consulta, limite, ruta_db=ruta_db) if consulta.strip()
                 else listar_recuerdos(limite, ruta_db=ruta_db))
    if not recuerdos:
        return ""
    lineas = ["[RECUERDOS PERSISTENTES]"]
    for recuerdo in recuerdos:
        valor = " ".join(str(recuerdo.get("valor") or "").split())
        if valor:
            lineas.append("- " + valor)
    bloque = "\n".join(lineas)
    if len(bloque) > LIMITE_CONTEXTO:
        recortado = []
        for linea in lineas:
            candidato = "\n".join(recortado + [linea])
            if len(candidato) > LIMITE_CONTEXTO - 1:
                break
            recortado.append(linea)
        if len(recortado) < 2:
            recortado = [lineas[0], lineas[1][:LIMITE_CONTEXTO - len(lineas[0]) - 2]]
        bloque = "\n".join(recortado)
    return bloque[:LIMITE_CONTEXTO]


__all__ = [
    "RUTA_DB", "LIMITE_CONTEXTO", "guardar_recuerdo", "buscar_recuerdos",
    "listar_recuerdos", "eliminar_recuerdo", "extraer_y_guardar_automatico",
    "contexto_para_prompt",
]
