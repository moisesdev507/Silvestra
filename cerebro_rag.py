"""Motor de RAG local seguro para proyectos del dueño en SQLite FTS5.

Indexa carpetas autorizadas (por defecto workspace_lyris/) excluyendo rutas sensibles,
archivos de configuración privada, secretos y librerías externas.
"""
import datetime
import os
import re
import sqlite3
import threading

_bloqueo = threading.RLock()
# DDL ejecutado una sola vez por proceso y ruta de BD (clave = ruta absoluta).
_inicializado = set()
RUTA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra_memoria.db")

EXTENSIONES_VALIDAS = {".py", ".js", ".ts", ".html", ".css", ".sql", ".md", ".txt", ".json"}
DIRECTORIOS_IGNORADOS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".gemini", ".vscode", ".idea", "build", "dist"}
ARCHIVOS_IGNORADOS_EXACTOS = {"config.py", "estado.json", "memoria.json"}
MAX_BYTES_ARCHIVO = 256 * 1024  # 256 KB


def _obtener_conexion():
    con = sqlite3.connect(RUTA_DB, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def invalidar_cache_rag():
    """Permite repetir el DDL tras cambiar RUTA_DB (útil en pruebas aisladas)."""
    with _bloqueo:
        _inicializado.clear()


def inicializar_rag(forzar=False):
    """Crea las tablas de indexación una sola vez por ruta de BD y proceso."""
    clave = os.path.abspath(RUTA_DB)
    with _bloqueo:
        if not forzar and clave in _inicializado:
            return
        with _obtener_conexion() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS rag_rutas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ruta TEXT UNIQUE NOT NULL,
                    tipo TEXT DEFAULT 'proyecto',
                    indexado_en TEXT NOT NULL,
                    total_archivos INTEGER DEFAULT 0,
                    total_fragmentos INTEGER DEFAULT 0
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS rag_fragmentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ruta_archivo TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    indice_fragmento INTEGER NOT NULL,
                    contenido TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_rag_frag_ruta ON rag_fragmentos(ruta_archivo)")
            try:
                con.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
                        nombre_archivo,
                        ruta_archivo,
                        contenido,
                        content='rag_fragmentos',
                        content_rowid='id'
                    )
                """)
                con.execute("""
                    CREATE TRIGGER IF NOT EXISTS rag_ai AFTER INSERT ON rag_fragmentos BEGIN
                        INSERT INTO rag_fts(rowid, nombre_archivo, ruta_archivo, contenido)
                        VALUES (new.id, new.nombre_archivo, new.ruta_archivo, new.contenido);
                    END;
                """)
                con.execute("""
                    CREATE TRIGGER IF NOT EXISTS rag_ad AFTER DELETE ON rag_fragmentos BEGIN
                        INSERT INTO rag_fts(rag_fts, rowid, nombre_archivo, ruta_archivo, contenido)
                        VALUES ('delete', old.id, old.nombre_archivo, old.ruta_archivo, old.contenido);
                    END;
                """)
            except Exception as e:
                print(f"[rag] FTS5 trigger notice: {e}", flush=True)
            con.commit()
        _inicializado.add(clave)


def es_ruta_segura(ruta):
    """Verifica si la ruta no pertenece a zonas del sistema operativo o carpetas críticas."""
    if not ruta or not str(ruta).strip():
        return False, "Ruta vacía."

    abs_p = os.path.abspath(ruta)
    p_norm = abs_p.lower().replace("/", "\\")

    patrones_bloqueados = [
        r"\\windows\\", r"\\system32\\", r"\\program files", r"\\program files \(x86\)",
        r"\\appdata\\local\\temp", r"\\boot\\", r"\\recovery\\"
    ]
    for pat in patrones_bloqueados:
        if re.search(pat, p_norm):
            return False, "Ruta de sistema operativo no permitida por seguridad."

    return True, abs_p


def _es_archivo_seguro(nombre_archivo, ruta_completa):
    """Filtra archivos de configuración sensible, extensiones binarias y pesos excesivos."""
    nom_l = nombre_archivo.lower()
    if nom_l in ARCHIVOS_IGNORADOS_EXACTOS:
        return False
    if nom_l.startswith(".env") or nom_l.endswith((".pem", ".key", ".db", ".sqlite", ".tmp", ".pyc")):
        return False

    _, ext = os.path.splitext(nom_l)
    if ext not in EXTENSIONES_VALIDAS:
        return False

    try:
        tam = os.path.getsize(ruta_completa)
        if tam <= 0 or tam > MAX_BYTES_ARCHIVO:
            return False
    except Exception:
        return False

    return True


def _fragmentar_texto(texto, tam_chunk=600, overlap=80):
    """Divide un texto en fragmentos solapados para búsqueda contextual."""
    t = str(texto or "").strip()
    if not t:
        return []
    if len(t) <= tam_chunk:
        return [t]

    chunks = []
    inicio = 0
    while inicio < len(t):
        fin = min(len(t), inicio + tam_chunk)
        chunks.append(t[inicio:fin])
        if fin == len(t):
            break
        inicio += (tam_chunk - overlap)
    return chunks


def indexar_ruta(ruta="workspace_lyris"):
    """Indexa de forma segura todos los archivos de texto/código de una carpeta permitida."""
    inicializar_rag()
    segura, res_o_motivo = es_ruta_segura(ruta)
    if not segura:
        return False, res_o_motivo

    ruta_abs = res_o_motivo
    if not os.path.exists(ruta_abs) or not os.path.isdir(ruta_abs):
        return False, f"La carpeta no existe: '{ruta}'."

    total_archivos = 0
    total_fragmentos = 0
    ahora_iso = datetime.datetime.now().isoformat()

    with _bloqueo:
        with _obtener_conexion() as con:
            # Limpiar fragmentos previos de esta ruta base
            con.execute("DELETE FROM rag_fragmentos WHERE ruta_archivo LIKE ?", (f"{ruta_abs}%",))

            for raiz, dirs, archivos in os.walk(ruta_abs):
                # Filtrar directorios prohibidos en caliente
                dirs[:] = [d for d in dirs if d.lower() not in DIRECTORIOS_IGNORADOS]

                for arch in archivos:
                    p_completa = os.path.join(raiz, arch)
                    if not _es_archivo_seguro(arch, p_completa):
                        continue

                    try:
                        with open(p_completa, "r", encoding="utf-8", errors="replace") as f:
                            contenido = f.read()
                    except Exception:
                        continue

                    _, ext = os.path.splitext(arch)
                    chunks = _fragmentar_texto(contenido)
                    if not chunks:
                        continue

                    total_archivos += 1
                    for idx, chunk in enumerate(chunks):
                        total_fragmentos += 1
                        con.execute("""
                            INSERT INTO rag_fragmentos (ruta_archivo, nombre_archivo, extension, indice_fragmento, contenido, actualizado_en)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (p_completa, arch, ext, idx, chunk, ahora_iso))

            # Actualizar registro de rutas
            con.execute("""
                INSERT INTO rag_rutas (ruta, indexado_en, total_archivos, total_fragmentos)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ruta) DO UPDATE SET
                    indexado_en=excluded.indexado_en,
                    total_archivos=excluded.total_archivos,
                    total_fragmentos=excluded.total_fragmentos
            """, (ruta_abs, ahora_iso, total_archivos, total_fragmentos))
            con.commit()

    nom_base = os.path.basename(ruta_abs.rstrip("\\/")) or ruta_abs
    return True, f"Indexados {total_archivos} archivos y {total_fragmentos} fragmentos en '{nom_base}' con éxito."


