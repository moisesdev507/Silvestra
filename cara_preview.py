"""Vista previa de la cara nueva de Silvestra (PySide6).

Ejecuta:  python cara_preview.py
Teclas:   H = hablar/callar   P = pensando   E = escuchando   Esc = salir
Mouse:    arrastra con clic izquierdo para moverla. Los ojos te siguen.
"""
import math
import random
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

TAM = 280
CIAN = QColor(79, 209, 197)
AMARILLO = QColor(255, 209, 102)
ROSA = QColor(255, 140, 160)


def con_alpha(color, a):
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


class CaraNueva(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(TAM, TAM)

        self.estado = "reposo"  # reposo | hablando | pensando | escuchando
        self.t0 = time.time()
        self.prox_parpadeo = time.time() + 2
        self.parpadeo_ini = None
        self.arrastre = None
        self.ojo_x = 0.0
        self.ojo_y = 0.0

        pantalla = QApplication.primaryScreen().availableGeometry()
        self.move(pantalla.right() - TAM - 40, pantalla.bottom() - TAM - 40)

        self.reloj = QTimer(self)
        self.reloj.timeout.connect(self.update)
        self.reloj.start(16)

    # ---------- Entrada ----------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            QApplication.quit()
        elif k == Qt.Key_H:
            self.estado = "reposo" if self.estado == "hablando" else "hablando"
        elif k == Qt.Key_P:
            self.estado = "reposo" if self.estado == "pensando" else "pensando"
        elif k == Qt.Key_E:
            self.estado = "reposo" if self.estado == "escuchando" else "escuchando"

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.arrastre = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.arrastre is not None:
            self.move(e.globalPosition().toPoint() - self.arrastre)

    def mouseReleaseEvent(self, e):
        self.arrastre = None

    # ---------- Dibujo ----------
    def paintEvent(self, _):
        t = time.time() - self.t0
        ahora = time.time()
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)

            c = TAM / 2
            # Respiración suave y flotar
            respira = 1 + 0.015 * math.sin(t * 1.6)
            flota = 4 * math.sin(t * 1.1)
            p.translate(c, c + flota)
            p.scale(respira, respira)

            color = AMARILLO if self.estado == "escuchando" else CIAN

            # Resplandor de fondo
            g = QRadialGradient(QPointF(0, 0), 135)
            g.setColorAt(0.55, con_alpha(color, 60))
            g.setColorAt(1.0, con_alpha(color, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(0, 0), 135, 135)

            # Anillos de luz
            vel = 160 if self.estado == "pensando" else 40
            pulso = 0.5 + 0.5 * math.sin(t * (9 if self.estado == "hablando" else 2.2))
            anillos = [(118, 3.0, 1.0, 110), (106, 2.2, -1.4, 70), (128, 1.6, 0.7, 50)]
            for radio, grosor, sentido, largo in anillos:
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

            # Ojos que siguen al mouse
            cur = QCursor.pos()
            ctr = self.mapToGlobal(QPointF(c, c).toPoint())
            dx = max(-1.0, min(1.0, (cur.x() - ctr.x()) / 500.0))
            dy = max(-1.0, min(1.0, (cur.y() - ctr.y()) / 500.0))
            if self.estado == "pensando":
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
            alto = 34 * (1 - 0.92 * cierre)

            for lado in (-1, 1):
                ex = lado * 32
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
            p.setBrush(con_alpha(ROSA, 90))
            p.drawEllipse(QPointF(-55, 22), 12, 7)
            p.drawEllipse(QPointF(55, 22), 12, 7)

            # Boca
            if self.estado == "hablando":
                abre = 4 + 11 * abs(math.sin(t * 11)) * (0.6 + 0.4 * math.sin(t * 3.3) ** 2)
                p.setBrush(QColor(200, 80, 100))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(0, 38), 13, abre)
            else:
                pluma = QPen(QColor(200, 80, 100), 3)
                pluma.setCapStyle(Qt.RoundCap)
                p.setPen(pluma)
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(-14, 26, 28, 18), int(200 * 16), int(140 * 16))
        finally:
            p.end()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    cara = CaraNueva()
    cara.show()
    cara.activateWindow()
    cara.setFocus()
    sys.exit(app.exec())