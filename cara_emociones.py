"""Perfiles visuales faciales y prosodia vocal para emociones en Silvestra / Lyris.

Define los rasgos geométricos para el avatar holográfico en PySide6 y los parámetros
de entonación de voz (rate, pitch, volume) para síntesis TTS.
"""
import unicodedata
from PySide6.QtGui import QColor

# Rasgos: (cejas_y, cejas_ang, ojos_apertura, boca_curva, boca_ancho, rubor_alpha, color_base)
RASGOS_FACIALES = {
    "neutral":     ( 0.0,   0.0, 1.00,  1.0, 28.0,  90.0, QColor(79, 209, 197)),
    "alegre":      (-5.0,   3.5, 1.10,  2.0, 38.0, 170.0, QColor(16, 185, 129)),
    "animada":     (-6.5,   4.0, 1.20,  2.2, 40.0, 180.0, QColor(245, 158, 11)),
    "calida":      (-2.5,   2.0, 0.95,  1.4, 32.0, 160.0, QColor(244, 114, 182)),
    "seria":       ( 3.5,  -4.5, 0.80,  0.0, 20.0,  40.0, QColor(59, 130, 246)),
    "preocupada":  (-5.5,   6.5, 1.12, -0.7, 22.0,  70.0, QColor(147, 51, 234)),
    # Nuevas emociones solicitadas:
    "concentrada": (-1.5,  -3.0, 0.92,  0.3, 24.0,  55.0, QColor(99, 102, 241)),
    "firme":       ( 4.5,  -6.0, 0.75, -0.5, 22.0,  30.0, QColor(239, 68, 68)),
    "enojada":     ( 4.5,  -6.0, 0.75, -0.5, 22.0,  30.0, QColor(239, 68, 68)),
    "orgullosa":   (-5.5,   4.0, 1.15,  2.4, 42.0, 185.0, QColor(234, 179, 8)),
}

PROSODIA_VOCAL = {
    "neutral":     {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
    "alegre":      {"rate": "+8%", "pitch": "+6Hz", "volume": "+0%"},
    "animada":     {"rate": "+12%", "pitch": "+8Hz", "volume": "+0%"},
    "calida":      {"rate": "-3%", "pitch": "+2Hz", "volume": "+0%"},
    "seria":       {"rate": "-5%", "pitch": "-4Hz", "volume": "+0%"},
    "preocupada":  {"rate": "-8%", "pitch": "-4Hz", "volume": "-5%"},
    # Nuevas emociones:
    "concentrada": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "firme":       {"rate": "-6%", "pitch": "-6Hz", "volume": "+5%"},
    "enojada":     {"rate": "-6%", "pitch": "-6Hz", "volume": "+5%"},
    "orgullosa":   {"rate": "+5%", "pitch": "+4Hz", "volume": "+5%"},
}


def _normalizar(emo):
    if not emo:
        return "neutral"
    t = unicodedata.normalize("NFD", str(emo).strip().lower())
    limpio = "".join(c for c in t if unicodedata.category(c) != "Mn")
    if limpio in ("enojado", "molesta", "molesto"):
        return "firme"
    if limpio in ("orgulloso", "satisfecha", "satisfecho"):
        return "orgullosa"
    if limpio in ("concentrado", "enfocada", "enfocado"):
        return "concentrada"
    return limpio


def obtener_rasgos(emocion):
    """Devuelve la tupla de rasgos geométricos para el renderizado facial en Qt."""
    clave = _normalizar(emocion)
    return RASGOS_FACIALES.get(clave, RASGOS_FACIALES["neutral"])


def obtener_prosodia(emocion):
    """Devuelve los parámetros de entonación vocal (rate, pitch, volume) para TTS."""
    clave = _normalizar(emocion)
    return PROSODIA_VOCAL.get(clave, PROSODIA_VOCAL["neutral"])


# Enriquecimiento dinámico y seguro de voz.py sin modificar su archivo protegido
try:
    import voz
    for k, v in PROSODIA_VOCAL.items():
        if k not in voz.EMOCIONES_VOZ:
            voz.EMOCIONES_VOZ[k] = v
            voz.EMOCIONES_VALIDAS.add(k)
except Exception:
    pass
