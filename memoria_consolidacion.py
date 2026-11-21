"""Consolidación conservadora con historial, linaje y cancelación por grupo."""
import re
from memoria_almacen import _ahora


def _tokens(texto):
    return set(re.findall(r"\w+", str(texto or "").casefold()))


def similitud(a, b):
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / max(1, len(x | y))


def _contradictorios(a, b):
    x, y = _tokens(a), _tokens(b)
    return bool(x & y) and (("no" in x) != ("no" in y))


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
            if _contradictorios(a["contenido"], b["contenido"]):
                pares.append((a["id"], b["id"], "contradiccion"))
            elif score >= .90:
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
