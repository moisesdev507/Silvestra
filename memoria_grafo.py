"""Grafo SQLite multiusuario con aristas trazables y recorridos acotados."""
import re
import unicodedata
from datetime import datetime, timezone

from memoria_modelos import validar_usuario_id
import memoria_grafo_recorrido as recorrido
import memoria_filtro

TIPOS_NODO = {"recuerdo", "persona", "perfil", "proyecto", "acontecimiento", "concepto",
              "tecnologia", "objetivo", "tarea", "experiencia", "procedimiento"}
TIPOS_RELACION = {"pertenece_a", "esta_relacionado_con", "utiliza", "depende_de", "es_parte_de",
                  "fue_creado_por", "ocurrio_antes_de", "ocurrio_despues_de", "es_version_de",
                  "contribuye_a", "tiene_como_objetivo", "es_consecuencia_de"}
ESTADOS = {"activo", "contradicho", "obsoleto", "eliminado"}


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", t, re.UNICODE))


class GrafoConocimiento:
    def __init__(self, almacen):
        self.almacen = almacen
        self.conexion = almacen.conexion
        self._lock = almacen._lock

    def _uid(self, usuario_id=None):
        return self.almacen._uid(usuario_id)

    def crear_nodo(self, nombre, tipo="concepto", usuario_id=None):
        uid, nombre = self._uid(usuario_id), str(nombre or "").strip()
        norm = normalizar(nombre)
        if not norm or len(nombre) > 240 or tipo not in TIPOS_NODO:
            raise ValueError("nodo inválido")
        privado = memoria_filtro.normalizar_para_filtro(nombre)
        if any(p in privado for p in memoria_filtro.PALABRAS_PRIVADAS):
            raise ValueError("nodo bloqueado por privacidad")
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self.conexion.execute("INSERT OR IGNORE INTO entidades(usuario_id,nombre,nombre_norm,tipo,creado_en) VALUES(?,?,?,?,?)",
                                  (uid, nombre, norm, tipo, ahora))
            self.conexion.commit()
            row = self.conexion.execute("SELECT * FROM entidades WHERE usuario_id=? AND nombre_norm=?", (uid, norm)).fetchone()
            return dict(row)

    def buscar_nodos(self, consulta, usuario_id=None, limite=20):
        return recorrido.buscar_nodos(self, consulta, usuario_id, limite)

    def obtener_nodo(self, nodo_id, usuario_id=None):
        with self._lock:
            r = self.conexion.execute("SELECT * FROM entidades WHERE id=? AND usuario_id=?",
                                      (int(nodo_id), self._uid(usuario_id))).fetchone()
            return dict(r) if r else None

    def _validar_extremo(self, nodo_id, uid):
        if not self.conexion.execute("SELECT 1 FROM entidades WHERE id=? AND usuario_id=?", (nodo_id, uid)).fetchone():
            raise KeyError(nodo_id)

    def crear_relacion(self, origen_id, tipo_relacion, destino_id, usuario_id=None,
                       dirigida=True, origen="inferida", confianza=.5, estado="activo",
                       recuerdo_id=None, origen_dato=None):
        uid = self._uid(usuario_id)
        if tipo_relacion not in TIPOS_RELACION or origen not in ("explicita", "inferida") or estado not in ESTADOS:
            raise ValueError("relación inválida")
        confianza = float(confianza)
        if not 0 <= confianza <= 1:
            raise ValueError("confianza fuera de rango")
        a, b = int(origen_id), int(destino_id)
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._validar_extremo(a, uid); self._validar_extremo(b, uid)
            if recuerdo_id is not None:
                rec = self.conexion.execute("SELECT estado FROM recuerdos WHERE id=? AND usuario_id=?",
                                             (int(recuerdo_id), uid)).fetchone()
                if rec is None or rec[0] != "activo":
                    raise KeyError(recuerdo_id)
            if not dirigida and b < a:
                a, b = b, a
            self.conexion.execute("""INSERT OR IGNORE INTO relaciones
                (usuario_id,origen_id,tipo_relacion,destino_id,peso,origen_dato,creado_en,recuerdo_id,
                 dirigida,origen,confianza,estado,actualizado_en)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, a, tipo_relacion, b, confianza, origen_dato, ahora, recuerdo_id,
                 int(bool(dirigida)), origen, confianza, estado, ahora))
            self.conexion.commit()
            return self.conexion.execute("""SELECT * FROM relaciones WHERE usuario_id=? AND origen_id=?
                AND tipo_relacion=? AND destino_id=? AND dirigida=? AND COALESCE(recuerdo_id,0)=COALESCE(?,0)
                AND origen=? AND COALESCE(origen_dato,'')=COALESCE(?,'') AND estado=? ORDER BY id LIMIT 1""",
                (uid, a, tipo_relacion, b, int(bool(dirigida)), recuerdo_id, origen, origen_dato, estado)).fetchone()

    def listar_relaciones(self, nodo_id=None, usuario_id=None, estado="activo", limite=100):
        uid, params = self._uid(usuario_id), [self._uid(usuario_id)]
        sql = "SELECT r.*,a.nombre AS nombre_origen,b.nombre AS nombre_destino FROM relaciones r JOIN entidades a ON a.id=r.origen_id AND a.usuario_id=r.usuario_id JOIN entidades b ON b.id=r.destino_id AND b.usuario_id=r.usuario_id WHERE r.usuario_id=?"
        if estado is not None:
            sql += " AND r.estado=?"; params.append(estado)
        if nodo_id is not None:
            sql += " AND (r.origen_id=? OR r.destino_id=?)"; params.extend((int(nodo_id), int(nodo_id)))
        sql += " ORDER BY r.id LIMIT ?"; params.append(max(0, min(int(limite), 500)))
        with self._lock:
            return [dict(r) for r in self.conexion.execute(sql, params).fetchall()]

    def actualizar_relacion(self, relacion_id, usuario_id=None, **campos):
        uid = self._uid(usuario_id); permitidos = {"confianza", "estado", "origen", "tipo_relacion"}
        if not campos or set(campos) - permitidos:
            raise ValueError("campos de relación inválidos")
        if "estado" in campos and campos["estado"] not in ESTADOS:
            raise ValueError("estado inválido")
        if "origen" in campos and campos["origen"] not in ("explicita", "inferida"):
            raise ValueError("origen inválido")
        if "tipo_relacion" in campos and campos["tipo_relacion"] not in TIPOS_RELACION:
            raise ValueError("tipo inválido")
        if "confianza" in campos and not 0 <= float(campos["confianza"]) <= 1:
            raise ValueError("confianza fuera de rango")
        campos["actualizado_en"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sql = "UPDATE relaciones SET " + ",".join(k+"=?" for k in campos) + " WHERE id=? AND usuario_id=?"
        with self._lock:
            self.conexion.execute(sql, (*campos.values(), int(relacion_id), uid)); self.conexion.commit()
            row = self.conexion.execute("SELECT * FROM relaciones WHERE id=? AND usuario_id=?", (relacion_id, uid)).fetchone()
            return dict(row) if row else None

    def eliminar_relacion(self, relacion_id, usuario_id=None):
        return self.actualizar_relacion(relacion_id, usuario_id, estado="eliminado") is not None

    def marcar_recuerdo_obsoleto(self, recuerdo_id, usuario_id=None):
        uid = self._uid(usuario_id); ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self.conexion.execute("UPDATE relaciones SET estado='obsoleto',actualizado_en=? WHERE recuerdo_id=? AND usuario_id=? AND estado='activo'",
                                        (ahora, int(recuerdo_id), uid)); self.conexion.commit()
            return cur.rowcount

    def recorrer(self, nodo_id, usuario_id=None, max_profundidad=2, max_resultados=20):
        return recorrido.recorrer(self, nodo_id, usuario_id, max_profundidad, max_resultados)

    def relaciones_de_recuerdos(self, ids, usuario_id=None, confianza_min=.75, limite=12):
        return recorrido.relaciones_de_recuerdos(self, ids, usuario_id, confianza_min, limite)
