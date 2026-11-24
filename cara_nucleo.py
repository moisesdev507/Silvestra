"""Núcleo holográfico J.A.R.V.I.S. con transiciones suaves y expresión sutil.

Mantiene la API pública usada por ``cara_dibujo`` y los tests: constantes de
paleta, ``color_estado``, ``esta_silenciada``, ``modo``, ``nivel``,
``registrar_cuadro``, ``alpha`` y ``dibujar``.
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


def _lerp(cara, clave, objetivo, factor):
    actual = float(getattr(cara, clave, objetivo))
    actual += (float(objetivo) - actual) * factor
    setattr(cara, clave, actual)
    return actual


def color_suavizado(cara, objetivo, factor=0.12):
    """Interpola RGB entre estados; el cambio nunca es brusco de un frame."""
    r = _lerp(cara, "_color_r", objetivo.red(), factor)
    g = _lerp(cara, "_color_g", objetivo.green(), factor)
    b = _lerp(cara, "_color_b", objetivo.blue(), factor)
    return QColor(round(r), round(g), round(b))


def _halo(p, color, energia, silenciada, t):
    radio = 132 + 6 * energia
    g = QRadialGradient(QPointF(0, 0), radio)
    g.setColorAt(0.45, alpha(color, 32 if silenciada else int(70 + 40 * energia)))
    g.setColorAt(0.82, alpha(color, 14))
    g.setColorAt(1.0, alpha(color, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), radio, radio)

    if silenciada:
        return
    for k in range(10):
        ang = t * (0.5 + 0.11 * (k % 3)) + k * 2.39996
        r = 111 + (k % 4) * 7 + 6 * energia
        punto = QPointF(r * math.cos(ang), r * math.sin(ang))
        p.setBrush(alpha(CELESTE_CLARO if energia < 0.3 else AMBAR_CLARO,
                         45 + int(60 * energia)))
        p.drawEllipse(punto, 1.3, 1.3)


def _anillos(p, color, estado, energia, t):
    silenciada = estado == "silenciada"
    vel = 0.0 if silenciada else 1.0 + 2.4 * energia
    anillos = ((116, 2.8, 10.0 * vel, 112),
               (101, 1.9, -7.0 * vel, 86),
               (132, 1.5, 5.0 * vel, 62))
    if silenciada:
        anillos = ((116, 2.0, 0.0, 340), (101, 1.4, 0.0, 340))
    for indice, (radio, grosor, grados, largo) in enumerate(anillos):
        pluma = QPen(alpha(color, (72 if silenciada else 135) + int(75 * energia)),
                     grosor)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(-radio, -radio, radio * 2, radio * 2)
        ini = (t * grados + indice * 47) % 360
        p.drawArc(rect, int(ini * 16), int(largo * 16))
        if not silenciada:
            p.drawArc(rect, int((ini + 140) * 16), int(largo * 16))
            p.drawArc(rect, int((ini + 265) * 16), int(largo * 16))
            for m in range(12):
                a = math.radians(m * 30 + ini)
                x, y = math.cos(a), math.sin(a)
                pluma.setWidthF(0.8)
                p.setPen(pluma)
                p.drawLine(QPointF(radio * x, radio * y),
                           QPointF((radio + 4) * x, (radio + 4) * y))


def _espectro(p, color, estado, energia, t):
    if estado == "silenciada":
        return
    tono = AMBAR_CLARO if estado == "hablando" else CELESTE_CLARO
    base = 78
    for i in range(36):
        if i % 2 and energia < 0.2:
            continue
        ang = i * math.tau / 36.0 + t * (0.2 + 0.5 * energia)
        var = abs(math.sin(t * 4.5 + i * 0.9))
        largo = 3 + 17 * energia * var
        c, s = math.cos(ang), math.sin(ang)
        p.setPen(QPen(alpha(tono, 35 + int(95 * energia * var)), 1.2))
        p.drawLine(QPointF(base * c, base * s),
                   QPointF((base + largo) * c, (base + largo) * s))
    for k in range(3):
        radio = 88 + k * 14 + 6 * energia * math.sin(t * 5 + k)
        p.setPen(QPen(alpha(color, 60 + int(45 * energia) - k * 12), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(-radio, -radio, radio * 2, radio * 2))


def _iris(p, color, sonrisa, energia, estado, t):
    """Dos arcos sutiles dentro del orbe: cálidos en reposo, enfocados al hablar."""
    tono = AMBAR_CLARO if estado in ("escuchando", "hablando") else CELESTE_CLARO
    inicio, arco = (200, 140) if sonrisa >= 0 else (20, 140)
    pluma = QPen(alpha(tono, 115 + int(70 * energia)), 2.0)
    pluma.setCapStyle(Qt.RoundCap)
    p.setPen(pluma)
    p.setBrush(Qt.NoBrush)
    for lado in (-1, 1):
        y = -1 + 1.5 * sonrisa + 1.5 * energia * math.sin(t * 13 + lado)
        rect = QRectF(lado * 12 - 13, y - 7, 26, 14 + 4 * max(0.0, sonrisa))
        p.drawArc(rect, int(inicio * 16), int(arco * 16))


def dibujar(p, cara, color, t, tam):
    """Dibuja el núcleo completo; ``t`` es tiempo monótono en segundos."""
    estado = modo(cara)
    silenciada = estado == "silenciada"
    nivel_actual = nivel(cara)
    objetivo = 0.0 if silenciada else (
        0.25 + 0.75 * nivel_actual if estado in ("escuchando", "hablando") else 0.12)
    energia = _lerp(cara, "_energia_suave", objetivo, 0.10)
    color_suave = color_suavizado(cara, color)
    pulso = 0.0 if silenciada else (
        0.5 + 0.5 * math.sin(t * 0.8) if estado == "reposo" else 0.35 + 0.65 * energia)
    radio = _lerp(cara, "_radio_suave",
                  52 + (2.0 if estado == "reposo" else 6.0 * energia), 0.12)
    ahora = time.time()
    feliz = ahora < getattr(cara, "feliz_hasta", 0.0) or ahora < getattr(cara, "baile_hasta", 0.0)
    objetivo_sonrisa = 0.0 if silenciada else (
        0.8 if feliz or estado == "reposo" else
        0.15 if estado == "escuchando" else -0.2)
    sonrisa = _lerp(cara, "_sonrisa_suave", objetivo_sonrisa, 0.10)

    esc = tam / 280.0
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(tam / 2.0, tam / 2.0)
    p.scale(esc, esc)

    _halo(p, color_suave, energia, silenciada, t)
    _anillos(p, color_suave, estado, energia, t)
    _espectro(p, color_suave, estado, energia, t)

    orbe = QRadialGradient(QPointF(-radio * 0.18, -radio * 0.2), radio)
    orbe.setColorAt(0.0, alpha(CELESTE_CLARO if estado == "reposo" else color_suave, 255))
    orbe.setColorAt(0.45, alpha(color_suave, 225))
    orbe.setColorAt(1.0, alpha(color_suave, 55))
    p.setPen(QPen(alpha(color_suave, 80 if silenciada else 170), 1.8))
    p.setBrush(QBrush(orbe))
    p.drawEllipse(QPointF(0, 0), radio, radio)
    _iris(p, color_suave, sonrisa, energia, estado, t)

    p.setPen(Qt.NoPen)
    p.setBrush(alpha(QColor(255, 255, 255), 55 if silenciada else 150 + int(60 * pulso)))
    p.drawEllipse(QPointF(0, 0), 4 + 2 * pulso, 4 + 2 * pulso)
    p.restore()
