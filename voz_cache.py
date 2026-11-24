"""Caché en memoria de audio y sonidos de espera inmediata para Silvestra."""
import io
import threading
import time

_cache_audio = {}
_bloqueo = threading.Lock()
_ultimo_sonido = None

# Sonidos / muletillas naturales de espera corta
SONIDOS_ESPERA = ["Mm...", "A ver...", "Claro...", "Déjame ver..."]


def normalizar_clave(frase, emocion="neutral"):
    return (str(frase).strip().lower(), str(emocion).strip().lower())


def obtener_audio_cache(frase, emocion="neutral"):
    """Devuelve los bytes de audio si ya están en caché; de lo contrario None."""
    clave = normalizar_clave(frase, emocion)
    with _bloqueo:
        return _cache_audio.get(clave)


def guardar_audio_cache(frase, audio_bytes, emocion="neutral"):
    """Guarda en caché los bytes de audio generados."""
    if not audio_bytes:
        return
    clave = normalizar_clave(frase, emocion)
    with _bloqueo:
        # Limitar caché a las 150 frases más frecuentes
        if len(_cache_audio) > 150:
            _cache_audio.pop(next(iter(_cache_audio)))
        _cache_audio[clave] = audio_bytes


def limpiar():
    """Invalida el caché cuando cambian la voz o el estilo (aplicación en caliente)."""
    with _bloqueo:
        _cache_audio.clear()


def obtener_siguiente_muletilla():
    """Selecciona la siguiente muletilla de espera sin repetir la misma consecutivamente."""
    global _ultimo_sonido
    with _bloqueo:
        candidatos = [s for s in SONIDOS_ESPERA if s != _ultimo_sonido]
        if not candidatos:
            candidatos = SONIDOS_ESPERA
        import random
        elegido = random.choice(candidatos)
        _ultimo_sonido = elegido
        return elegido


def precargar_audios_frecuentes(sintetizar_fn):
    """Genera en segundo plano el audio de las muletillas y frases frecuentes."""
    def _tarea():
        frases_base = list(SONIDOS_ESPERA) + [
            "¿Sí?",
            "Listo, me callo.",
            "Te escucho, dime.",
            "De acuerdo.",
            "Estoy usando mi cerebro de respaldo.",
            "Dame un segundito que se me fue la señal de mis cerebros, pero ya estoy reintentando reconectarme.",
        ]
        for f in frases_base:
            if not obtener_audio_cache(f):
                try:
                    aud = sintetizar_fn(f, "neutral")
                    if aud:
                        guardar_audio_cache(f, aud, "neutral")
                except Exception:
                    pass
                time.sleep(0.05)

    threading.Thread(target=_tarea, daemon=True).start()
