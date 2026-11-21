"""Esquema SQLite del almacenamiento cognitivo."""
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
 estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','obsoleto','contradicho','eliminado')),
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
    if tabla and not fts:
        conexion.execute("INSERT INTO recuerdos_fts(recuerdos_fts) VALUES('rebuild')")
    conexion.commit()
    memoria_esquema_relaciones.migrar(conexion)
    return conexion
