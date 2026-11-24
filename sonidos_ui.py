"""Earcons HUD de J.A.R.V.I.S., generados en memoria con NumPy + ``wave``.

Dos armónicos limpios (880 Hz + 1318.5 Hz), deslizamiento ascendente de 40 ms
y envolvente suave sin clics. Reproducción asíncrona en hilo daemon; en tests,
sin earcons o sin winsound no hace nada y nunca lanza excepción.
"""
import io
import os
import sys
import threading
import wave

import numpy as np

_TASA = 22050
_H1, _H2 = 880.0, 1318.5
# variante -> (duración, deslizamiento, volumen)
_TONOS = {
    "activar": (0.150, 0.040, 0.105),
    "confirmar": (0.095, 0.040, 0.085),
    # alias que sigue usando eventos.py (archivo no modificado)
    "captado": (0.150, 0.040, 0.105),
    "accion": (0.095, 0.040, 0.085),
}
_CACHE = {}
_BLOQUEO = threading.Lock()


def _sin_sonido():
    return os.environ.get("SILVESTRA_SIN_EARCONS") == "1" or "unittest" in sys.modules


def generar_wav(nombre="activar"):
    """WAV mono 16-bit con quinta justa, barrido corto y envolvente anti-clic."""
    dur, desl, vol = _TONOS.get(nombre, _TONOS["activar"])
    t = np.arange(int(dur * _TASA), dtype=np.float64) / _TASA
    pendiente = _H1 * 0.06 / desl
    subida = np.minimum(t, desl)
    fase = 2.0 * np.pi * (_H1 * t + 0.5 * pendiente * subida ** 2
                         + (_H1 + pendiente * desl) * np.maximum(t - desl, 0.0))
    n = len(t)
    na, ns = int(0.012 * _TASA), int(0.040 * _TASA)
    env = np.ones(n)
    env[:na] = 0.5 * (1.0 - np.cos(np.pi * np.arange(na) / na))
    env[-ns:] = 0.5 * (1.0 + np.cos(np.pi * np.arange(ns) / ns))
    senal = vol * env * (np.sin(fase) + 0.45 * np.sin(_H2 / _H1 * fase + 0.35))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_TASA)
        muestras = np.clip(senal * 32767.0, -32768.0, 32767.0).astype("<i2")
        wf.writeframes(muestras.tobytes())
    return buf.getvalue()


def _reproducir(datos):
    try:
        import winsound
        winsound.PlaySound(datos, winsound.SND_MEMORY)
    except Exception:
        pass


def reproducir(nombre="activar"):
    """Reproduce un earcon sin bloquear al llamador."""
    if _sin_sonido():
        return
    with _BLOQUEO:
        datos = _CACHE.get(nombre)
        if datos is None:
            try:
                datos = generar_wav(nombre)
            except Exception:
                datos = b""
            _CACHE[nombre] = datos
    if datos:
        threading.Thread(target=_reproducir, args=(datos,), daemon=True).start()
