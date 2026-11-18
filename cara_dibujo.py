"""Dibujo de la cara de Silvestra (lo usa cara_qt.py)."""
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QRadialGradient

TAM = 250               # tamaño de la ventana de la cara
ESC = TAM / 280.0       # escala del dibujo
CIAN = QColor(79, 209, 197)
AMARILLO = QColor(255, 209, 102)
ROSA = QColor(255, 140, 160)
GRIS = QColor(120, 132, 160)


def con_alpha(color, a):
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def pintar(self):
    """Dibuja la cara. 'self' es la ventana Cara."""
    ahora = time.time()
    t = ahora - self.t0
    feliz = ahora < self.feliz_hasta or ahora < self.baile_hasta
    pensando = self.pensando and ahora < self.pensando_hasta
    bailando = ahora < self.baile_hasta

    if not self.viva:
        color = GRIS
    elif self.escuchando:
        color = AMARILLO
    elif feliz:
        color = ROSA
    else:
        color = CIAN

    p = QPainter(self)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        c = w / 2.0
        esc = (w / 280.0)
        p.translate(c, c + 4 * math.sin(t * 1.1) * esc)
        resp = esc * (1 + 0.015 * math.sin(t * 1.6))
        p.scale(resp, resp)
        if bailando:
            p.rotate(6 * math.sin(t * 9))

        # Resplandor
        g = QRadialGradient(QPointF(0, 0), 135)
        g.setColorAt(0.55, con_alpha(color, 60))
        g.setColorAt(1.0, con_alpha(color, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), 135, 135)

        # Anillos de luz
        vel = 160 if pensando else (100 if bailando else 40)
        pulso = 0.5 + 0.5 * math.sin(t * (9 if self.hablando else 2.2))
        for radio, grosor, sentido, largo in [(118, 3.0, 1.0, 110), (106, 2.2, -1.4, 70), (128, 1.6, 0.7, 50)]:
            pluma = QPen(con_alpha(color, 140 + 90 * pulso), grosor)
            pluma.setCapStyle(Qt.RoundCap)
            p.setPen(pluma)
            p.setBrush(Qt.NoBrush)
            ini = (t * vel * sentido) % 360
            rect = QRectF(-radio, -radio, radio * 2, radio * 2)
            for k in range(3):
                p.drawArc(rect, int((ini + k * 120) * 16), int(largo * 16))

        # Cabeza
        g = QRadialGradient(QPointF(-25, -35), 120)
        g.setColorAt(0.0, QColor(255, 255, 255))
        g.setColorAt(0.6, QColor(226, 244, 246))
        g.setColorAt(1.0, QColor(160, 215, 220))
        p.setPen(QPen(con_alpha(color, 200), 2))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), 92, 88)

        # Lacito
        p.save()
        p.translate(-52, -74)
        p.rotate(-25)
        p.setPen(QPen(QColor(214, 90, 125), 2))
        p.setBrush(QColor(255, 140, 170))
        p.drawEllipse(QPointF(-11, 0), 12, 8)
        p.drawEllipse(QPointF(11, 0), 12, 8)
        p.setBrush(QColor(255, 105, 150))
        p.drawEllipse(QPointF(0, 0), 6, 6)
        p.restore()

        # Hacia dónde mira
        cur = QCursor.pos()
        ctr = self.mapToGlobal(QPointF(c, c).toPoint())
        dx = max(-1.0, min(1.0, (cur.x() - ctr.x()) / 500.0))
        dy = max(-1.0, min(1.0, (cur.y() - ctr.y()) / 500.0))
        if self.mx:
            dx = self.mx / 5.0
        if pensando:
            dx, dy = 0.5 * math.sin(t * 2), -0.7
        self.ojo_x += (dx * 7 - self.ojo_x) * 0.15
        self.ojo_y += (dy * 5 - self.ojo_y) * 0.15

        # Parpadeo
        if self.parpadeo_ini is None and ahora >= self.prox_parpadeo:
            self.parpadeo_ini = ahora
        cierre = 0.0
        if self.parpadeo_ini is not None:
            f = (ahora - self.parpadeo_ini) / 0.18
            if f >= 1:
                self.parpadeo_ini = None
                self.prox_parpadeo = ahora + random.uniform(2, 5)
            else:
                cierre = math.sin(f * math.pi)
        if not self.viva:
            cierre = max(cierre, 0.6)  # dormida: ojitos entrecerrados
        alto = 34 * (1 - 0.92 * cierre)

        # Cejitas
        elevar = -5 if (pensando or self.escuchando) else (-3 if feliz else 0)
        pluma = QPen(QColor(70, 90, 105), 3)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        for lado in (-1, 1):
            ex = lado * 32
            p.drawArc(QRectF(ex - 11 + self.ojo_x * 0.4, -42 + elevar, 22, 10), int(30 * 16), int(120 * 16))

        # Ojos
        for lado in (-1, 1):
            ex = lado * 32
            if feliz:
                pluma = QPen(QColor(35, 55, 70), 4)
                pluma.setCapStyle(Qt.RoundCap)
                p.setPen(pluma)
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(ex - 12, -18, 24, 20), 0, int(180 * 16))
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(35, 55, 70))
            p.drawEllipse(QPointF(ex + self.ojo_x, -8 + self.ojo_y), 14, alto / 2 + 2)
            if cierre < 0.5:
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(ex + self.ojo_x + 5, -15 + self.ojo_y), 4.5, 4.5)
                p.setBrush(con_alpha(QColor(255, 255, 255), 200))
                p.drawEllipse(QPointF(ex + self.ojo_x - 4, -3 + self.ojo_y), 2.2, 2.2)

        # Mejillas
        p.setPen(Qt.NoPen)
        p.setBrush(con_alpha(ROSA, 140 if feliz else 90))
        p.drawEllipse(QPointF(-55, 22), 12, 7)
        p.drawEllipse(QPointF(55, 22), 12, 7)

        # Boca
        if self.hablando:
            abre = 4 + 11 * abs(math.sin(t * 11)) * (0.6 + 0.4 * math.sin(t * 3.3) ** 2)
            p.setBrush(QColor(200, 80, 100))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 38), 13, abre)
        else:
            pluma = QPen(QColor(200, 80, 100), 3)
            pluma.setCapStyle(Qt.RoundCap)
            p.setPen(pluma)
            p.setBrush(Qt.NoBrush)
            if feliz:
                p.drawArc(QRectF(-18, 24, 36, 24), int(200 * 16), int(140 * 16))
            else:
                p.drawArc(QRectF(-14, 26, 28, 18), int(200 * 16), int(140 * 16))
    finally:
        p.end()