"""Analiza intención, tiempo y referencias incompletas de una consulta."""
import datetime
import re

import memoria_busqueda as mb
import memoria_tiempo as mt


def analizar(consulta, usuario_id="local", trabajo=(), contexto=""):
    original = str(consulta or "").strip()
    texto = mt.normalizar_texto(original)
    temporal = any(x in texto for x in ("ayer", "hoy", "anoche", "esta semana", "la semana pasada"))
    if temporal:
        intencion = "temporal"
    elif any(x in texto for x in ("como solucion", "como arregl", "pasos", "procedimiento")):
        intencion = "procedimental"
    elif any(x in texto for x in ("proyecto", "decid", "continu", "dejamos", "estabamos")):
        intencion = "proyecto_estado"
    else:
        intencion = "conceptual"
    tipos = {"temporal": ("episodica",), "procedimental": ("procedimental",),
             "proyecto_estado": ("episodica", "semantica", "trabajo"),
             "conceptual": ("semantica", "episodica", "procedimental")}[intencion]
    rango = None
    hoy = mt.obtener_fecha_actual()
    if "ayer" in texto or "anoche" in texto:
        d = hoy - datetime.timedelta(days=1)
        rango = (d.isoformat(), d.isoformat())
    elif "hoy" in texto:
        rango = (hoy.isoformat(), hoy.isoformat())
    elif "esta semana" in texto:
        inicio = hoy - datetime.timedelta(days=hoy.weekday())
        rango = (inicio.isoformat(), hoy.isoformat())
    anafora = any(x in texto for x in ("este proyecto", "ese problema", "lo dejamos", "donde lo dejamos", "eso", "aquello"))
    resolucion = None
    if anafora:
        for item in reversed(list(trabajo or [])):
            contenido = getattr(item, "contenido", "")
            if getattr(item, "usuario_id", usuario_id) == usuario_id and isinstance(contenido, str) and contenido.strip():
                resolucion = contenido.strip()[:240]
                break
        if resolucion is None and str(contexto or "").strip():
            resolucion = str(contexto).strip()[:240]
    palabras = mb.extraer_palabras_clave(texto)
    return {"consulta": original, "normalizada": texto, "intencion": intencion,
            "terminos": sorted(palabras), "tipos": tipos, "rango_temporal": rango,
            "anaforica": anafora, "resolucion": resolucion,
            "ambigua": bool(anafora and not resolucion) or not bool(palabras),
            "contexto_insuficiente": bool(anafora and not resolucion)}
