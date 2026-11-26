"""Consolidación conservadora con historial, linaje y cancelación por grupo."""
from memoria_almacen import _ahora
from memoria_consolidacion_validacion import (
    es_duplicado, incompatibilidad as _incompatibilidad, similitud,
)


def analizar(almacen, usuario_id="local"):
    items = almacen.listar_recuerdos(1000, usuario_id=usuario_id)
    grupos, revision, pares = [], [], []
    usados = set()
    for i, a in enumerate(items):
        if a["id"] in usados:
            continue
        grupo = [a]
        for b in items[i + 1:]:
            if b["id"] in usados or len(grupo) >= 20 or a["tipo_memoria"] != b["tipo_memoria"]:
                continue
            score = similitud(a["contenido"], b["contenido"])
            incompatibilidad = _incompatibilidad(a["contenido"], b["contenido"])
            if incompatibilidad:
                pares.append((a["id"], b["id"], incompatibilidad))
            elif es_duplicado(a["contenido"], b["contenido"]):
                grupo.append(b)
            elif score >= .75:
                revision.append((a["id"], b["id"], score))
        if len(grupo) > 1:
            grupos.append(grupo)
            usados.update(x["id"] for x in grupo)
    return {"grupos": grupos, "revision": revision, "contradicciones": pares}


def consolidar(almacen, usuario_id="local", token_cancelacion=None, progreso=None):
    uid = almacen._uid(usuario_id)
    plan = analizar(almacen, uid)
    hechos, cancelado = [], False
    for indice, grupo in enumerate(plan["grupos"], 1):
        if token_cancelacion is not None and token_cancelacion.is_set():
            cancelado = True
            break
        try:
            with almacen.transaccion():
                if token_cancelacion is not None and token_cancelacion.is_set():
                    raise InterruptedError
                actuales = [almacen.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=? AND estado='activo'",
                    (x["id"], uid)).fetchone() for x in grupo]
                if any(x is None for x in actuales) or any(x["contenido_norm"] != g["contenido_norm"] for x, g in zip(actuales, grupo)):
                    continue
                grupo = [almacen._fila(x) for x in actuales]
                principal = max(grupo, key=lambda x: (x.get("confianza", 0), x.get("actualizado_en", "")))
                if len({x["contenido_norm"] for x in grupo}) == 1:
                    nuevo = principal
                else:
                    texto = " | ".join(dict.fromkeys(x["contenido"] for x in grupo))[:4000]
                    nuevo = almacen.guardar_recuerdo(texto, principal["tipo_memoria"],
                        principal["categoria"], principal["origen"], principal["confianza"],
                        metadatos={**principal.get("metadatos", {}), "consolidado": True},
                        reemplaza_a_id=principal["id"], usuario_id=uid)
                for origen in grupo:
                    almacen.guardar_snapshot(origen, "consolidacion", "fuente preservada")
                    if origen["id"] != nuevo["id"]:
                        almacen.conexion.execute("UPDATE recuerdos SET estado='obsoleto',actualizado_en=? WHERE id=? AND usuario_id=?",
                            (_ahora(), origen["id"], uid))
                        ya_en_linaje = almacen.conexion.execute(
                            "SELECT 1 FROM recuerdos_linaje WHERE recuerdo_id=? AND origen_id=? AND usuario_id=?",
                            (nuevo["id"], origen["id"], uid)).fetchone()
                        if not ya_en_linaje:
                            almacen.conexion.execute("INSERT INTO recuerdos_linaje(recuerdo_id,origen_id,usuario_id,fecha,motivo) VALUES(?,?,?,?,?)",
                                (nuevo["id"], origen["id"], uid, _ahora(), "consolidacion"))
                if token_cancelacion is not None and token_cancelacion.is_set():
                    raise InterruptedError
                hechos.append({"id": nuevo["id"], "origenes": [x["id"] for x in grupo]})
        except InterruptedError:
            cancelado = True
            break
        if progreso:
            progreso(indice, len(plan["grupos"]))
    return {"consolidados": hechos, "revision": plan["revision"],
            "contradicciones": plan["contradicciones"], "cancelado": cancelado}
