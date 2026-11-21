"""Repositorio de planes por usuario en la conexión cognitiva ya abierta."""
import json
import time

import planificador_modelo as pm
from memoria_modelos import validar_usuario_id

DDL = """
CREATE TABLE IF NOT EXISTS planes_fase5 (
 usuario_id TEXT NOT NULL, id_plan TEXT NOT NULL, estado TEXT NOT NULL,
 documento_json TEXT NOT NULL, creado_en REAL NOT NULL, actualizado_en REAL NOT NULL,
 PRIMARY KEY(usuario_id,id_plan));
CREATE INDEX IF NOT EXISTS idx_planes_fase5_usuario_estado
 ON planes_fase5(usuario_id,estado,actualizado_en);
"""
_CAMPOS_TEXTO = {"titulo", "objetivo_general", "requisitos", "restricciones", "preguntas_pendientes",
    "nombre", "descripcion", "detalle", "motivo_bloqueo", "justificacion", "evidencia_requerida",
    "ventajas", "desventajas", "medida_preventiva", "principal", "secundarios",
    "informacion_faltante", "evidencia"}


def _textos_plan(dato, campo=""):
    if isinstance(dato, dict):
        return [s for k, v in dato.items() for s in _textos_plan(v, k)]
    if isinstance(dato, (list, tuple)):
        return [s for v in dato for s in _textos_plan(v, campo)]
    return [dato] if campo in _CAMPOS_TEXTO and isinstance(dato, str) else []


class AlmacenPlanes:
    def __init__(self, almacen):
        if not hasattr(almacen, "conexion") or not callable(getattr(almacen, "transaccion", None)):
            raise TypeError("Se requiere el almacén SQLite cognitivo existente")
        self.almacen = almacen
        with almacen.transaccion() as con:
            for stmt in DDL.split(";"):
                if stmt.strip():
                    con.execute(stmt)

    def _uid(self, usuario_id):
        return validar_usuario_id(usuario_id or self.almacen.usuario_id)

    def cargar(self, usuario_id=None):
        uid = self._uid(usuario_id)
        with self.almacen._lock:
            rows = self.almacen.conexion.execute(
                "SELECT id_plan,documento_json FROM planes_fase5 WHERE usuario_id=? ORDER BY actualizado_en",
                (uid,)).fetchall()
        planes, extras = {}, {}
        for row in rows:
            try:
                doc = json.loads(row["documento_json"])
                plan = pm.PlanObjetivo.de_dict(doc["plan"])
                planes[plan.id_plan] = plan
                extras[plan.id_plan] = doc.get("analisis", {})
            except (ValueError, TypeError, KeyError):
                continue
        return planes, extras

    def guardar_lote(self, planes, analisis=None, usuario_id=None):
        uid = self._uid(usuario_id)
        analisis = analisis or {}
        ahora = time.time()
        filas = []
        for plan_id, plan in planes.items():
            doc = {"plan": plan.a_dict(), "analisis": analisis.get(plan_id, {})}
            texto = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
            try:
                import memoria_filtro
                if memoria_filtro._contiene_secreto(" ".join(_textos_plan(doc))):
                    raise ValueError("Plan contiene un valor secreto; no se persiste")
            except ImportError:
                pass
            if len(texto.encode("utf-8")) > 200000:
                raise ValueError("Plan supera el tamaño persistible")
            filas.append((uid, str(plan_id), plan.estado, texto, plan.creado_en, ahora))
        with self.almacen.transaccion() as con:
            con.executemany("""INSERT INTO planes_fase5
                (usuario_id,id_plan,estado,documento_json,creado_en,actualizado_en)
                VALUES(?,?,?,?,?,?) ON CONFLICT(usuario_id,id_plan) DO UPDATE SET
                estado=excluded.estado,documento_json=excluded.documento_json,
                actualizado_en=excluded.actualizado_en""", filas)
        return len(filas)

    def guardar(self, plan, analisis=None, usuario_id=None):
        return self.guardar_lote({plan.id_plan: plan}, {plan.id_plan: analisis or {}}, usuario_id)

    def obtener(self, id_plan, usuario_id=None):
        planes, extras = self.cargar(usuario_id)
        return (planes.get(str(id_plan)), extras.get(str(id_plan)))

    def listar(self, usuario_id=None, estado=None):
        uid = self._uid(usuario_id)
        with self.almacen._lock:
            sql = "SELECT documento_json FROM planes_fase5 WHERE usuario_id=?"
            args = [uid]
            if estado:
                sql += " AND estado=?"
                args.append(str(estado))
            rows = self.almacen.conexion.execute(sql + " ORDER BY actualizado_en", args).fetchall()
        salida = []
        for row in rows:
            try:
                salida.append(pm.PlanObjetivo.de_dict(json.loads(row[0])["plan"]))
            except (ValueError, TypeError, KeyError):
                continue
        return salida
