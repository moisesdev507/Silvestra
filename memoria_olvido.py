"""Obsolescencia y olvido controlado; purga ligada a una petición explícita."""
import memoria_politicas
import memoria_tema


def evaluar(almacen, usuario_id="local", umbral_dias=365):
    salida = []
    for item in almacen.listar_recuerdos(10000, usuario_id=usuario_id):
        decision = memoria_politicas.evaluar_retencion(item, umbral_dias=umbral_dias)
        if decision["decision"] != "conservar":
            salida.append({"id": item["id"], **decision})
    return salida


def mantener(almacen, usuario_id="local", token_cancelacion=None, progreso=None,
             umbral_dias=365):
    uid = almacen._uid(usuario_id)
    candidatos = evaluar(almacen, uid, umbral_dias)
    aplicados = []
    for n, item in enumerate(candidatos, 1):
        if token_cancelacion is not None and token_cancelacion.is_set():
            break
        if item["decision"] == "obsoleto":
            with almacen.transaccion():
                fila = almacen.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=? AND estado='activo'",
                    (item["id"], uid)).fetchone()
                if fila:
                    almacen.guardar_snapshot(fila, "obsolescencia", item["motivo"])
                    almacen.conexion.execute("UPDATE recuerdos SET estado='obsoleto',actualizado_en=datetime('now') WHERE id=? AND usuario_id=?",
                        (item["id"], uid))
                    aplicados.append(item["id"])
        if progreso:
            progreso(n, len(candidatos))
    return {"evaluados": len(candidatos), "obsoletos": aplicados,
            "cancelado": bool(token_cancelacion is not None and token_cancelacion.is_set())}


def olvidar(almacen, tema, usuario_id="local", explicito=False):
    if not explicito:
        raise PermissionError("El olvido físico requiere una solicitud explícita")
    uid = almacen._uid(usuario_id)
    if not memoria_tema.terminos(tema):
        return 0
    filas = almacen.listar_recuerdos(10000, usuario_id=uid)
    ids = [f["id"] for f in filas if memoria_tema.coincide(tema, f.get("contenido"))]
    return almacen.eliminar_recuerdos_fisicos(ids, uid)
