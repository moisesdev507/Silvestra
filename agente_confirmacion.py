"""Confirmación humana real, con TTL corto, para acciones de riesgo alto."""
import threading
import time

import verificacion_modelo as vm
import voz_gracia as vg

TTL_CONFIRMACION_SEG = 40.0
TTL_MAXIMO_SEG = 45.0
CANALES_INTERACTIVOS = frozenset({"microfono", "voz", "chat", "telegram"})
NEGACIONES = frozenset({
    "no", "nop", "nel", "cancelar", "cancela", "cancelado", "rechazo",
    "rechazar", "deten", "detener", "para", "alto", "nada",
})


class Pendiente:
    __slots__ = ("nombre", "descripcion", "datos", "canal", "creado",
                 "evento", "respuesta")

    def __init__(self, nombre, descripcion, datos, canal):
        self.nombre = str(nombre or "esa acción")[:60]
        self.descripcion = str(descripcion or "")[:120]
        self.datos = vm.sanitizar_datos(datos if isinstance(datos, dict) else {})
        self.canal = str(canal or "desconocido")
        self.creado = time.time()
        self.evento = threading.Event()
        self.respuesta = None

    def expirado(self, ahora=None, ttl=TTL_CONFIRMACION_SEG):
        ahora = time.time() if ahora is None else float(ahora)
        return ahora - self.creado > float(ttl)


_PENDIENTES = {}
_BLOQUEO = threading.RLock()


def _clave(app):
    return id(app) if app is not None else 0


def _decir(app, texto, emocion="seria"):
    cola = getattr(app, "cola", None)
    if cola is not None and hasattr(cola, "put"):
        cola.put(("hablar", (texto, emocion)))
        return True
    decir = getattr(app, "decir", None)
    if callable(decir):
        decir(texto)
        return True
    return False


def es_interactivo(app, canal=None, interactivo=None):
    """Los canales sin respuesta de usuario se bloquean siempre."""
    if interactivo is not None:
        return bool(interactivo)
    canal = str(canal or getattr(app, "origen_entrada_actual", "") or "").lower()
    return canal in CANALES_INTERACTIVOS


def pendiente(app):
    with _BLOQUEO:
        return _PENDIENTES.get(_clave(app))


def hay_pendiente(app):
    return pendiente(app) is not None


def cancelar(app):
    """Cierra el pendiente y despierta al hilo que esperaba la respuesta."""
    with _BLOQUEO:
        item = _PENDIENTES.pop(_clave(app), None)
    if item is None:
        return False
    item.respuesta = False
    item.evento.set()
    return True


def resolver(app, texto, ahora=None):
    """Devuelve 'aprobado', 'rechazado' o None si el texto no confirma."""
    item = pendiente(app)
    if item is None:
        return None
    if item.expirado(ahora=ahora):
        cancelar(app)
        return None
    limpio = vg.normalizar(texto).strip("¿?¡!.,;:…\"'")
    if not limpio:
        return None
    palabras = {p.strip("¿?¡!.,;:…\"'") for p in limpio.split()}
    if palabras & NEGACIONES:
        item.respuesta = False
    elif vg.es_confirmacion_breve(limpio):
        item.respuesta = True
    else:
        return None
    item.evento.set()
    return "aprobado" if item.respuesta else "rechazado"


def solicitar(app, nombre, descripcion="", datos=None, canal=None,
              ttl=TTL_CONFIRMACION_SEG, interactivo=None):
    """Pregunta y espera hasta ttl. Solo devuelve True con confirmación humana."""
    if not es_interactivo(app, canal=canal, interactivo=interactivo):
        return False
    try:
        espera = min(max(0.01, float(ttl)), TTL_MAXIMO_SEG)
    except (TypeError, ValueError):
        espera = TTL_CONFIRMACION_SEG
    clave = _clave(app)
    item = Pendiente(nombre, descripcion, datos, canal)
    with _BLOQUEO:
        if clave in _PENDIENTES and not _PENDIENTES[clave].expirado():
            return False
        _PENDIENTES[clave] = item
    vg.registrar_pregunta(app)
    _decir(app, f"¿Confirmas que ejecute {item.nombre}?")
    despertado = item.evento.wait(espera)
    with _BLOQUEO:
        if _PENDIENTES.get(clave) is item:
            del _PENDIENTES[clave]
    return bool(despertado and item.respuesta)
