"""Migración aditiva e idempotente de los JSON históricos."""
import json
import os

import memoria_filtro


CLAVE = "json_legado_v1"


def _leer(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def migrar_legado_a_sqlite(almacen, directorio_datos, usuario_id=None, token_cancelacion=None):
    """Importa datos JSON sin abrirlos nunca para escritura."""
    uid = almacen._uid(usuario_id)
    clave = f"{CLAVE}:{uid}"
    if almacen.migracion_aplicada(clave):
        return {"migrados": 0, "omitidos": 0, "ya_aplicada": True}
    base = os.path.abspath(os.fspath(directorio_datos))
    memoria = _leer(os.path.join(base, "memoria.json"), {})
    candidatos = []
    if isinstance(memoria, dict):
        for hecho in memoria.get("hechos", []):
            if isinstance(hecho, str):
                candidatos.append((hecho, "semantica", "general", None, {}))
        res = memoria.get("resumenes_tematicos", {})
        if isinstance(res, dict):
            for cat, texto in res.items():
                if isinstance(texto, str) and texto.strip():
                    candidatos.append((texto, "semantica", str(cat), None, {"resumen": True}))
    for nombre, campo in (("ideas.json", "idea"), ("hilos.json", "hilo"), ("correcciones.json", "correccion")):
        filas = _leer(os.path.join(base, nombre), [])
        if not isinstance(filas, list):
            continue
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            if fila.get("estado", "activo") in ("cerrado", "completado", "eliminado", "inactivo"):
                continue
            texto = fila.get("texto") or fila.get("contenido")
            if texto:
                fecha = fila.get("fecha")
                meta = {k: v for k, v in fila.items() if k not in ("texto", "contenido")}
                meta.update({"categoria": campo, "fecha_original": fecha})
                candidatos.append((str(texto), "episodica" if campo == "hilo" else "semantica",
                                   campo, fecha, meta))
    migrados = omitidos = 0
    for texto, tipo, categoria, fecha, meta in candidatos:
        if token_cancelacion is not None and callable(getattr(token_cancelacion, "is_set", None)) and token_cancelacion.is_set():
            return {"migrados": migrados, "omitidos": omitidos, "cancelado": True}
        if not memoria_filtro.es_recuerdo_valido(texto)[0]:
            omitidos += 1
            continue
        try:
            resultado = almacen.guardar_recuerdo(texto, tipo, categoria, "migrado", 0.8,
                                                  fecha_evento=fecha, metadatos=meta, usuario_id=uid)
            if resultado["origen"] == "migrado":
                migrados += 1
            else:
                omitidos += 1
        except (ValueError, TypeError):
            omitidos += 1
    almacen.marcar_migracion(clave, json.dumps({"migrados": migrados, "omitidos": omitidos}))
    return {"migrados": migrados, "omitidos": omitidos, "ya_aplicada": False, "cancelado": False}
