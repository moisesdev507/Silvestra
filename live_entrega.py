"""Registro de la sesión Live viva e inyección thread-safe de turnos completos."""
import asyncio
import threading

from google.genai import types

import live_estado

_REGISTRO_BLOQUEO = threading.RLock()
_SESION_ACTIVA = None


def registrar_sesion_activa(sesion):
    """Publica la sesión viva para hilos de fondo (S2, iniciativa, HUD)."""
    global _SESION_ACTIVA
    with _REGISTRO_BLOQUEO:
        _SESION_ACTIVA = sesion
    return sesion


def _sesion_registrada():
    with _REGISTRO_BLOQUEO:
        return _SESION_ACTIVA


def sesion_activa():
    """Devuelve la sesión registrada solo si sigue activa."""
    sesion = _sesion_registrada()
    return sesion if sesion is not None and getattr(sesion, "activo", False) else None


def despertar_y_notificar(sesion):
    """Despierta Reposo Azul y marca actividad antes de hablar."""
    try:
        puente = getattr(sesion, "_puente_webrtc", None)
        if puente is not None and getattr(puente, "dormida", False):
            try:
                puente.despertar()
            except Exception:
                pass
            puente.dormida = False
        live_estado.reanudar_escucha(sesion)
        puerta = getattr(sesion, "puerta", None)
        if puerta is not None and callable(getattr(puerta, "notificar_actividad", None)):
            puerta.notificar_actividad()
    except Exception:
        pass


def enviar_texto(sesion, texto, turn_complete: bool = True) -> bool:
    """Inyecta un turno completo en la sesión viva sin esperar otra voz."""
    if not getattr(sesion, "activo", False) or not getattr(sesion, "_loop", None):
        return False
    if not getattr(sesion, "_session_genai", None):
        return False
    mensaje = str(texto or "").strip()
    if not mensaje:
        return False
    despertar_y_notificar(sesion)

    def _enviar():
        session = sesion._session_genai
        if session is None:
            return

        async def _coro():
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=mensaje)]),
                turn_complete=bool(turn_complete),
            )

        tarea = asyncio.create_task(_coro())
        bloqueo = getattr(sesion, "_bloqueo_envio", None)
        tareas = getattr(sesion, "_tareas_envio", None)
        if bloqueo is None or tareas is None:
            return

        def _fin(t):
            with bloqueo:
                tareas.discard(t)
            if not t.cancelled():
                try:
                    error = t.exception()
                except Exception:
                    error = None
                if error:
                    print(f"[LIVE] Error texto: {error}", flush=True)

        with bloqueo:
            tareas.add(tarea)
        tarea.add_done_callback(_fin)

    try:
        sesion._loop.call_soon_threadsafe(_enviar)
        return True
    except Exception:
        return False


__all__ = [
    "registrar_sesion_activa", "sesion_activa", "_sesion_registrada",
    "despertar_y_notificar", "enviar_texto",
]
