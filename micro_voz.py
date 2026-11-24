"""Micro-confirmación vocal con la voz de Salomé, sin pitidos sintéticos.

Usa el mismo motor y la misma caché que ``Voz.hablar`` pero reproduce directo
el audio cacheado: no cambia el estado visual de la cara ni bloquea al llamador.
"""
import threading

import voz_cache

FRASE_INVOCACION = "¿Sí?"


def _preparar(voz):
    """Sintetiza la frase en segundo plano si aún no está en caché."""
    try:
        audio = voz._audio(FRASE_INVOCACION, "neutral")
        if audio:
            voz_cache.guardar_audio_cache(FRASE_INVOCACION, audio, "neutral")
    except Exception:
        pass


def sonar_invocacion(app):
    """Responde «¿Sí?» al invocar «Lyris» sola. Devuelve True si sonó."""
    voz = getattr(app, "voz", None)
    if voz is None:
        return False
    try:
        audio = voz_cache.obtener_audio_cache(FRASE_INVOCACION, "neutral")
        if not audio:
            threading.Thread(target=_preparar, args=(voz,), daemon=True).start()
            return False
        if getattr(voz, "reproductor", None) is not None:
            voz.reproductor.reproducir_corto(audio, volumen=0.65)
            print(f"[voz] micro_invocacion='{FRASE_INVOCACION}'", flush=True)
            return True
    except Exception:
        pass
    return False
