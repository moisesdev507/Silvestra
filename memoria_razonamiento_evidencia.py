"""Utilidades de trazabilidad temporal y comparación con respaldo."""
import json
import re


def cronologia(almacen, item, uid, texto, confianza, limite=8):
    salida, vistos, actual = [], set(), item
    for _ in range(max(1, min(limite, 12))):
        rid = actual.get("id")
        if not isinstance(rid, int) or rid in vistos:
            break
        vistos.add(rid)
        snaps = []
        try:
            for h in almacen.listar_historial(rid, uid)[:8]:
                snap = json.loads(h.get("snapshot_json") or "{}")
                snaps.append({"accion": h.get("accion"), "fecha": h.get("fecha"),
                    "contenido": texto(snap.get("contenido"), 240), "origen": snap.get("origen"),
                    "confianza": confianza(snap.get("confianza")), "estado": snap.get("estado")})
        except Exception:
            snaps = []
        salida.append({"id": rid, "estado": actual.get("estado", "activo"),
            "fecha": str(actual.get("actualizado_en") or actual.get("creado_en") or "")[:32],
            "reemplaza_a_id": actual.get("reemplaza_a_id"), "snapshots": snaps})
        parent = actual.get("reemplaza_a_id")
        if not parent:
            break
        fila = almacen.conexion.execute("SELECT * FROM recuerdos WHERE id=? AND usuario_id=?", (int(parent), uid)).fetchone()
        if fila is None:
            break
        actual = almacen._fila(fila)
    return salida


def comparar(consulta, evidencia):
    opciones = re.search(r"\b([\wáéíóúñ+#.-]+)\s+o\s+([\wáéíóúñ+#.-]+)\b", str(consulta or ""), re.I)
    if not opciones:
        return [], False
    comparables = []
    for opcion in (opciones.group(1).strip(), opciones.group(2).strip()):
        norm = opcion.casefold().strip(" ?¿.,")
        refs = [e for e in evidencia if isinstance(e.get("id"), int) and norm and
                norm in e["contenido"].casefold() and e.get("confianza") is not None]
        if refs:
            comparables.append({"opcion": opcion, "recuerdo_ids": [e["id"] for e in refs],
                "confianza": max(e["confianza"] for e in refs), "comparacion": "respaldo encontrado"})
    return comparables, True
