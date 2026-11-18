"""Hilos abiertos y pendientes: temas que Silvestra quiere retomar en otra conversación."""
import difflib
import json
import os
import time

import acciones

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hilos.json")


def cargar():
    try:
        if os.path.exists(RUTA):
            with open(RUTA, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def guardar(datos):
    try:
        with open(RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def anotar_pendiente(texto):
    """Guarda un tema o hilo abierto pendiente."""
    texto = (texto or "").strip()
    if not texto:
        return
    datos = cargar()
    for d in datos:
        if difflib.SequenceMatcher(None, d.get("texto", "").lower(), texto.lower()).ratio() > 0.7:
            d["estado"] = "abierto"
            d["fecha"] = time.strftime("%Y-%m-%d")
            break
    else:
        datos.append({"texto": texto, "estado": "abierto", "fecha": time.strftime("%Y-%m-%d")})
    guardar(datos)


def cerrar_pendiente(texto):
    """Marca como resuelto o cerrado un tema pendiente."""
    texto = (texto or "").strip().lower()
    if not texto:
        return
    datos = cargar()
    for d in datos:
        if d.get("estado", "abierto") == "abierto":
            d_txt = d.get("texto", "").lower()
            if texto in d_txt or d_txt in texto or difflib.SequenceMatcher(None, d_txt, texto).ratio() > 0.6:
                d["estado"] = "resuelto"
                d["fecha_cierre"] = time.strftime("%Y-%m-%d")
                break
    guardar(datos)


def resumen(maximo=6):
    """Devuelve un texto con los hilos pendientes para el prompt del cerebro."""
    abiertos = [d for d in cargar() if d.get("estado", "abierto") == "abierto"][:maximo]
    if not abiertos:
        return "ninguno todavía"
    return "; ".join(d["texto"] for d in abiertos)


def instalar(app):
    acciones.registrar(
        "anotar_pendiente",
        anotar_pendiente,
        "anota un tema pendiente o hilo abierto para retomar en otra conversación. "
        "Escribe: ACCION: anotar_pendiente | tema pendiente a retomar",
        con_texto=True,
    )
    acciones.registrar(
        "cerrar_pendiente",
        cerrar_pendiente,
        "marca como resuelto o cerrado un tema pendiente del que ya hablaron. "
        "Escribe: ACCION: cerrar_pendiente | tema resuelto",
        con_texto=True,
    )
