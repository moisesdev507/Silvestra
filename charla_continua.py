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
_piso_eco_estimado = 0.0
_t_inicio_habla_asistente = 0.0
_bloques_bajos_tolerados = 0
_diag_total_bloques = 0
_diag_max_rms = 0.0
_T_ARRANQUE_PROCESO = time.monotonic()


def barge_in_habilitado():
    """True si barge-in está habilitado por defecto o configuración."""
    import os
    if os.environ.get("LYRIS_BARGE_IN") == "0":
        return False
    return True


def reiniciar_estado_barge_in():
    """Reinicia variables de calibración de eco y barge-in."""
    global _energia_sostenida_inicio, _piso_eco_estimado, _t_inicio_habla_asistente
    global _bloques_bajos_tolerados, _diag_total_bloques, _diag_max_rms
    with _bloqueo:
        _energia_sostenida_inicio = 0.0
        _piso_eco_estimado = 0.0
        _t_inicio_habla_asistente = 0.0
        _bloques_bajos_tolerados = 0
        _diag_total_bloques = 0
        _diag_max_rms = 0.0


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
    """Evalúa si el audio del micrófono corresponde a voz humana sostenida sobre el eco.
    
    Usa umbral adaptativo calibrado contra el piso de eco medido durante el habla de Kaya.
    Corta en < 300 ms cuando el usuario habla normal (~550-850 RMS) sin falsos positivos por parlante.
    """
    global _energia_sostenida_inicio, _piso_eco_estimado, _t_inicio_habla_asistente
    global _bloques_bajos_tolerados, _diag_total_bloques, _diag_max_rms
    hablando = bool(app and hasattr(app, "voz") and app.voz.ocupada())
    if not hablando:
        if _diag_total_bloques > 0:
            print(f"[barge_in_diag] bloques={_diag_total_bloques} max_rms={_diag_max_rms:.1f} "
                  f"piso_eco={_piso_eco_estimado:.1f} disparado=False", flush=True)
        reiniciar_estado_barge_in()
        return False

    if datos_audio is None or len(datos_audio) == 0:
        return False

    try:
        if isinstance(datos_audio, np.ndarray):
            muestras = datos_audio.astype(np.float32)
        else:
            muestras = np.frombuffer(datos_audio, dtype=np.int16).astype(np.float32)
        
        # Normalizar si viene en escala normalizada float32 [-1.0, 1.0]
        if muestras.size > 0:
            max_abs = float(np.max(np.abs(muestras)))
            if max_abs <= 1.5:
                muestras = muestras * 32768.0

        rms = float(np.sqrt(np.mean(muestras ** 2)))
    except Exception:
        return False

    _diag_total_bloques += 1
    if rms > _diag_max_rms:
        _diag_max_rms = rms

    ahora = time.monotonic()
    if (ahora - _T_ARRANQUE_PROCESO) < 2.5:
        # Gracia de arranque: permitir estabilización de hardware de audio sin cortes falsos
        return False
    if _t_inicio_habla_asistente == 0.0:
        _t_inicio_habla_asistente = ahora

    duracion_hablando = ahora - _t_inicio_habla_asistente

    # Calibración del piso de eco en los primeros bloques si no hay voz humana fuerte
    if duracion_hablando <= 0.25 and rms < 450.0:
        _piso_eco_estimado = max(_piso_eco_estimado, rms)

    # Umbral adaptativo para parlantes de laptop:
    # Si piso_eco es bajo, umbral = 450. Si hay eco moderado, umbral = min(piso*1.22, piso+200)
    umbral_dinamico = max(450.0, min(_piso_eco_estimado * 1.22, _piso_eco_estimado + 200.0))

    if rms >= umbral_dinamico:
        _bloques_bajos_tolerados = 0
        if _energia_sostenida_inicio == 0.0:
            _energia_sostenida_inicio = ahora
            return False
        duracion_energia = ahora - _energia_sostenida_inicio
        if duracion_energia >= 0.15:  # ~150 ms de energía sostenida sobre el eco
            print(f"[barge_in] interrumpida rms={rms:.1f} piso_eco={_piso_eco_estimado:.1f} umbral={umbral_dinamico:.1f}", flush=True)
            print(f"[barge_in_diag] bloques={_diag_total_bloques} max_rms={_diag_max_rms:.1f} "
                  f"piso_eco={_piso_eco_estimado:.1f} umbral={umbral_dinamico:.1f} disparado=True", flush=True)
            reiniciar_estado_barge_in()
            if hasattr(app.voz, "detener"):
                app.voz.detener(motivo="barge_in")
            if hasattr(app, "cola"):
                app.cola.put(("interrupcion", None))
            return True
    else:
        # Tolerancia a micro-caídas entre sílabas (1 bloque ~50-80 ms)
        if _energia_sostenida_inicio > 0.0 and _bloques_bajos_tolerados < 1:
            _bloques_bajos_tolerados += 1
        else:
            _energia_sostenida_inicio = 0.0
            _bloques_bajos_tolerados = 0

    return False
