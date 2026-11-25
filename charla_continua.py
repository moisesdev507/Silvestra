"""Módulo de charla continua (10s), cierre inteligente y barge-in seguro anti-eco."""
import re
import threading
import time
import unicodedata
import numpy as np

DURACION_VENTANA_CHARLA = 10.0
UMBRAL_RMS_BARGE_IN = 850.0  # Señal vocal clara por encima de eco de parlantes
DURACION_MIN_BARGE_IN = 0.22  # Energía sostenida para no cortar por clic o ruido impulsivo

TERMINOS_CIERRE = {
    "gracias", "muchas gracias", "ok gracias", "vale gracias",
    "listo", "ya esta", "ya está", "eso era todo", "nada mas", "nada más",
    "adios", "adiós", "chao", "hasta luego", "bye", "dejalo asi", "déjalo así",
    "descansa", "vale listo", "todo bien"
}

_bloqueo = threading.RLock()
_limite_charla_continua = 0.0
_energia_sostenida_inicio = 0.0


def normalizar_texto(texto):
    txt = unicodedata.normalize("NFKD", str(texto or "").strip().lower())
    sin_tildes = "".join(c for c in txt if not unicodedata.combining(c))
    limpio = re.sub(r"[^\w\s]", " ", sin_tildes)
    return " ".join(limpio.split())


def abrir_ventana_charla(duracion=DURACION_VENTANA_CHARLA):
    """Abre o refresca la ventana temporal de conversación sin wake-word."""
    global _limite_charla_continua
    with _bloqueo:
        _limite_charla_continua = time.monotonic() + float(duracion)


def cerrar_ventana_charla():
    """Cierra inmediatamente la ventana de charla continua."""
    global _limite_charla_continua
    with _bloqueo:
        _limite_charla_continua = 0.0


def ventana_charla_activa():
    """True si la ventana de seguimiento conversacional está vigente."""
    with _bloqueo:
        return time.monotonic() < _limite_charla_continua


def es_cierre_conversacion(texto):
    """Detecta si la frase es una despedida, agradecimiento o cierre de turno."""
    t = normalizar_texto(texto)
    if not t:
        return False
    if t in TERMINOS_CIERRE:
        return True
    for c in ("gracias", "ok gracias", "listo", "eso era todo", "nada mas", "chao", "adios"):
        if t.startswith(c + " ") or t.endswith(" " + c):
            return True
    return False


def respuesta_cierre_amable():
    """Respuesta breve y natural de Kaya al cerrar la conversación."""
    import random
    opciones = [
        "Dale, con gusto. Aquí ando si me necesitas.",
        "Listo, cuando quieras seguimos.",
        "A la orden. Que te rinda.",
        "Perfecto, aquí me quedo atenta.",
        "Dale, cuídate."
    ]
    return random.choice(opciones)


def evaluar_barge_in_seguro(app, datos_audio):
    """Evalúa si el audio del micrófono corresponde a voz humana sostenida y no a eco.
    
    Devuelve True si se confirma interrupción legítima y detiene el audio.
    """
    global _energia_sostenida_inicio
    if not (app and hasattr(app, "voz") and app.voz.ocupada()):
        _energia_sostenida_inicio = 0.0
        return False

    if datos_audio is None or len(datos_audio) == 0:
        _energia_sostenida_inicio = 0.0
        return False

    try:
        if isinstance(datos_audio, np.ndarray):
            muestras = datos_audio.astype(np.float32)
        else:
            muestras = np.frombuffer(datos_audio, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(muestras ** 2)))
    except Exception:
        return False

    ahora = time.monotonic()

    # Si la energía supera el umbral de presencia vocal clara sobre el altavoz
    if rms >= UMBRAL_RMS_BARGE_IN:
        if _energia_sostenida_inicio == 0.0:
            _energia_sostenida_inicio = ahora
            return False
        duracion_energia = ahora - _energia_sostenida_inicio
        if duracion_energia >= DURACION_MIN_BARGE_IN:
            _energia_sostenida_inicio = 0.0
            print(f"[barge-in] interrumpido legítimo: rms={rms:.1f} duracion={duracion_energia:.2f}s", flush=True)
            if hasattr(app.voz, "detener"):
                app.voz.detener()
            if hasattr(app, "cola"):
                app.cola.put(("interrupcion", None))
            return True
    else:
        _energia_sostenida_inicio = 0.0

    return False
