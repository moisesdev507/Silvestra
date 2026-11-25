"""Voz clásica Celeste en streaming progresivo con métrica de primer audio.

Reutiliza el productor/consumidor de ``tts_aura_stream``: reproduce cada trozo
PCM en cuanto llega (RawOutputStream, sin archivos temporales) y respeta la
cancelación inmediata y la compuerta anti-eco del motor clásico.
"""
import time

import tts_aura_stream


def detener():
    """Señala cancelación cooperativa al hilo dueño del stream."""
    return tts_aura_stream.detener_reproduccion_activa()


def precalentar(forzar=False):
    return tts_aura_stream.precalentar_conexion(forzar=forzar)


def disponible():
    return tts_aura_stream.aura_disponible()


def reproducir(texto, cancelar_fn=None, al_iniciar=None, al_nivel=None):
    """Reproduce progresivamente y registra el tiempo hasta el primer audio."""
    t0 = time.monotonic()

    def al_primer_audio():
        ms = round((time.monotonic() - t0) * 1000.0)
        print(f"[tiempo] clasico_tts_primer_audio={ms}ms", flush=True)
        if callable(al_iniciar):
            try:
                al_iniciar()
            except Exception:
                pass

    try:
        return tts_aura_stream.reproducir_stream_aura(
            texto, cancelar_fn, al_primer_audio, al_nivel
        )
    except Exception as exc:
        print(f"[voz] streaming no disponible ({exc}), usando fallback local.", flush=True)
        return False


__all__ = ["detener", "precalentar", "disponible", "reproducir"]
