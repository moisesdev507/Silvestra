"""Esquema SQLite del almacenamiento cognitivo."""
import datetime
import json
import os
import memoria_esquema_relaciones


DDL = """
CREATE TABLE IF NOT EXISTS recuerdos (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 usuario_id TEXT NOT NULL DEFAULT 'local',
 tipo_memoria TEXT NOT NULL CHECK(tipo_memoria IN ('episodica','semantica','procedimental')),
 contenido TEXT NOT NULL, contenido_norm TEXT NOT NULL,
 categoria TEXT DEFAULT 'general',
 origen TEXT NOT NULL CHECK(origen IN ('explicito','inferido','multimodal','migrado','sistema')),
 confianza REAL NOT NULL DEFAULT 0.8,
 estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','consolidado','obsoleto','contradicho','eliminado')),
 reemplaza_a_id INTEGER NULL REFERENCES recuerdos(id), fecha_evento TEXT NULL,
 creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL,
 metadatos_json TEXT DEFAULT '{}', embedding BLOB NULL);
CREATE INDEX IF NOT EXISTS idx_recuerdos_usuario_estado_tipo ON recuerdos(usuario_id,estado,tipo_memoria);
CREATE INDEX IF NOT EXISTS idx_recuerdos_usuario_norm ON recuerdos(usuario_id,contenido_norm);
CREATE VIRTUAL TABLE IF NOT EXISTS recuerdos_fts USING fts5(
 contenido,categoria,content='recuerdos',content_rowid='id');
CREATE TRIGGER IF NOT EXISTS recuerdos_ai AFTER INSERT ON recuerdos BEGIN
 INSERT INTO recuerdos_fts(rowid,contenido,categoria) VALUES(new.id,new.contenido,new.categoria);
END;
CREATE TRIGGER IF NOT EXISTS recuerdos_ad AFTER DELETE ON recuerdos BEGIN
 INSERT INTO recuerdos_fts(recuerdos_fts,rowid,contenido,categoria)
 VALUES('delete',old.id,old.contenido,old.categoria);
END;
CREATE TRIGGER IF NOT EXISTS recuerdos_au AFTER UPDATE ON recuerdos BEGIN
 INSERT INTO recuerdos_fts(recuerdos_fts,rowid,contenido,categoria)
 VALUES('delete',old.id,old.contenido,old.categoria);
 INSERT INTO recuerdos_fts(rowid,contenido,categoria) VALUES(new.id,new.contenido,new.categoria);
END;
CREATE TABLE IF NOT EXISTS entidades (
 id INTEGER PRIMARY KEY AUTOINCREMENT,nombre TEXT NOT NULL,nombre_norm TEXT NOT NULL,
 tipo TEXT,creado_en TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_entidades_norm ON entidades(nombre_norm);
CREATE TABLE IF NOT EXISTS relaciones (
 id INTEGER PRIMARY KEY AUTOINCREMENT,origen_id INTEGER NOT NULL REFERENCES entidades(id),
 tipo_relacion TEXT NOT NULL,destino_id INTEGER NOT NULL REFERENCES entidades(id),
 peso REAL NOT NULL DEFAULT 1.0,origen_dato TEXT,creado_en TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_relaciones_origen ON relaciones(origen_id);
CREATE INDEX IF NOT EXISTS idx_relaciones_destino ON relaciones(destino_id);
CREATE TABLE IF NOT EXISTS migraciones_estado (
 clave TEXT PRIMARY KEY,aplicado_en TEXT NOT NULL,detalles TEXT);
"""


