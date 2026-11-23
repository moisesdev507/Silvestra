"""Earcons suaves y fugaces para reflejos de J.A.R.V.I.S.

Reutiliza el generador WAV anti-clic de ``oido_feedback`` (seno con fade) y
reproduce en un hilo daemon mediante ``winsound``. Sin dispositivo, en tests o
con ``SILVESTRA_SIN_EARCONS=1`` no hace nada y nunca lanza excepción.
"""
import os
import sys
import threading

from oido_feedback import generar_wav_feedback

_TONOS = {
    "captado": {"duracion": 0.075, "f_inicio": 660.0, "f_fin": 880.0, "volumen": 0.10},
    "accion": {"duracion": 0.060, "f_inicio": 520.0, "f_fin": 700.0, "volumen": 0.08},
}
_CACHE = {}
_BLOQUEO = threading.Lock()


def _sin_sonido():
    return os.environ.get("SILVESTRA_SIN_EARCONS") == "1" or "unittest" in sys.modules


def _wav(nombre):
    with _BLOQUEO:
        if nombre not in _CACHE:
            try:
                _CACHE[nombre] = generar_wav_feedback(**_TONOS[nombre])
            except Exception:
                _CACHE[nombre] = b""
        return _CACHE[nombre]


def reproducir(nombre):
    """Reproduce un earcon conocido; silencioso ante cualquier fallo."""
    if _sin_sonido() or nombre not in _TONOS:
        return
    try:
        wav = _wav(nombre)
        if not wav:
            return
        import winsound
        hilo = threading.Thread(
            target=winsound.PlaySound,
            args=(wav, winsound.SND_MEMORY),
            daemon=True,
        )
        hilo.start()
    except Exception:
        pass
