"""DDL idempotente y migración aditiva del almacén experiencial."""
import json

DDL="""
CREATE TABLE IF NOT EXISTS experiencias_fase5 (
 usuario_id TEXT NOT NULL,id_experiencia TEXT NOT NULL,clave_patron TEXT NOT NULL,
 origen_clave TEXT NOT NULL DEFAULT '',exito INTEGER,verificada INTEGER NOT NULL,
 documento_json TEXT NOT NULL,creado_en REAL NOT NULL,PRIMARY KEY(usuario_id,id_experiencia));
CREATE INDEX IF NOT EXISTS idx_exp_usuario_patron ON experiencias_fase5(usuario_id,clave_patron);
CREATE TABLE IF NOT EXISTS aprendizajes_experiencia (
 usuario_id TEXT NOT NULL,id_aprendizaje TEXT NOT NULL,tipo TEXT NOT NULL,estado TEXT NOT NULL,
 clave_patron TEXT NOT NULL,confianza REAL NOT NULL,documento_json TEXT NOT NULL,actualizado_en REAL NOT NULL,
 PRIMARY KEY(usuario_id,id_aprendizaje));
CREATE INDEX IF NOT EXISTS idx_apr_usuario_estado ON aprendizajes_experiencia(usuario_id,estado,tipo);
CREATE TABLE IF NOT EXISTS evaluaciones_experiencia (
 usuario_id TEXT NOT NULL,id_evaluacion TEXT NOT NULL,id_aprendizaje TEXT NOT NULL,
 antes REAL NOT NULL,despues REAL NOT NULL,mejora INTEGER NOT NULL,creado_en REAL NOT NULL,
 PRIMARY KEY(usuario_id,id_evaluacion));
"""


def inicializar(almacen):
    with almacen.transaccion() as con:
        for stmt in DDL.split(";"):
            if stmt.strip(): con.execute(stmt)
        cols={r[1] for r in con.execute("PRAGMA table_info(experiencias_fase5)")}
        if "origen_clave" not in cols:
            con.execute("ALTER TABLE experiencias_fase5 ADD COLUMN origen_clave TEXT NOT NULL DEFAULT ''")
        rows=con.execute("SELECT usuario_id,id_experiencia,documento_json FROM experiencias_fase5 WHERE origen_clave='' ").fetchall()
        for row in rows:
            try:
                d=json.loads(row["documento_json"]); key=str(d.get("origen_clave") or "")
                ids=[str(x) for x in d.get("origen_ids",()) if x is not None]
                if not key and len(ids)>=3: key=f"plan:{ids[-2]}|tarea:{ids[-1]}"
                elif not key and len(ids)==2: key=f"plan:{ids[0]}|tarea:{ids[1]}"
                elif not key and ids: key="origen:"+"|".join(sorted(ids))
            except (ValueError,TypeError): key=""
            if key and not con.execute("SELECT 1 FROM experiencias_fase5 WHERE usuario_id=? AND origen_clave=?",(row["usuario_id"],key)).fetchone():
                con.execute("UPDATE experiencias_fase5 SET origen_clave=? WHERE usuario_id=? AND id_experiencia=?",(key,row["usuario_id"],row["id_experiencia"]))
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_exp_usuario_origen ON experiencias_fase5(usuario_id,origen_clave) WHERE origen_clave<>''")