def consultar_rag(consulta, limite=3):
    """Consulta la base de conocimiento FTS5 y devuelve un bloque de contexto compacto (<= 900 chars)."""
    if not consulta or len(str(consulta).strip()) < 4:
        return ""

    inicializar_rag()
    tokens = re.findall(r"[a-zA-Z0-9_áéíóúüñÁÉÍÓÚÜÑ]{3,}", str(consulta).lower())
    stop_words = {"para", "como", "donde", "cual", "archivo", "proyecto", "codigo", "este", "esta", "sobre", "tiene", "hacer", "quiero", "puedes", "mira"}
    candidatos = [t for t in tokens if t not in stop_words]
    if not candidatos:
        return ""

    with _bloqueo:
        try:
            with _obtener_conexion() as con:
                # 1. Búsqueda con FTS5
                query_fts = " OR ".join(f'"{c}"' for c in candidatos[:5])
                filas = []
                try:
                    cur = con.execute("""
                        SELECT f.nombre_archivo, f.ruta_archivo, f.contenido
                        FROM rag_fts fts
                        JOIN rag_fragmentos f ON f.id = fts.rowid
                        WHERE rag_fts MATCH ?
                        LIMIT ?
                    """, (query_fts, limite))
                    filas = cur.fetchall()
                except Exception:
                    filas = []

                # 2. Respaldo LIKE si FTS5 no arrojó resultados
                if not filas:
                    conds = " OR ".join("contenido LIKE ?" for _ in candidatos[:3])
                    params = [f"%{c}%" for c in candidatos[:3]] + [limite]
                    cur = con.execute(f"""
                        SELECT nombre_archivo, ruta_archivo, contenido
                        FROM rag_fragmentos
                        WHERE {conds}
                        LIMIT ?
                    """, params)
                    filas = cur.fetchall()

                if not filas:
                    return ""

                lineas = ["[CONTEXTO DE PROYECTO (RAG LOCAL):"]
                caracteres_totales = 40
                for f in filas:
                    nom = f["nombre_archivo"]
                    cont = " ".join(str(f["contenido"] or "").split())
                    if len(cont) > 240:
                        cont = cont[:230] + "..."
                    linea = f"- {nom}: {cont}"
                    if caracteres_totales + len(linea) > 880:
                        break
                    lineas.append(linea)
                    caracteres_totales += len(linea) + 1

                lineas.append("]")
                return "\n".join(lineas)
        except Exception as e:
            print(f"[rag] Error en consulta: {e}", flush=True)
            return ""


def detectar_orden_indexacion(texto):
    """Detecta si el usuario ordena indexar o aprender un proyecto/carpeta."""
    if not texto or len(str(texto).strip()) < 6:
        return None
    m = re.search(r"^(?:por\s+favor\s+)?(?:indexa(?:r)?|aprende\s+mi\s+proyecto\s+en)\s+(?:la\s+carpeta\s+)?(.+?)[\.\?!]?$", str(texto).strip(), re.I)
    if m:
        candidato = m.group(1).strip().strip("\"'")
        if candidato and not any(exc in candidato.lower() for exc in ("habilidad", "recordatorio", "foto")):
            return candidato
    return None
