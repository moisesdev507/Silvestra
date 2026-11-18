"""Dibujo de la cara de Silvestra con expresiones emocionales, sincronía labial y vida en reposo."""
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

# Perfiles de expresión por emoción
# (cejas_y, cejas_ang, ojos_apertura, boca_curva, boca_ancho, rubor_alpha, color_base)
PERFILES_EMOCION = {
    "neutral":    ( 0.0,   0.0, 1.00,  1.0, 28.0,  90.0, QColor(79, 209, 197)),
    "alegre":     (-3.5,   2.5, 1.06,  1.5, 34.0, 140.0, QColor(52, 211, 153)),
    "animada":    (-6.0,   3.5, 1.15,  1.8, 36.0, 160.0, QColor(251, 191, 36)),
    "calida":     (-2.0,   1.5, 0.96,  1.2, 30.0, 140.0, QColor(244, 114, 182)),
    "seria":      ( 2.5,  -3.5, 0.84,  0.1, 22.0,  55.0, QColor(96, 165, 250)),
    "preocupada": (-4.5,   5.5, 1.08, -0.3, 24.0,  80.0, QColor(167, 139, 250)),
}


def con_alpha(color, a):
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def _asegurar_atributos(self):
    """Inicializa los estados de suavizado si no existen en la instancia Cara."""
    if not hasattr(self, "_exp_inicializada"):
        self._exp_inicializada = True
        self.val_cejas_y = 0.0
        self.val_cejas_ang = 0.0
        self.val_ojos_apertura = 1.0
        self.val_boca_curva = 1.0
        self.val_boca_ancho = 28.0
        self.val_rubor = 90.0
        self.val_color_r = float(CIAN.red())
        self.val_color_g = float(CIAN.green())
        self.val_color_b = float(CIAN.blue())
        self.boca_abre = 0.0
        self.micro_sac_x = 0.0
        self.micro_sac_y = 0.0
        self.prox_micro_sac = time.time() + 2.5
        self.ultimo_cursor_pos = None


