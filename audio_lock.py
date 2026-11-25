"""Bloqueo de ciclo de vida para PortAudio / sounddevice.

Evita colisiones WASAPI y corrupción de heap (0xc0000374) al abrir,
iniciar, detener y cerrar streams concurrentes entre hilos distintos.
"""
import contextlib
import threading

_PORTAUDIO_LOCK = threading.RLock()


@contextlib.contextmanager
def bloqueo_portaudio():
    """Context manager para operaciones de ciclo de vida en sounddevice."""
    with _PORTAUDIO_LOCK:
        yield
