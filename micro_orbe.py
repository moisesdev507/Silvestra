"""Detección de clic simple sobre el orbe, sin importar Qt ni tocar motores.

El evento se encola hacia la aplicación; la decisión de abrir o cerrar el
micrófono Live la toma ``live_orquestador`` fuera del hilo de la interfaz.
"""
import time

UMBRAL_CLIC_PX = 8
UMBRAL_DOBLE_CLIC_S = 0.35


def registrar_pulsacion(cara, pos):
    """Guarda el origen del clic y marca el segundo clic del doble clic."""
    ahora = time.monotonic()
    anterior = getattr(cara, "_orbe_pulsacion", None)
    if anterior is not None and ahora - anterior[2] < UMBRAL_DOBLE_CLIC_S:
        cara._orbe_pulsacion = None
        cara._orbe_doble = True
        return
    cara._orbe_doble = False
    cara._orbe_pulsacion = (pos.x(), pos.y(), ahora)


def finalizar_pulsacion(cara, pos):
    """Encola ``toggle_micro_live`` solo si fue un clic simple, no un arrastre."""
    if getattr(cara, "_orbe_doble", False):
        return False
    inicio = getattr(cara, "_orbe_pulsacion", None)
    cara._orbe_pulsacion = None
    if inicio is None:
        return False
    if (abs(pos.x() - inicio[0]) > UMBRAL_CLIC_PX
            or abs(pos.y() - inicio[1]) > UMBRAL_CLIC_PX):
        return False
    app = getattr(cara, "silvestra_app", None) or getattr(cara, "_ref_app", None)
    if app is None or not hasattr(app, "cola"):
        return False
    app.cola.put(("toggle_micro_live", None))
    return True
