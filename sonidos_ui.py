"""Earcons cinematográficos multi-capa para el HUD de J.A.R.V.I.S.

Síntesis procedural a 44.1 kHz con NumPy + ``wave`` en memoria: sub-thump
táctil, cascada armónica con chorus y cola de delay/reverb paso-bajo. Los
buffers se cachean para latencia cero y se reproducen en hilo daemon.
"""
import io
import os
import sys
import threading
import wave

import numpy as np

_TASA = 44100
_ARP = (587.33, 880.0, 1318.51, 1760.0)
# nombre -> (duración, ganancia); "captado"/"accion" los usa eventos.py
_TONOS = {
    "activar": (0.320, 1.0),
    "confirmar": (0.260, 0.85),
    "captado": (0.320, 1.0),
    "accion": (0.260, 0.85),
}
_CACHE = {}
_BLOQUEO = threading.Lock()


def _sin_sonido():
    return os.environ.get("SILVESTRA_SIN_EARCONS") == "1" or "unittest" in sys.modules


def _mezcla(t, vol):
    """Tres capas + ecos suavizados, sin frecuencias graves de 'pun'."""
    n = len(t)
    # Capa 1: sub-thump 115 -> 62 Hz en 90 ms con fase integrada.
    tau = 0.030
    fase = 2.0 * np.pi * (62.0 * t + 53.0 * tau * (1.0 - np.exp(-t / tau)))
    sub = np.sin(fase) * np.exp(-t / 0.11)
    sub[:int(0.003 * _TASA)] = 0.0
    # Capa 2: arpegio cristalino doblado con micro-desafinación (+4 Hz).
    arp = np.zeros(n)
    for i, f in enumerate(_ARP):
        local = t - i * 0.032
        vivo = local >= 0.0
        v = np.zeros(n)
        v[vivo] = (np.sin(2.0 * np.pi * f * local[vivo])
                   + 0.55 * np.sin(2.0 * np.pi * (f + 4.0) * local[vivo]))
        v[vivo] *= np.exp(-local[vivo] / 0.13)
        arp += v
    # Capa 3: tres ecos atenuados con filtro paso-bajo de promedio móvil.
    cola = np.zeros(n)
    for retardo, ganancia in ((0.055, 0.32), (0.110, 0.20), (0.175, 0.12)):
        d = int(retardo * _TASA)
        cola[d:] += ganancia * arp[:-d]
    cola = np.convolve(cola, np.ones(24) / 24.0, mode="same")
    return vol * (0.34 * sub + 0.42 * arp + cola) / 1.5


def generar_wav(nombre="activar"):
    """WAV mono 16-bit de 44.1 kHz con envolvente anti-clic."""
    dur, vol = _TONOS.get(nombre, _TONOS["activar"])
    t = np.arange(int(dur * _TASA), dtype=np.float64) / _TASA
    n = len(t)
    env = np.ones(n)
    ent, sal = int(0.004 * _TASA), int(0.035 * _TASA)
    env[:ent] = 0.5 * (1.0 - np.cos(np.pi * np.arange(ent) / ent))
    env[-sal:] = 0.5 * (1.0 + np.cos(np.pi * np.arange(sal) / sal))
    senal = _mezcla(t, vol) * env
    senal *= 0.95 / max(float(np.max(np.abs(senal))), 1e-6)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_TASA)
        wf.writeframes(np.clip(senal * 32767.0, -32768.0, 32767.0)
                       .astype("<i2").tobytes())
    return buf.getvalue()


def _reproducir(datos):
    try:
        import winsound
        winsound.PlaySound(datos, winsound.SND_MEMORY)
    except Exception:
        pass


def reproducir(nombre="activar"):
    """Reproduce un earcon cacheado sin bloquear al llamador."""
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


def activar():
    reproducir("activar")


def confirmar():
    reproducir("confirmar")


def captado():
    reproducir("captado")


def accion():
    reproducir("accion")
