"""Transiciones de estado y watchdog de Live sin tocar widgets ni bloquear audio."""
from __future__ import annotations

import time
from typing import Any


def notificar_actividad_audio(sesion: Any) -> None:
    """Actualiza el reloj de actividad con cada paquete de audio enviado o recibido."""
    if sesion is not None:
        sesion._t_inicio_bloqueo = time.time()


def reanudar_escucha(sesion: Any) -> bool:
    """Vuelve a 'escuchando' tras interrupciones, turnos o herramientas."""
    if sesion is None:
        return False
    sesion._t_inicio_bloqueo = None
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


def limpiar_para_reconexion(sesion: Any) -> None:
    """Limpia colas, restablece estado y resetea banderas tras desconexiones o error 1011."""
    if sesion is None:
        return
    sesion._t_inicio_bloqueo = None
    if callable(getattr(sesion, "vaciar_colas_audio_entrada", None)):
        try:
            sesion.vaciar_colas_audio_entrada()
        except Exception:
            pass
    cola_salida = getattr(sesion, "cola_audio_salida", None)
    if cola_salida is not None and hasattr(cola_salida, "mutex"):
        try:
            with cola_salida.mutex:
                cola_salida.queue.clear()
        except Exception:
            pass
    puente = getattr(sesion, "_puente_webrtc", None)
    if puente is not None:
        if callable(getattr(puente, "interrumpir_salida", None)):
            try:
                puente.interrumpir_salida()
            except Exception:
                pass
    reanudar_escucha(sesion)


def vigilar_bloqueo(sesion: Any, timeout_seg: float = 14.0) -> bool:
    """Protege el micrófono: si queda trabado en 'hablando'/'pensando', lo libera."""
    if sesion is None or not getattr(sesion, "activo", False):
        return False
    estado = getattr(sesion, "_estado_actual", "")
    if estado in ("hablando", "pensando"):
        t_inicio = getattr(sesion, "_t_inicio_bloqueo", None)
        ahora = time.time()
        if t_inicio is None:
            sesion._t_inicio_bloqueo = ahora
            return False
        if ahora - t_inicio > timeout_seg:
            print(
                f"[LIVE] Watchdog: estado '{estado}' superó {timeout_seg:.0f}s sin fin de turno. "
                "Liberando micrófono hacia escucha.",
                flush=True,
            )
            sesion._t_inicio_bloqueo = None
            limpiar_para_reconexion(sesion)
            return True
    else:
        sesion._t_inicio_bloqueo = None
    return False


__all__ = ["limpiar_para_reconexion", "notificar_actividad_audio", "reanudar_escucha", "vigilar_bloqueo"]
