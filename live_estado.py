"""Transiciones de estado de Live sin tocar widgets ni bloquear audio."""


def reanudar_escucha(sesion):
    """Vuelve a 'escuchando' tras interrupciones, turnos o herramientas."""
    puente = getattr(sesion, "_puente_webrtc", None)
    if puente is not None and getattr(puente, "dormida", False):
        return False
    if puente is not None and callable(getattr(puente, "activar_escucha", None)):
        puente.activar_escucha()
    notificar = getattr(sesion, "_notificar_estado", None)
    if callable(notificar):
        try:
            notificar("escuchando")
        except Exception:
            pass
    puerta = getattr(sesion, "puerta", None)
    if puerta is not None and callable(getattr(puerta, "notificar_actividad", None)):
        try:
            puerta.notificar_actividad()
        except Exception:
            pass
    return True


__all__ = ["reanudar_escucha"]
