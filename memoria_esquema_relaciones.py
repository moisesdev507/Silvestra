"""Migración transaccional aditiva para el grafo de conocimiento."""
import re
import unicodedata


def _normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", t, re.UNICODE))


def migrar(conexion):
    with conexion:
        conexion.execute("BEGIN IMMEDIATE")
        for tabla, campos in (("entidades", {"usuario_id": "TEXT NOT NULL DEFAULT 'local'"}),
            ("relaciones", {"usuario_id": "TEXT NOT NULL DEFAULT 'local'",
             "recuerdo_id": "INTEGER REFERENCES recuerdos(id) ON DELETE SET NULL",
             "dirigida": "INTEGER NOT NULL DEFAULT 1 CHECK(dirigida IN (0,1))",
             "origen": "TEXT NOT NULL DEFAULT 'inferida' CHECK(origen IN ('explicita','inferida'))",
             "confianza": "REAL NOT NULL DEFAULT 0.5 CHECK(confianza BETWEEN 0 AND 1)",
             "estado": "TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','contradicho','obsoleto','eliminado'))",
             "actualizado_en": "TEXT NOT NULL DEFAULT ''"})):
            columnas = {r[1] for r in conexion.execute(f"PRAGMA table_info({tabla})")}
            if tabla == "relaciones":
                antigua_origen = "origen" not in columnas
                antigua_confianza = "confianza" not in columnas
            for nombre, ddl in campos.items():
                if nombre not in columnas:
                    conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {ddl}")
                    columnas.add(nombre)
        for fila in conexion.execute("SELECT id,nombre FROM entidades ORDER BY id").fetchall():
            norm = _normalizar(fila[1]) or f"entidad_{fila[0]}"
            conexion.execute("UPDATE entidades SET nombre_norm=? WHERE id=?", (norm, fila[0]))
        grupos = {}
        for eid, uid, norm in conexion.execute("SELECT id,usuario_id,nombre_norm FROM entidades ORDER BY id"):
            grupos.setdefault((uid, norm), []).append(eid)
        for ids in grupos.values():
            canon = ids[0]
            for dup in ids[1:]:
                conexion.execute("UPDATE relaciones SET origen_id=? WHERE origen_id=?", (canon, dup))
                conexion.execute("UPDATE relaciones SET destino_id=? WHERE destino_id=?", (canon, dup))
                conexion.execute("DELETE FROM entidades WHERE id=?", (dup,))
        conexion.execute("UPDATE relaciones SET actualizado_en=creado_en WHERE actualizado_en=''")
        if antigua_confianza:
            conexion.execute("UPDATE relaciones SET confianza=MIN(1.0,MAX(0.0,COALESCE(peso,0.5)))")
        if antigua_origen:
            conexion.execute("UPDATE relaciones SET origen=CASE WHEN lower(COALESCE(origen_dato,'')) IN ('explicita','explícita','usuario','explicit') THEN 'explicita' ELSE 'inferida' END")
        conexion.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_entidades_usuario_norm ON entidades(usuario_id,nombre_norm)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_relaciones_usuario_origen ON relaciones(usuario_id,origen_id,estado)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_relaciones_usuario_destino ON relaciones(usuario_id,destino_id,estado)")
        conexion.execute("""CREATE TABLE IF NOT EXISTS recuerdos_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recuerdo_id INTEGER NOT NULL,
            usuario_id TEXT NOT NULL, accion TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            fecha TEXT NOT NULL, motivo TEXT DEFAULT '')""")
        conexion.execute("""CREATE TABLE IF NOT EXISTS recuerdos_linaje (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recuerdo_id INTEGER NOT NULL,
            origen_id INTEGER NOT NULL, usuario_id TEXT NOT NULL,
            fecha TEXT NOT NULL, motivo TEXT DEFAULT '')""")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_historial_usuario_recuerdo ON recuerdos_historial(usuario_id,recuerdo_id)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_linaje_usuario_recuerdo ON recuerdos_linaje(usuario_id,recuerdo_id)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_linaje_usuario_origen ON recuerdos_linaje(usuario_id,origen_id)")
        conexion.execute("""DELETE FROM relaciones WHERE estado='activo' AND id NOT IN
            (SELECT MIN(id) FROM relaciones WHERE estado='activo' GROUP BY usuario_id,origen_id,
             tipo_relacion,destino_id,dirigida,COALESCE(recuerdo_id,0),origen,COALESCE(origen_dato,''))""")
        conexion.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_relaciones_dedupe ON relaciones(usuario_id,origen_id,tipo_relacion,destino_id,dirigida,COALESCE(recuerdo_id,0),origen,COALESCE(origen_dato,'')) WHERE estado='activo'")
        conexion.execute("""CREATE TRIGGER IF NOT EXISTS recuerdo_relacion_obsoleta
            AFTER UPDATE OF estado ON recuerdos WHEN new.estado IN ('eliminado','obsoleto')
            BEGIN UPDATE relaciones SET estado='obsoleto',actualizado_en=datetime('now')
            WHERE recuerdo_id=old.id AND usuario_id=new.usuario_id AND estado='activo'; END""")
        conexion.execute("""CREATE TRIGGER IF NOT EXISTS recuerdo_relacion_borrado
            AFTER DELETE ON recuerdos BEGIN UPDATE relaciones SET recuerdo_id=NULL,
            estado='obsoleto',actualizado_en=datetime('now') WHERE recuerdo_id=old.id; END""")
