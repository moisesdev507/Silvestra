"""TTS local con sherpa-onnx/Kokoro: modelo perezoso, emoción -> speed y WAV en memoria.

Nunca lanza excepción hacia la voz: si faltan archivos o falla la síntesis,
devuelve None para que ``Voz._audio`` caiga limpiamente a edge-tts.
"""
import io
import os
import re
import threading
import wave
from array import array

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_MODELOS = os.path.join(_RAIZ, "modelos")
_LOCK = threading.Lock()
_TTS = None
_FALLADO = False

# Velocidad hablada por emoción (Kokoro solo expone speed/speaker id).
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
    """Traduce la emoción de Lyris al parámetro speed de Kokoro."""
    return _VELOCIDADES[normalizar_emocion(emocion)]


def _archivos():
    """Localiza model/voices/tokens (y lexicon opcional) dentro de modelos/."""
    if not os.path.isdir(_MODELOS):
        return None
    encontrados = []
    for raiz, _dirs, archivos in os.walk(_MODELOS):
        for nombre in archivos:
            encontrados.append((nombre.lower(), os.path.join(raiz, nombre)))

    def buscar(nombres):
        return next((ruta for nombre, ruta in encontrados if nombre in nombres), "")

    modelo = next(
        (ruta for nombre, ruta in encontrados
         if nombre.endswith(".onnx")
         and ("kokoro" in nombre
              or "kokoro" in os.path.basename(os.path.dirname(ruta)).lower())),
        "",
    )
    voces = buscar(("voices.bin",)) or next(
        (ruta for nombre, ruta in encontrados
         if nombre.endswith(".bin") and "voices" in os.path.dirname(ruta).lower()),
        "",
    )
    tokenes = buscar(("tokens.txt",))
    if not (modelo and voces and tokenes):
        return None
    return modelo, voces, tokenes, buscar(("lexicon.txt", "lexicon_us.txt"))


def disponible():
    """True si sherpa-onnx y los archivos del modelo están listos."""
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
                print("[voz_local] sin modelo Kokoro; edge-tts sigue activo", flush=True)
                return None
            modelo, voces, tokenes, lexico = rutas
            kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=modelo, voices=voces, tokens=tokenes, lexicon=lexico)
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(kokoro=kokoro))
            _TTS = sherpa_onnx.OfflineTts(config)
            _FALLADO = False
            print("[voz_local] Kokoro cargado", flush=True)
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
    """Devuelve WAV local o None; jamás propaga errores al flujo de voz."""
    texto = " ".join(str(frase or "").split())
    if not texto:
        return None
    try:
        tts = _cargar()
        if tts is None:
            return None
        audio = tts.generate(texto, speed=velocidad_para(emocion))
        muestras = getattr(audio, "samples", None)
        if muestras is None or len(muestras) == 0:
            return None
        return samples_a_wav(muestras, getattr(audio, "sample_rate", 24000))
    except Exception:
        return None
