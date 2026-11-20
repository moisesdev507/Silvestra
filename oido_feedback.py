"""Sonido sutil de feedback al terminar de capturar voz para Silvestra.

Genera un tono suave (~75 ms, 880 Hz -> 1175 Hz con envolvente anti-clic)
completamente en memoria y lo reproduce de forma asíncrona mediante winsound,
sin tocar sounddevice ni interferir con PortAudio.
"""
import io
import math
import struct
import wave

_WAV_FEEDBACK_BYTES = None


def generar_wav_feedback(duracion=0.075, rate=22050, f_inicio=880.0, f_fin=1175.0, volumen=0.15):
    """Genera en memoria un WAV de 16-bit mono con barrido suave y envolvente anti-clic."""
    n_muestras = int(duracion * rate)
    n_in = int(0.015 * rate)
    n_out = int(0.025 * rate)
    amp_max = int(32767 * volumen)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n_muestras):
            t = i / float(rate)
            fase = 2.0 * math.pi * (f_inicio * t + 0.5 * (f_fin - f_inicio) * (t ** 2) / duracion)
            if i < n_in:
                env = 0.5 * (1.0 - math.cos(math.pi * i / float(n_in)))
            elif i >= (n_muestras - n_out):
                env = 0.5 * (1.0 + math.cos(math.pi * (i - (n_muestras - n_out)) / float(n_out)))
            else:
                env = 1.0
            val = int(amp_max * env * math.sin(fase))
            frames.extend(struct.pack("<h", max(-32768, min(32767, val))))
        wf.writeframes(frames)
    return buf.getvalue()


def obtener_wav_feedback():
    """Retorna el buffer en memoria del WAV de feedback (generado solo una vez)."""
    global _WAV_FEEDBACK_BYTES
    if _WAV_FEEDBACK_BYTES is None:
        try:
            _WAV_FEEDBACK_BYTES = generar_wav_feedback()
        except Exception as e:
            print(f"[oido_feedback] Error generando WAV en memoria: {e}", flush=True)
            _WAV_FEEDBACK_BYTES = b""
    return _WAV_FEEDBACK_BYTES


def reproducir_feedback_escucha(app=None):
    """Reproduce el tono de feedback de escucha de forma 100% asíncrona."""
    if app:
        if getattr(app, "silencio_activo", False) or getattr(app, "modo_privado", False):
            return
        if hasattr(app, "estado_global") and getattr(app.estado_global, "modo_silencioso", False):
            return

    try:
        import winsound
        wav = obtener_wav_feedback()
        if not wav:
            return
        try:
            winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            # Fallback seguro en Windows: winsound.c en Python restringe SND_MEMORY | SND_ASYNC directo
            import threading
            threading.Thread(target=winsound.PlaySound, args=(wav, winsound.SND_MEMORY), daemon=True).start()
    except Exception:
        pass
