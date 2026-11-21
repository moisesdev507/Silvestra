"""Transacciones componibles e historial inmutable del almacén."""
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TransaccionesMemoria:
    @contextmanager
    def transaccion(self):
        """SAVEPOINT anidado; solo la capa exterior confirma."""
        with self._lock:
            nivel = self._tx_depth
            punto = f"memoria_{nivel}"
            self.conexion.execute("BEGIN IMMEDIATE" if nivel == 0 else f"SAVEPOINT {punto}")
            self._tx_depth += 1
            try:
                yield self.conexion
                self.conexion.execute(f"RELEASE SAVEPOINT {punto}") if nivel else self.conexion.commit()
            except BaseException:
                if nivel:
                    self.conexion.execute(f"ROLLBACK TO SAVEPOINT {punto}")
                    self.conexion.execute(f"RELEASE SAVEPOINT {punto}")
                else:
                    self.conexion.rollback()
                raise
            finally:
                self._tx_depth -= 1

    def guardar_snapshot(self, fila, accion, motivo=""):
        if fila is None:
            return
        datos = self._fila(fila)
        self.conexion.execute("INSERT INTO recuerdos_historial(usuario_id,recuerdo_id,accion,snapshot_json,fecha,motivo) VALUES(?,?,?,?,?,?)",
            (datos["usuario_id"], datos["id"], str(accion), json.dumps(datos, ensure_ascii=False, default=str), _ahora(), str(motivo)[:240]))

    def listar_historial(self, recuerdo_id, usuario_id=None):
        with self._lock:
            return [dict(x) for x in self.conexion.execute("SELECT * FROM recuerdos_historial WHERE recuerdo_id=? AND usuario_id=? ORDER BY id",
                (int(recuerdo_id), self._uid(usuario_id))).fetchall()]

    def listar_linaje(self, recuerdo_id, usuario_id=None):
        with self._lock:
            return [dict(x) for x in self.conexion.execute("SELECT * FROM recuerdos_linaje WHERE recuerdo_id=? AND usuario_id=? ORDER BY id",
                (int(recuerdo_id), self._uid(usuario_id))).fetchall()]

    def purgar_historial(self, recuerdo_id, usuario_id=None):
        with self.transaccion():
            cur = self.conexion.execute("DELETE FROM recuerdos_historial WHERE recuerdo_id=? AND usuario_id=?",
                (int(recuerdo_id), self._uid(usuario_id)))
            return cur.rowcount
