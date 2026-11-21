"""Acceso thread-safe al almacén cognitivo SQLite + FTS5."""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

import memoria_esquema
from memoria_transacciones import TransaccionesMemoria
from memoria_modelos import validar_usuario_id
import memoria_almacen_purga
import memoria_tema


def normalizar(texto):
    return " ".join(re.findall(r"\w+", str(texto or "").casefold(), re.UNICODE))


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AlmacenMemoriaCognitiva(TransaccionesMemoria):
    def __init__(self, ruta=":memory:", usuario_id="local"):
        self.ruta = os.fspath(ruta)
        self.usuario_id = validar_usuario_id(usuario_id)
        self._lock = threading.RLock()
        self._cerrado = False
        self._tx_depth = 0
        self.conexion = sqlite3.connect(self.ruta, check_same_thread=False, timeout=10)
        self.conexion.row_factory = sqlite3.Row
        memoria_esquema.inicializar(self.conexion, self.ruta)

    def cerrar(self):
        with self._lock:
            if not self._cerrado:
                self.conexion.close()
                self._cerrado = True

    close = cerrar

    def _uid(self, usuario_id=None):
        return validar_usuario_id(usuario_id if usuario_id is not None else self.usuario_id)

    def _fila(self, fila):
        if fila is None:
            return None
        d = dict(fila)
        try:
            d["metadatos"] = json.loads(d.pop("metadatos_json", "{}"))
        except (TypeError, ValueError):
            d["metadatos"] = {}
        return d

    def guardar_recuerdo(self, contenido, tipo_memoria="semantica", categoria="general",
                         origen="explicito", confianza=0.8, fecha_evento=None,
                         metadatos=None, reemplaza_a_id=None, usuario_id=None):
        uid = self._uid(usuario_id)
        texto = str(contenido or "").strip()
        norm = normalizar(texto)
        if not norm:
            raise ValueError("El recuerdo debe contener texto")
        if tipo_memoria not in ("episodica", "semantica", "procedimental"):
            raise ValueError("tipo_memoria no válido")
        if origen not in ("explicito", "inferido", "multimodal", "migrado", "sistema"):
            raise ValueError("origen no válido")
        conf = float(confianza)
        if not 0 <= conf <= 1:
            raise ValueError("confianza fuera de rango")
        ahora = _ahora()
        meta = json.dumps(metadatos or {}, ensure_ascii=False, default=str)
        with self._lock:
            previo = self.conexion.execute(
                "SELECT * FROM recuerdos WHERE usuario_id=? AND contenido_norm=? AND estado='activo' LIMIT 1", (uid, norm)
            ).fetchone()
            if previo:
                return self._fila(previo)
            if reemplaza_a_id is not None and not self.conexion.execute(
                "SELECT 1 FROM recuerdos WHERE id=? AND usuario_id=?", (reemplaza_a_id, uid)
            ).fetchone():
                raise KeyError(reemplaza_a_id)
            cur = self.conexion.execute("""INSERT INTO recuerdos
                (usuario_id,tipo_memoria,contenido,contenido_norm,categoria,origen,confianza,
                 reemplaza_a_id,fecha_evento,creado_en,actualizado_en,metadatos_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, tipo_memoria, texto, norm, categoria or "general", origen, conf,
                 reemplaza_a_id, fecha_evento, ahora, ahora, meta))
            if not self._tx_depth:
                self.conexion.commit()
            fila = self.conexion.execute("SELECT * FROM recuerdos WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._fila(fila)

    def buscar_texto(self, consulta, limite=10, tipos=None, solo_activos=True, usuario_id=None):
        uid = self._uid(usuario_id)
        tokens = re.findall(r"[\w]+", str(consulta or ""), re.UNICODE)
        limite = max(0, min(int(limite), 500))
        if not limite:
            return []
        where, args = ["r.usuario_id=?"], [uid]
        if solo_activos:
            where.append("r.estado='activo'")
        if tipos:
            ts = tuple(tipos)
            if not ts:
                return []
            where.append("r.tipo_memoria IN (" + ",".join("?" for _ in ts) + ")")
            args.extend(ts)
        base = " FROM recuerdos r "
        filtro = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock:
            if tokens:
                # Cada token va citado; puntuación, comillas y operadores no son sintaxis FTS.
                match = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
                try:
                    sql = "SELECT r.*" + base + "JOIN recuerdos_fts f ON f.rowid=r.id WHERE recuerdos_fts MATCH ?"
                    sql += (" AND " + " AND ".join(where)) if where else ""
                    filas = self.conexion.execute(sql + " ORDER BY r.actualizado_en DESC LIMIT ?", (match, *args, limite)).fetchall()
                    return [self._fila(x) for x in filas]
                except sqlite3.OperationalError:
                    pass
            patron = "%" + "%".join(tokens) + "%" if tokens else "%" + str(consulta or "").strip() + "%"
            sql = "SELECT r.*" + base + filtro
            sql += (" AND " if filtro else " WHERE ") + "r.contenido LIKE ? COLLATE NOCASE"
            filas = self.conexion.execute(sql + " ORDER BY r.actualizado_en DESC LIMIT ?", (*args, patron, limite)).fetchall()
            return [self._fila(x) for x in filas]

    def actualizar_recuerdo(self, recuerdo_id, nuevo_contenido=None, confianza=None,
                            categoria=None, metadatos=None, usuario_id=None):
        uid = self._uid(usuario_id)
        cambios, args = ["actualizado_en=?"], [_ahora()]
        if nuevo_contenido is not None:
            texto = str(nuevo_contenido).strip()
            if not normalizar(texto):
                raise ValueError("El recuerdo debe contener texto")
            cambios += ["contenido=?", "contenido_norm=?"]
            args += [texto, normalizar(texto)]
        if confianza is not None:
            cambios.append("confianza=?")
            conf = float(confianza)
            if not 0 <= conf <= 1:
                raise ValueError("confianza fuera de rango")
            args.append(conf)
        if categoria is not None:
            cambios.append("categoria=?")
            args.append(str(categoria))
        if metadatos is not None:
            cambios.append("metadatos_json=?")
            args.append(json.dumps(metadatos, ensure_ascii=False, default=str))
        args += [int(recuerdo_id), uid]
        with self.transaccion():
            anterior = self.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=?", (int(recuerdo_id), uid)).fetchone()
            if anterior is None:
                return None
            self.guardar_snapshot(anterior, "actualizacion", "campos actualizados")
            self.conexion.execute("UPDATE recuerdos SET " + ",".join(cambios) + " WHERE id=? AND usuario_id=?", args)
            return self._fila(self.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=?",
                                                    (recuerdo_id, uid)).fetchone())

    def reemplazar_recuerdo(self, anterior_id, nuevo_contenido, tipo_memoria=None,
                            origen="explicito", confianza=1.0, usuario_id=None):
        uid = self._uid(usuario_id)
        with self.transaccion():
            anterior = self.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=?",
                                              (anterior_id, uid)).fetchone()
            if anterior is None:
                raise KeyError(anterior_id)
            self.guardar_snapshot(anterior, "reemplazo", "corrección trazable")
            nuevo = self.guardar_recuerdo(nuevo_contenido, tipo_memoria or anterior["tipo_memoria"],
                anterior["categoria"], origen, confianza, reemplaza_a_id=anterior_id, usuario_id=uid)
            if nuevo["id"] != anterior_id:
                self.conexion.execute("UPDATE recuerdos SET estado='obsoleto',actualizado_en=? WHERE id=? AND usuario_id=?",
                                      (_ahora(), anterior_id, uid))
                self.conexion.execute("INSERT INTO recuerdos_linaje(recuerdo_id,origen_id,usuario_id,fecha,motivo) VALUES(?,?,?,?,?)",
                    (nuevo["id"], int(anterior_id), uid, _ahora(), "reemplazo"))
            return nuevo

    def olvidar_por_tema(self, tema, usuario_id=None):
        uid = self._uid(usuario_id)
        if not memoria_tema.terminos(tema):
            return 0
        filas = self.listar_recuerdos(10000, usuario_id=uid)
        ids = [x["id"] for x in filas if memoria_tema.coincide(tema, x.get("contenido"))]
        return self.eliminar_recuerdos_fisicos(ids, uid)

    def eliminar_recuerdo(self, recuerdo_id, fisico=False, usuario_id=None):
        uid = self._uid(usuario_id)
        if fisico:
            return bool(self.eliminar_recuerdos_fisicos([recuerdo_id], uid))
        with self._lock:
            cur = self.conexion.execute("UPDATE recuerdos SET estado='eliminado',actualizado_en=? WHERE id=? AND usuario_id=?",
                (_ahora(), int(recuerdo_id), uid))
            self.conexion.commit()
            return cur.rowcount > 0

    def eliminar_recuerdos_fisicos(self, ids, usuario_id=None):
        return memoria_almacen_purga.eliminar_fisicos(self, ids, usuario_id)

    def eliminar_todos(self, usuario_id=None):
        return memoria_almacen_purga.eliminar_todos(self, usuario_id)

    def contar_recuerdos(self, solo_activos=True, usuario_id=None):
        uid = self._uid(usuario_id)
        sql = "SELECT count(*) FROM recuerdos WHERE usuario_id=?" + (" AND estado='activo'" if solo_activos else "")
        with self._lock:
            return self.conexion.execute(sql, (uid,)).fetchone()[0]

    def listar_recuerdos(self, limite=100, solo_activos=True, tipo_memoria=None, usuario_id=None):
        uid = self._uid(usuario_id)
        where, args = ["usuario_id=?"], [uid]
        if solo_activos:
            where.append("estado='activo'")
        if tipo_memoria:
            where.append("tipo_memoria=?")
            args.append(tipo_memoria)
        sql = "SELECT * FROM recuerdos" + ((" WHERE " + " AND ".join(where)) if where else "")
        sql += " ORDER BY id LIMIT ?"
        with self._lock:
            filas = self.conexion.execute(sql, (*args, max(0, int(limite)))).fetchall()
            return [self._fila(x) for x in filas]

    def marcar_migracion(self, clave, detalles=""):
        with self._lock:
            self.conexion.execute("INSERT OR REPLACE INTO migraciones_estado VALUES(?,?,?)",
                                  (clave, _ahora(), str(detalles)))
            self.conexion.commit()

    def migracion_aplicada(self, clave):
        with self._lock:
            return self.conexion.execute("SELECT 1 FROM migraciones_estado WHERE clave=?", (clave,)).fetchone() is not None