def migrar_check_estados(conexion):
    """Recrea `recuerdos` para aceptar 'consolidado' sin perder filas ni FTS.

    Idempotente: solo actúa cuando la tabla existente conserva el CHECK antiguo.
    Los disparadores se reconstruyen desde el propio DDL para que apunten a la
    tabla nueva, y el índice FTS se regenera desde el contenido copiado.
    """
    fila = conexion.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recuerdos'"
    ).fetchone()
    if not fila or "'consolidado'" in (fila[0] or ""):
        return False
    total = conexion.execute("SELECT COUNT(*) FROM recuerdos").fetchone()[0]
    foreign_keys = int(conexion.execute("PRAGMA foreign_keys").fetchone()[0])
    conexion.execute("PRAGMA foreign_keys=OFF")
    conexion.execute("PRAGMA legacy_alter_table=ON")
    try:
        for disparador in ("recuerdos_ai", "recuerdos_ad", "recuerdos_au"):
            conexion.execute("DROP TRIGGER IF EXISTS " + disparador)
        conexion.execute("ALTER TABLE recuerdos RENAME TO recuerdos_legado")
        conexion.executescript(DDL)
        conexion.execute("INSERT INTO recuerdos SELECT * FROM recuerdos_legado")
        conexion.execute("DROP TABLE recuerdos_legado")
        conexion.execute("INSERT INTO recuerdos_fts(recuerdos_fts) VALUES('rebuild')")
        conexion.execute(
            "INSERT OR REPLACE INTO migraciones_estado(clave,aplicado_en,detalles) "
            "VALUES(?,?,?)",
            ("check_estado_v2",
             datetime.datetime.now(datetime.timezone.utc).isoformat(),
             json.dumps({"recuerdos": total}, ensure_ascii=False)))
        conexion.commit()
    finally:
        conexion.execute("PRAGMA legacy_alter_table=OFF")
        conexion.execute("PRAGMA foreign_keys=" + str(foreign_keys))
    return True


def reparar_fk_legado(conexion):
    """Restaura FKs que SQLite haya reescrito hacia recuerdos_legado."""
    filas = conexion.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%recuerdos_legado%'"
    ).fetchall()
    if not filas:
        return False
    fk_prev = int(conexion.execute("PRAGMA foreign_keys").fetchone()[0])
    conexion.execute("PRAGMA foreign_keys=OFF")
    conexion.execute("PRAGMA legacy_alter_table=ON")
    try:
        for nombre, sql in filas:
            idxs = [r[0] for r in conexion.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (nombre,),
            ).fetchall()]
            nuevo_sql = sql.replace('"recuerdos_legado"', "recuerdos").replace("recuerdos_legado", "recuerdos")
            tmp = f"_tmp_{nombre}_fk"
            conexion.execute(f"DROP TABLE IF EXISTS {tmp}")
            conexion.execute(f"ALTER TABLE {nombre} RENAME TO {tmp}")
            conexion.execute(nuevo_sql)
            conexion.execute(f"INSERT INTO {nombre} SELECT * FROM {tmp}")
            conexion.execute(f"DROP TABLE {tmp}")
            for idx_sql in idxs:
                conexion.execute(idx_sql)
        conexion.commit()
    finally:
        conexion.execute("PRAGMA legacy_alter_table=OFF")
        conexion.execute("PRAGMA foreign_keys=" + str(fk_prev))
    return True


def inicializar(conexion, ruta=None):
    """Aplica pragmas y DDL idempotente a una conexión SQLite."""
    if ruta and ruta != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    conexion.execute("PRAGMA foreign_keys=ON")
    if ruta != ":memory:":
        conexion.execute("PRAGMA journal_mode=WAL")
        conexion.execute("PRAGMA synchronous=NORMAL")
    tabla = conexion.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recuerdos'").fetchone()
    fts = conexion.execute("SELECT 1 FROM sqlite_master WHERE name='recuerdos_fts'").fetchone()
    if tabla:
        columnas = {r[1] for r in conexion.execute("PRAGMA table_info(recuerdos)")}
        if "usuario_id" not in columnas:
            conexion.execute("ALTER TABLE recuerdos ADD COLUMN usuario_id TEXT NOT NULL DEFAULT 'local'")
            conexion.commit()
    conexion.executescript(DDL)
    migrar_check_estados(conexion)
    reparar_fk_legado(conexion)
    if tabla and not fts:
        conexion.execute("INSERT INTO recuerdos_fts(recuerdos_fts) VALUES('rebuild')")
    conexion.commit()
    memoria_esquema_relaciones.migrar(conexion)
    return conexion
