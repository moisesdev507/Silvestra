"""Fondo espacial cinematográfico con parallax y anillo de energía para Silvestra."""
import math
import random
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient

from escenario_estilo import COLOR_FONDO_BASE, COLOR_CIAN_BRILLO, COLOR_CIAN_MEDIO


class FondoEscenario:
    """Fondo de ciencia ficción con movimiento suave y anillo de energía."""

    def __init__(self):
        self.particulas_fondo = []
        self.particulas_frente = []
        self.fase = 0.0
        self.angulo_anillo = 0.0

    def inicializar(self, w, h):
        self.particulas_fondo = []
        for _ in range(18):
            self.particulas_fondo.append({
                "x": random.uniform(10, w - 10),
                "y": random.uniform(10, h - 10),
                "vx": random.uniform(-0.15, 0.15),
                "vy": random.uniform(-0.15, 0.15),
                "r": random.uniform(1.2, 2.0),
            })
        self.particulas_frente = []
        for _ in range(12):
            self.particulas_frente.append({
                "x": random.uniform(10, w - 10),
                "y": random.uniform(10, h - 10),
                "vx": random.uniform(-0.35, 0.35),
                "vy": random.uniform(-0.35, 0.35),
                "r": random.uniform(2.2, 3.5),
            })

    def avanzar(self, w, h):
        self.fase = (self.fase + 1.2) % 360.0
        self.angulo_anillo = (self.angulo_anillo + 1.5) % 360.0
        if not self.particulas_fondo:
            self.inicializar(w, h)

        for p in self.particulas_fondo:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["x"] < 0 or p["x"] > w: p["vx"] *= -1
            if p["y"] < 0 or p["y"] > h: p["vy"] *= -1

        for p in self.particulas_frente:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["x"] < 0 or p["x"] > w: p["vx"] *= -1
            if p["y"] < 0 or p["y"] > h: p["vy"] *= -1

    def dibujar(self, p: QPainter, w, h, silv_cx, silv_cy, silv_tam, voz_hablando=False):
        p.setRenderHint(QPainter.Antialiasing)

        # 1. Lienzo base azul noche muy oscuro
        p.fillRect(0, 0, w, h, COLOR_FONDO_BASE)

        # 2. Cuadrícula suave con sutil respiración
        respiro = 1.0 + 0.006 * math.sin(math.radians(self.fase))
        paso_grid = int(75 * respiro)
        p.setPen(QPen(QColor(20, 35, 65, 35), 1))
        for x in range(0, w, paso_grid):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, paso_grid):
            p.drawLine(0, y, w, y)

        # 3. Partículas de fondo (capa lenta)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(56, 189, 248, 40))
        for pt in self.particulas_fondo:
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["r"], pt["r"])

        # 4. Partículas de frente (capa dinámica con conexiones cercanas)
        n = len(self.particulas_frente)
        for i in range(n):
            pi = self.particulas_frente[i]
            for j in range(i + 1, n):
                pj = self.particulas_frente[j]
                dist = math.hypot(pi["x"] - pj["x"], pi["y"] - pj["y"])
                if dist < 120:
                    alpha = int(40 * (1.0 - dist / 120.0))
                    p.setPen(QPen(QColor(6, 182, 212, alpha), 1))
                    p.drawLine(QPointF(pi["x"], pi["y"]), QPointF(pj["x"], pj["y"]))

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(125, 211, 252, 75))
        for pt in self.particulas_frente:
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["r"], pt["r"])

        # 5. Anillo de energía cinematográfico alrededor de Silvestra
        self._dibujar_anillo_silvestra(p, silv_cx, silv_cy, silv_tam, voz_hablando)

    def _dibujar_anillo_silvestra(self, p: QPainter, cx, cy, tam, voz_hablando):
        radio = tam * 0.62
        pulso = math.sin(math.radians(self.fase * 2.0))
        r_dinamico = radio + (pulso * 4.0 if voz_hablando else pulso * 1.5)

        # Aura radial
        aura = QRadialGradient(cx, cy, r_dinamico * 1.4)
        col_aura = QColor(6, 182, 212, 100 if voz_hablando else 45)
        aura.setColorAt(0.5, col_aura)
        aura.setColorAt(1.0, QColor(4, 8, 18, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(aura)
        p.drawEllipse(QPointF(cx, cy), r_dinamico * 1.4, r_dinamico * 1.4)

        # Anillo giratorio de segmentos
        ang = self.angulo_anillo
        p.setPen(QPen(COLOR_CIAN_MEDIO, 1.8))
        p.drawArc(int(cx - r_dinamico), int(cy - r_dinamico), int(r_dinamico * 2), int(r_dinamico * 2),
                  int(ang * 16), int(110 * 16))
        p.drawArc(int(cx - r_dinamico), int(cy - r_dinamico), int(r_dinamico * 2), int(r_dinamico * 2),
                  int((ang + 180) * 16), int(90 * 16))

        # Puntos baliza cardinales
        for delta in (0, 90, 180, 270):
            rad = math.radians(ang + delta)
            bx = cx + (r_dinamico + 6) * math.cos(rad)
            by = cy + (r_dinamico + 6) * math.sin(rad)
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_CIAN_BRILLO)
            p.drawEllipse(QPointF(bx, by), 2.5, 2.5)