def pintar(self):
    """Dibuja la cara con expresiones interpoladas y sincronía labial sin bloquear Qt."""
    _asegurar_atributos(self)
    ahora = time.time()
    t = ahora - self.t0
    feliz = ahora < self.feliz_hasta or ahora < self.baile_hasta
    pensando = self.pensando and ahora < self.pensando_hasta
    bailando = ahora < self.baile_hasta

    # Suavizado de transición emocional (~300 ms a 30 FPS: factor ~0.22 por cuadro)
    emo_clave = getattr(self, "emocion_objetivo", "neutral") or "neutral"
    t_cejas_y, t_cejas_ang, t_ojos_ap, t_boca_curva, t_boca_ancho, t_rubor, t_color = (
        PERFILES_EMOCION.get(emo_clave, PERFILES_EMOCION["neutral"])
    )

    factor = 0.22
    self.val_cejas_y += (t_cejas_y - self.val_cejas_y) * factor
    self.val_cejas_ang += (t_cejas_ang - self.val_cejas_ang) * factor
    self.val_ojos_apertura += (t_ojos_ap - self.val_ojos_apertura) * factor
    self.val_boca_curva += (t_boca_curva - self.val_boca_curva) * factor
    self.val_boca_ancho += (t_boca_ancho - self.val_boca_ancho) * factor
    self.val_rubor += (t_rubor - self.val_rubor) * factor

    self.val_color_r += (t_color.red() - self.val_color_r) * factor
    self.val_color_g += (t_color.green() - self.val_color_g) * factor
    self.val_color_b += (t_color.blue() - self.val_color_b) * factor
    color_emocion = QColor(int(self.val_color_r), int(self.val_color_g), int(self.val_color_b))

    if not self.viva:
        color = GRIS
    elif self.escuchando:
        color = AMARILLO
    elif feliz:
        color = ROSA
    else:
        color = color_emocion

    p = QPainter(self)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        c = w / 2.0
        esc = (w / 280.0)

        # Microgestos de reposo: respiración orgánica e inclinación leve
        inclinacion_reposo = 0.0
        if not self.hablando and self.viva and not bailando:
            inclinacion_reposo = 1.2 * math.sin(t * 0.7) * math.sin(t * 0.25)
            y_resp = 3.5 * math.sin(t * 1.2) * esc
            resp_escala = esc * (1 + 0.012 * math.sin(t * 1.6))
        else:
            y_resp = 4.0 * math.sin(t * 1.1) * esc
            resp_escala = esc * (1 + 0.015 * math.sin(t * 1.6))

        p.translate(c, c + y_resp)
        p.scale(resp_escala, resp_escala)

        if bailando:
            p.rotate(6 * math.sin(t * 9))
        elif inclinacion_reposo:
            p.rotate(inclinacion_reposo)

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

        # Hacia dónde mira + micro-miradas sacádicas en reposo
        cur = QCursor.pos()
        ctr = self.mapToGlobal(QPointF(c, c).toPoint())
        dx = max(-1.0, min(1.0, (cur.x() - ctr.x()) / 500.0))
        dy = max(-1.0, min(1.0, (cur.y() - ctr.y()) / 500.0))

        if self.ultimo_cursor_pos == cur and not pensando and self.viva:
            if ahora >= self.prox_micro_sac:
                self.micro_sac_x = random.uniform(-1.8, 1.8)
                self.micro_sac_y = random.uniform(-1.2, 1.2)
                self.prox_micro_sac = ahora + random.uniform(2.5, 5.0)
        else:
            self.ultimo_cursor_pos = cur
            self.micro_sac_x = 0.0
            self.micro_sac_y = 0.0

        if self.mx:
            dx = self.mx / 5.0
        if pensando:
            dx, dy = 0.5 * math.sin(t * 2), -0.7

        self.ojo_x += ((dx * 7 + self.micro_sac_x) - self.ojo_x) * 0.15
        self.ojo_y += ((dy * 5 + self.micro_sac_y) - self.ojo_y) * 0.15

        # Parpadeo natural cada 3 a 6 s con variación de parpadeo doble
        if self.parpadeo_ini is None and ahora >= self.prox_parpadeo:
            self.parpadeo_ini = ahora

        cierre = 0.0
        if self.parpadeo_ini is not None:
            f = (ahora - self.parpadeo_ini) / 0.17
            if f >= 1:
                self.parpadeo_ini = None
                # 18% probabilidad de parpadeo doble rápido
                if random.random() < 0.18:
                    self.prox_parpadeo = ahora + random.uniform(0.18, 0.32)
                else:
                    self.prox_parpadeo = ahora + random.uniform(3.0, 6.0)
            else:
                cierre = math.sin(f * math.pi)

        if not self.viva:
            cierre = max(cierre, 0.6)  # dormida: ojitos entrecerrados
        alto = 34 * (1 - 0.92 * cierre)

        # Cejitas expresivas con curvatura e inclinación
        elevar = -5 if (pensando or self.escuchando) else (-3 if feliz else self.val_cejas_y)
        pluma = QPen(QColor(70, 90, 105), 3)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        for lado in (-1, 1):
            ex = lado * 32
            ang_lado = -lado * self.val_cejas_ang
            p.save()
            p.translate(ex - 11 + self.ojo_x * 0.4 + 11, -42 + elevar + 5)
            p.rotate(ang_lado)
            p.drawArc(QRectF(-11, -5, 22, 10), int(30 * 16), int(120 * 16))
            p.restore()

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
            alto_ojo = (alto / 2 + 2) * self.val_ojos_apertura
            p.drawEllipse(QPointF(ex + self.ojo_x, -8 + self.ojo_y), 14, alto_ojo)
            if cierre < 0.5:
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(ex + self.ojo_x + 5, -15 + self.ojo_y), 4.5, 4.5)
                p.setBrush(con_alpha(QColor(255, 255, 255), 200))
                p.drawEllipse(QPointF(ex + self.ojo_x - 4, -3 + self.ojo_y), 2.2, 2.2)

        # Mejillas sonrojadas
        p.setPen(Qt.NoPen)
        p.setBrush(con_alpha(ROSA, 140 if feliz else self.val_rubor))
        p.drawEllipse(QPointF(-55, 22), 12, 7)
        p.drawEllipse(QPointF(55, 22), 12, 7)

        # Boca con sincronía labial RMS / animación suave silábica
        if self.hablando:
            nivel_rms = getattr(self, "nivel_volumen", -1.0)
            if nivel_rms >= 0.0:
                abre_target = 3.0 + 15.0 * min(1.0, nivel_rms * 1.6)
            else:
                fase_silaba = (math.sin(t * 11.5) * 0.5 + 0.5) * (0.6 + 0.4 * math.sin(t * 3.3) ** 2)
                abre_target = 3.5 + 11.0 * fase_silaba

            self.boca_abre += (abre_target - self.boca_abre) * 0.35
            ancho_boca = max(11.0, self.val_boca_ancho * 0.48)
            p.setBrush(QColor(200, 80, 100))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 38), ancho_boca, max(2.5, self.boca_abre))
        else:
            self.boca_abre = 0.0
            pluma = QPen(QColor(200, 80, 100), 3)
            pluma.setCapStyle(Qt.RoundCap)
            p.setPen(pluma)
            p.setBrush(Qt.NoBrush)
            if feliz:
                p.drawArc(QRectF(-18, 24, 36, 24), int(200 * 16), int(140 * 16))
            else:
                w_boca = self.val_boca_ancho
                h_boca = max(4.0, 18.0 * abs(self.val_boca_curva))
                if self.val_boca_curva >= 0:
                    p.drawArc(QRectF(-w_boca / 2.0, 26, w_boca, h_boca), int(200 * 16), int(140 * 16))
                else:
                    p.drawArc(QRectF(-w_boca / 2.0, 38 - h_boca, w_boca, h_boca), int(20 * 16), int(140 * 16))
    finally:
        p.end()
