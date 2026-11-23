"""Ventana de gracia de sesión para confirmaciones breves del dueño.

Solo concede el beneficio a confirmaciones explícitas y audios muy cortos
dentro de una ventana reciente. Nunca sustituye a la biometría en audios
largos ni abre la puerta a frases de invitados.
"""
import time
import unicodedata

VENTANA_GRACIA_SEG = 60.0
UMBRAL_AUDIO_CORTO = 1.2

CONFIRMACIONES_BREVES = frozenset({
    "si", "sí", "sip", "no", "nop", "nel", "dale", "listo", "ya", "vale",
    "ok", "okey", "claro", "cierto", "exacto", "afirmativo", "negativo",
    "sigue", "adelante", "aceptar", "confirmar", "confirmo", "afirmo",
    "bueno", "de acuerdo", "por supuesto", "supuesto", "eso es",
})


def normalizar(texto):
    """Minúsculas sin tildes, útil para comparar confirmaciones habladas."""
    s = str(texto or "").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def es_confirmacion_breve(texto):
    """True para 'Sí.', 'dale', 'ok, claro'; False para órdenes largas."""
    limpio = normalizar(texto).strip("¿?¡!.,;:…\"'")
    if not limpio:
        return False
    if limpio in CONFIRMACIONES_BREVES:
        return True
    partes = [p.strip("¿?¡!.,;:…\"'") for p in limpio.split()]
    return 1 < len(partes) <= 3 and all(p in CONFIRMACIONES_BREVES for p in partes)


def en_ventana(ts, ahora=None, ventana=VENTANA_GRACIA_SEG):
    """True si la marca de tiempo está dentro de la ventana de gracia."""
    if not ts:
        return False
    ahora = time.time() if ahora is None else float(ahora)
    return 0.0 <= ahora - float(ts) <= float(ventana)


def conceder(ts_verificacion, ts_pregunta, texto, duracion, ahora=None):
    """Devuelve el motivo de gracia o None si no debe concederse."""
    try:
        segundos = float(duracion)
    except (TypeError, ValueError):
        return None
    if segundos < 0.0 or segundos >= UMBRAL_AUDIO_CORTO:
        return None
    if not es_confirmacion_breve(texto):
        return None
    if en_ventana(ts_verificacion, ahora):
        return "gracia_verificacion_reciente"
    if en_ventana(ts_pregunta, ahora):
        return "gracia_pregunta_confirmacion"
    return None


def registrar_pregunta(app, ahora=None):
    """Marca que Silvestra acaba de formular una pregunta al usuario."""
    vd = getattr(app, "voz_dueno", None)
    if vd is None:
        return False
    setattr(vd, "_ultima_pregunta_ts", time.time() if ahora is None else float(ahora))
    return True
