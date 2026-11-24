"""Núcleo J.A.R.V.I.S.: orbe luminoso y anillos reactivos al audio/habla.

Solo geometría y dibujo en Qt; la lógica de turnos sigue en la cola de eventos.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient

CELESTE = QColor(34, 211, 238)
CELESTE_CLARO = QColor(56, 189, 248)
AMBAR = QColor(245, 158, 11)
AMBAR_CLARO = QColor(251, 191, 36)
GRIS = QColor(100, 116, 139)
ROSA = QColor(244, 114, 182)


def registrar_cuadro(cara, dt):
    """Telemetría ligera de FPS fuera del widget (mantiene cara_qt delgada)."""
    cara._tiempo_dibujo_acum += dt
    cara._fps_cuadros += 1
    ahora = time.time()
    dt_fps = ahora - cara._fps_t0
    if dt_fps >= 5.0:
        fps = cara._fps_cuadros / dt_fps
        cpu = (cara._tiempo_dibujo_acum / dt_fps) * 100.0
        print(f"[cara] fps={fps:.1f}, cpu_estimada={cpu:.1f}%", flush=True)
        cara._fps_cuadros = 0
        cara._fps_t0 = ahora
        cara._tiempo_dibujo_acum = 0.0


def alpha(color, a):
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def color_estado(viva, escuchando, hablando, feliz=False, base=None, silenciada=False):
    if silenciada or not viva:
        return GRIS
    if escuchando or hablando:
        return AMBAR
    if feliz:
        return ROSA
    return base if base is not None else CELESTE


def esta_silenciada(cara):
    valor = getattr(cara, "voz_silenciada", None)
    if valor is None:
        app = getattr(cara, "silvestra_app", None) or getattr(cara, "_ref_app", None)
        valor = getattr(app, "voz_silenciada", False)
    return bool(valor)


def modo(cara):
    if esta_silenciada(cara):
        return "silenciada"
    if getattr(cara, "hablando", False):
        return "hablando"
    if getattr(cara, "escuchando", False) or getattr(cara, "pensando", False):
        return "escuchando"
    return "reposo"


def nivel(cara):
    if esta_silenciada(cara):
        objetivo = 0.0
    else:
        try:
            objetivo = float(getattr(cara, "nivel_volumen", 0.0) or 0.0)
        except Exception:
            objetivo = 0.0
        objetivo = max(0.0, min(1.0, objetivo))
    suave = float(getattr(cara, "_nivel_suave", 0.0))
    suave += (objetivo - suave) * 0.25
    cara._nivel_suave = suave
    return suave


def _anillos(p, color, estado, t, pulso):
    if estado == "silenciada":
       anillos_cfg = ((118, 2.0, 0.0, 350), (104, 1.4, 0.0, 350))
    elif estado == "reposo":
       anillos_cfg = ((118, 2.6, 12.0, 105), (104, 1.8, -8.0, 80), (130, 1.3, 6.0, 55))
    else:
       anillos_cfg = ((120 + 4 * pulso, 3.2, 75.0, 120),
              (104 + 3 * pulso, 2.2, -55.0, 90),
              (134 + 6 * pulso, 1.6, 40.0, 70))
    base = 70 if estado == "silenciada" else 140
    for radio, grosor, vel, largo in anillos_cfg:
        c = color if estado != "silenciada" else GRIS
        pluma = QPen(alpha(c, base + 80 * pulso), grosor)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(-radio, -radio, radio * 2, radio * 2)
        ini = (t * vel) % 360
        p.drawArc(rect, int(ini * 16), int(largo * 16))
        if estado != "silenciada":
            p.drawArc(rect, int((ini + 150) * 16), int(largo * 16))
            p.drawArc(rect, int((ini + 270) * 16), int(largo * 16))


def _ondas(p, color, estado, t, nivel_actual):
    if estado in ("reposo", "silenciada"):
        return
    for k in range(3):
        radio = 86 + k * 15 + 7 * nivel_actual * (1 + 0.3 * math.sin(t * 5 + k))
        pluma = QPen(alpha(AMBAR_CLARO if estado == "hablando" else color,
                           90 - k * 25 + int(60 * nivel_actual)), 1.6)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(-radio, -radio, radio * 2, radio * 2))


def dibujar(p, cara, color, t, tam):
    """Dibuja el núcleo completo; `t` es tiempo monotonico en segundos."""
    estado = modo(cara)
    nivel_actual = nivel(cara)
    if estado == "silenciada":
        pulso = 0.0
    elif estado == "reposo":
        pulso = 0.5 + 0.5 * math.sin(t * 0.9)
    else:
        pulso = max(0.25, min(1.0, 0.45 + 0.55 * nivel_actual))

    esc = tam / 280.0
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(tam / 2.0, tam / 2.0)
    p.scale(esc, esc)

    brillo = QRadialGradient(QPointF(0, 0), 135)
    brillo.setColorAt(0.5, alpha(color, 46 if estado == "silenciada" else 78))
    brillo.setColorAt(1.0, alpha(color, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(brillo))
    p.drawEllipse(QPointF(0, 0), 135, 135)

    _anillos(p, color, estado, t, pulso)
    _ondas(p, color, estado, t, nivel_actual)

    radio = 54 + (1.6 if estado == "reposo" else 5.0 * nivel_actual)
    if estado == "silenciada":
        radio = 52
    orbe = QRadialGradient(QPointF(-8, -10), radio)
    orbe.setColorAt(0.0, alpha(CELESTE_CLARO if estado == "reposo" else color, 255))
    orbe.setColorAt(0.45, alpha(color, 230))
    orbe.setColorAt(1.0, alpha(color, 60))
    p.setPen(QPen(alpha(color, 180 if estado != "silenciada" else 90), 1.8))
    p.setBrush(QBrush(orbe))
    p.drawEllipse(QPointF(0, 0), radio, radio)

    p.setPen(Qt.NoPen)
    p.setBrush(alpha(QColor(255, 255, 255), 190 if estado != "silenciada" else 60))
    p.drawEllipse(QPointF(0, 0), 5 + 2 * pulso, 5 + 2 * pulso)
    p.restore()
