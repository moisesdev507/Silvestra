"""Persistencia de experiencias en la SQLite cognitiva existente."""
import json
import time
import uuid
from memoria_modelos import validar_usuario_id

DDL = """
CREATE TABLE IF NOT EXISTS experiencias_fase5 (
 usuario_id TEXT NOT NULL,id_experiencia TEXT NOT NULL,clave_patron TEXT NOT NULL,
 exito INTEGER,verificada INTEGER NOT NULL,documento_json TEXT NOT NULL,creado_en REAL NOT NULL,
 PRIMARY KEY(usuario_id,id_experiencia));
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


class AlmacenExperiencias:
    def __init__(self, almacen):
        if not hasattr(almacen, "conexion") or not hasattr(almacen, "_lock"):
            raise TypeError("Se requiere el almacén cognitivo existente")
        self.almacen = almacen
        with almacen.transaccion() as con:
            for sql in DDL.split(";"):
                if sql.strip():
                    con.execute(sql)

    def uid(self, usuario_id=None):
        return validar_usuario_id(usuario_id if usuario_id is not None else self.almacen.usuario_id)

    def guardar_experiencia(self, dato, clave, usuario_id=None):
        uid = self.uid(usuario_id)
        texto = json.dumps(dato, ensure_ascii=False, separators=(",", ":"))
        with self.almacen.transaccion() as con:
            con.execute("INSERT OR IGNORE INTO experiencias_fase5 VALUES(?,?,?,?,?,?,?)",
                (uid, dato["id_experiencia"], clave, None if dato.get("exito") is None else int(dato["exito"]),
                 int(bool(dato.get("verificada"))), texto, time.time()))
        return dato["id_experiencia"]

    def experiencias(self, clave, usuario_id=None):
        uid = self.uid(usuario_id)
        with self.almacen._lock:
            rows = self.almacen.conexion.execute("SELECT documento_json FROM experiencias_fase5 WHERE usuario_id=? AND clave_patron=? ORDER BY creado_en", (uid, clave)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def guardar_aprendizaje(self, dato, usuario_id=None):
        uid = self.uid(usuario_id)
        with self.almacen.transaccion() as con:
            con.execute("""INSERT INTO aprendizajes_experiencia VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(usuario_id,id_aprendizaje) DO UPDATE SET tipo=excluded.tipo,
                estado=excluded.estado,confianza=excluded.confianza,documento_json=excluded.documento_json,
                actualizado_en=excluded.actualizado_en""", (uid,dato["id_aprendizaje"],dato["tipo"],dato["estado"],
                dato["clave_patron"],dato["confianza"],json.dumps(dato,ensure_ascii=False),time.time()))

    def listar_aprendizajes(self, usuario_id=None, estados=("preliminar", "validado")):
        uid = self.uid(usuario_id)
        qs = ",".join("?" for _ in estados)
        with self.almacen._lock:
            rows = self.almacen.conexion.execute("SELECT documento_json FROM aprendizajes_experiencia WHERE usuario_id=? AND estado IN ("+qs+")", (uid,*estados)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def evaluar(self, id_aprendizaje, antes, despues, usuario_id=None):
        uid = self.uid(usuario_id)
        with self.almacen.transaccion() as con:
            con.execute("INSERT INTO evaluaciones_experiencia VALUES(?,?,?,?,?,?,?)",
                (uid,"eval_"+uuid.uuid4().hex,str(id_aprendizaje),float(antes),float(despues),int(float(despues)>float(antes)),time.time()))
        return float(despues) > float(antes)
