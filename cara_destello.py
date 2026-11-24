"""Seguidor de envolvente silábica y mezcla de color para el núcleo J.A.R.V.I.S.

Aísla el parpadeo vocal: ataque rápido y caída suave, con energía propia aunque
el micrófono entregue un nivel plano o bajo.
"""
import math

from PySide6.QtGui import QColor


def mezcla(c1, c2, f):
    """Interpola dos QColor para el destello blanco-dorado."""
    f = max(0.0, min(1.0, f))
    return QColor(round(c1.red() + (c2.red() - c1.red()) * f),
                  round(c1.green() + (c2.green() - c1.green()) * f),
                  round(c1.blue() + (c2.blue() - c1.blue()) * f))


def pulso_silaba(cara, suavizar, estado, nivel, t, dt):
    """Envolvente orgánica por sílaba: ataque corto, cola exponencial."""
    if estado != "hablando":
        return suavizar(cara, "_destello_voz", 0.0, 0.30)
    fase = float(getattr(cara, "_fase_silaba", 0.0)) + dt * (
        4.2 + 1.1 * math.sin(t * 0.63))
    cara._fase_silaba = fase
    ciclo = fase % 1.0
    silaba = min(1.0, ciclo / 0.12) * (
        math.exp(-3.0 * (ciclo - 0.12)) if ciclo > 0.12 else 1.0)
    objetivo = (0.28 + 0.72 * silaba) * (0.55 + 0.45 * nivel)
    return suavizar(cara, "_destello_voz", objetivo, 0.40)
