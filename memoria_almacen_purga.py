"""Purga atómica y aislada de datos relacionados con recuerdos."""


def eliminar_fisicos(almacen, ids, usuario_id):
    uid = almacen._uid(usuario_id)
    valores = list(dict.fromkeys(int(x) for x in ids))
    if not valores:
        return 0
    with almacen.transaccion():
        slots = ",".join("?" for _ in valores)
        filas = almacen.conexion.execute(
            f"SELECT id FROM recuerdos WHERE usuario_id=? AND id IN ({slots})", (uid, *valores)
        ).fetchall()
        reales = [int(x[0]) for x in filas]
        for rid in reales:
            almacen.conexion.execute("DELETE FROM recuerdos_historial WHERE recuerdo_id=? AND usuario_id=?", (rid, uid))
            almacen.conexion.execute("DELETE FROM recuerdos_linaje WHERE usuario_id=? AND (recuerdo_id=? OR origen_id=?)", (uid, rid, rid))
            almacen.conexion.execute("UPDATE relaciones SET recuerdo_id=NULL,estado='obsoleto',actualizado_en=datetime('now') WHERE recuerdo_id=? AND usuario_id=?", (rid, uid))
            almacen.conexion.execute("UPDATE recuerdos SET reemplaza_a_id=NULL WHERE reemplaza_a_id=? AND usuario_id=?", (rid, uid))
            almacen.conexion.execute("DELETE FROM recuerdos WHERE id=? AND usuario_id=?", (rid, uid))
        return len(reales)


def eliminar_todos(almacen, usuario_id):
    uid = almacen._uid(usuario_id)
    with almacen.transaccion():
        ids = [x[0] for x in almacen.conexion.execute("SELECT id FROM recuerdos WHERE usuario_id=?", (uid,)).fetchall()]
        return eliminar_fisicos(almacen, ids, uid)
