"""Earcons desactivados: Silvestra no emite pitidos ni sonidos sintéticos.

La API pública se conserva para que ningún módulo rompa, pero toda reproducción
es un no-op. ``generar_wav`` devuelve un WAV válido, mono y silencioso para que
los consumidores que inspeccionan el buffer sigan funcionando sin audio.
"""
import io
import wave

_TASA = 44100
_DURACION = 0.30


def _wav_silencio():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_TASA)
        wf.writeframes(b"\x00\x00" * int(_TASA * _DURACION))
    return buf.getvalue()


_SILENCIO = _wav_silencio()


def generar_wav(nombre="activar"):
    """WAV mono 16-bit de 44.1 kHz sin ninguna muestra audible."""
    return _SILENCIO


def reproducir(nombre="activar"):
    """No-op seguro: nunca genera hilos ni reproduce audio."""
    return None


def activar():
    """No-op: la confirmación la hace la micro-voz natural de Salomé."""
    return None


def confirmar():
    """No-op: la confirmación la hace la micro-voz natural de Salomé."""
    return None


def captado():
    """No-op: la captura se confirma visualmente, sin pitidos."""
    return None


def accion():
    """No-op: la acción se confirma con voz, sin pitidos."""
    return None
