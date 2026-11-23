"""Caché de contexto situacional con TTL corto entre turnos consecutivos."""
from __future__ import annotations

import copy
import threading
import time

TTL_POR_DEFECTO = 8.0
_bloqueo = threading.RLock()
_cache = {}  # id(app) -> (timestamp, motor, snapshot)


def obtener_contexto(app=None, ttl=None):
    """Devuelve el contexto del motor reutilizando el snapshot por unos segundos."""
    ahora = time.time()
    duracion = float(ttl if ttl is not None else TTL_POR_DEFECTO)
    clave = id(app) if app is not None else "global"
    import contexto_motor
    motor = contexto_motor.obtener_motor_contexto(app)
    with _bloqueo:
        entrada = _cache.get(clave)
        if entrada and ahora - entrada[0] < duracion and entrada[1] is motor:
            return copy.deepcopy(entrada[2])
    datos = motor.obtener_contexto()
    with _bloqueo:
        _cache[clave] = (ahora, motor, copy.deepcopy(datos))
    return copy.deepcopy(datos)


def invalidar(app=None):
    """Descarta el snapshot cacheado (o solo el de una app)."""
    with _bloqueo:
        if app is None:
            _cache.clear()
        else:
            _cache.pop(id(app), None)


def estadisticas():
    with _bloqueo:
        return {"entradas": len(_cache), "ttl": TTL_POR_DEFECTO}
