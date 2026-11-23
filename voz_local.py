"""TTS local de respaldo: Piper VITS en español vía sherpa-onnx.

Carga perezosa con Lock, emoción -> speed y WAV PCM16 en memoria. Devuelve
None ante cualquier fallo para que ``Voz._audio`` siga con edge-tts o SAPI.
"""
import asyncio
import io
import os
import re
import threading
import wave
from array import array

from voz_fonemas import fonemas_es

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_MODELOS = os.path.join(_RAIZ, "modelos")
_LOCK = threading.Lock()
_TTS = None
_FALLADO = False

# Piper VITS solo expone speed; estas son las variaciones usadas por Lyris.
_VELOCIDADES = {
    "neutral": 1.0, "normal": 1.0, "enojada": 1.0,
    "alegre": 1.06, "animada": 1.08, "orgullosa": 1.06,
    "calida": 1.02, "cariñosa": 1.02,
    "seria": 0.96, "firme": 0.96, "concentrada": 0.96,
    "preocupada": 0.92, "calmada": 0.92, "descanso": 0.90,
}


def normalizar_emocion(emocion):
    """Devuelve una emoción conocida o 'neutral'."""
    e = re.sub(r"[^a-z]", "", str(emocion or "").strip().lower())
    return e if e in _VELOCIDADES else "neutral"


def velocidad_para(emocion):
    """Traduce la emoción al parámetro speed de Piper VITS."""
    return _VELOCIDADES[normalizar_emocion(emocion)]


def debe_ir_local_primero():
    """Solo LYRIS_TTS_LOCAL=1 invierte la prioridad natural (edge-tts primero)."""
    return os.environ.get("LYRIS_TTS_LOCAL") == "1"


def _carpeta_modelo():
    """Localiza vits-piper-* en modelos/, prefiriendo una voz en español."""
    if not os.path.isdir(_MODELOS):
        return ""
    candidatas = [
        raiz for raiz, _dirs, _archivos in os.walk(_MODELOS)
        if os.path.basename(raiz).lower().startswith("vits-piper")
    ]
    return next((r for r in candidatas if "es_" in os.path.basename(r).lower()),
                candidatas[0] if candidatas else "")


def _archivos():
    """Devuelve (model.onnx, tokens.txt, espeak-ng-data) del modelo Piper."""
    carpeta = _carpeta_modelo()
    if not carpeta:
        return None
    modelo = next(
        (os.path.join(carpeta, n) for n in sorted(os.listdir(carpeta))
         if n.lower().endswith(".onnx")), "")
    tokenes = os.path.join(carpeta, "tokens.txt")
    if not (modelo and os.path.isfile(tokenes)):
        return None
    dato = os.path.join(carpeta, "espeak-ng-data")
    if not os.path.isdir(dato):
        dato = next(
            (os.path.join(r, "espeak-ng-data")
             for r, dirs, _f in os.walk(carpeta)
             if "espeak-ng-data" in dirs), "")
    return modelo, tokenes, dato


def disponible():
    """True si sherpa-onnx y el modelo Piper están listos."""
    if _TTS is not None:
        return True
    try:
        import sherpa_onnx  # noqa: F401
    except Exception:
        return False
    return _archivos() is not None


def _cargar():
    """Carga OfflineTts una sola vez, bajo lock y de forma perezosa."""
    global _TTS, _FALLADO
    if _TTS is not None:
        return _TTS
    with _LOCK:
        if _TTS is not None or _FALLADO:
            return _TTS
        _FALLADO = True
        try:
            import sherpa_onnx
            rutas = _archivos()
            if not rutas:
                print("[voz_local] sin modelo Piper; edge-tts sigue activo", flush=True)
                return None
            modelo, tokenes, dato = rutas
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=modelo, tokens=tokenes, data_dir=dato)
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(vits=vits))
            _TTS = sherpa_onnx.OfflineTts(config)
            _FALLADO = False
            print("[voz_local] Piper VITS cargado", flush=True)
            return _TTS
        except Exception as e:
            print(f"[voz_local] no disponible: {e}", flush=True)
            return None


def samples_a_wav(samples, sample_rate=24000):
    """Convierte muestras float32 (-1..1) a WAV PCM16 mono en bytes."""
    try:
        muestras = array("f", (float(x) for x in samples))
        if not muestras:
            return None
        pcm = array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in muestras))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(sample_rate or 24000))
            wav.writeframes(pcm.tobytes())
        return buf.getvalue()
    except Exception:
        return None


def sintetizar_wav(frase, emocion="neutral"):
    """Devuelve WAV de Piper o None; jamás propaga errores."""
    texto = " ".join(str(frase or "").split())
    if not texto:
        return None
    try:
        import sherpa_onnx
        tts = _cargar()
        if tts is None:
            return None
        velocidad = velocidad_para(emocion)
        generacion = getattr(sherpa_onnx, "GenerationConfig", None)
        if generacion is None:  # sherpa-onnx < 2 usa data_dir directamente
            audio = tts.generate(texto, speed=velocidad)
        else:
            config = generacion()
            config.speed = velocidad
            config.phoneme_codepoints = fonemas_es(texto)
            audio = tts.generate(texto, config)
        muestras = getattr(audio, "samples", None)
        if muestras is None or len(muestras) == 0:
            return None
        return samples_a_wav(muestras, getattr(audio, "sample_rate", 24000))
    except Exception:
        return None


def fallback_local(frase, emocion="neutral"):
    """Respaldo offline con log del motor; None si Piper no está listo."""
    try:
        audio = sintetizar_wav(frase, emocion)
    except Exception:
        return None
    if audio:
        print("[voz] motor=piper_local", flush=True)
    return audio


def generar_edge(crear, frase, emocion):
    """Ejecuta el stream edge-tts con timeout y lo cachea; None si falla."""
    import voz_cache
    try:
        audio = asyncio.run(asyncio.wait_for(crear(), 10))
    except Exception:
        return None
    if not audio:
        return None
    voz_cache.guardar_audio_cache(frase, audio, emocion)
    return audio
