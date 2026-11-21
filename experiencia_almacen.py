"""Persistencia de experiencias en la SQLite cognitiva existente."""
import json
import time
import uuid
import experiencia_esquema
from memoria_modelos import validar_usuario_id


class AlmacenExperiencias:
    def __init__(self, almacen):
        if not hasattr(almacen, "conexion") or not hasattr(almacen, "_lock"):
            raise TypeError("Se requiere el almacén cognitivo existente")
        self.almacen = almacen
        experiencia_esquema.inicializar(almacen)

    def uid(self, usuario_id=None):
        return validar_usuario_id(usuario_id if usuario_id is not None else self.almacen.usuario_id)

    def guardar_experiencia(self, dato, clave, origen_clave="", usuario_id=None):
        uid = self.uid(usuario_id)
        origen_clave=str(origen_clave or "")[:360]
        texto = json.dumps(dato, ensure_ascii=False, separators=(",", ":"))
        with self.almacen.transaccion() as con:
            previo=con.execute("SELECT id_experiencia,verificada FROM experiencias_fase5 WHERE usuario_id=? AND origen_clave=?",(uid,origen_clave)).fetchone() if origen_clave else None
            if previo:
                if previo["verificada"] and not dato.get("verificada"):
                    dato["id_experiencia"]=previo["id_experiencia"]
                    return dato["id_experiencia"]
                dato["id_experiencia"]=previo["id_experiencia"]
                texto=json.dumps(dato,ensure_ascii=False,separators=(",",":"))
                con.execute("UPDATE experiencias_fase5 SET clave_patron=?,exito=?,verificada=?,documento_json=?,creado_en=? WHERE usuario_id=? AND origen_clave=?",
                    (clave,None if dato.get("exito") is None else int(dato["exito"]),int(bool(dato.get("verificada"))),texto,time.time(),uid,origen_clave))
            else:
                con.execute("INSERT INTO experiencias_fase5(usuario_id,id_experiencia,clave_patron,origen_clave,exito,verificada,documento_json,creado_en) VALUES(?,?,?,?,?,?,?,?)",
                    (uid,dato["id_experiencia"],clave,origen_clave,None if dato.get("exito") is None else int(dato["exito"]),int(bool(dato.get("verificada"))),texto,time.time()))
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
