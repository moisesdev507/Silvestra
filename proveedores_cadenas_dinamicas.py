"""Reordenamiento dinámico de cadenas de proveedores según salud observada."""
from __future__ import annotations

import time

import proveedores_salud as salud


def _datos(registro, nombre, modelo):
    try:
        return registro.obtener_salud(nombre, modelo)
    except Exception:
        return {"intentos": 0}


def _penalizacion(datos, tarea, carril, ahora):
    """Penalización en [0, ~1.5]; cero significa sin historial (orden estático)."""
    intentos = int(datos.get("intentos") or 0)
    if intentos <= 0:
        return 0.0
    errores = int(datos.get("errores") or 0)
    errores_429 = int(datos.get("errores_429") or 0)
    peso_error = 0.75 if carril == "pro" else 0.5
    peso_lat = 0.25 if (carril == "pro" and tarea != "voz") else 0.6
    penal = (errores / intentos) * peso_error + (errores_429 / intentos) * 0.4
    ttft = datos.get("ewma_ttft")
    if ttft:
        penal += min(peso_lat, max(0.0, (float(ttft) - 0.4) / 8.0))
    ts_fallo = datos.get("ts_fallo") or 0
    if ts_fallo:
        edad = ahora - float(ts_fallo)
        if 0 <= edad < 120:
            penal += 0.35 * (1.0 - edad / 120.0)
    return min(penal, 1.5)


def reordenar(candidatos, tarea="charla", carril="rapido", registro=None):
    """Ordena por salud sin alterar el hedge top-2; sin historial conserva el orden."""
    if not candidatos:
        return []
    reg = registro or salud
    ahora = time.time()
    puntuados = []
    for idx, prov in enumerate(candidatos):
        nombre = prov.get("nombre", "")
        modelos = prov.get("modelos_activos") or prov.get("modelos") or []
        modelo = modelos[0] if modelos else None
        penal = _penalizacion(_datos(reg, nombre, modelo), tarea, carril, ahora)
        puntuados.append((-penal, -idx, prov))
    puntuados.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in puntuados]
