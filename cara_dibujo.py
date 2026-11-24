"""Dibujo de la cara de Silvestra con expresiones emocionales, sincronía labial y vida en reposo."""
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QRadialGradient

import cara_baile
import cara_sincronia

TAM = 208               # tamaño compacto de la ventana de la cara (-17%)
ESC = TAM / 280.0       # escala proporcional del dibujo
CIAN = QColor(79, 209, 197)
AMARILLO = QColor(255, 209, 102)
ROSA = QColor(255, 140, 160)
GRIS = QColor(120, 132, 160)

import cara_emociones


def color_estado(viva, escuchando, hablando, feliz=False, base=None):
    """Celeste en reposo; amarillo solo al escuchar o hablar (gris si no viva)."""
    if not viva:
        return GRIS
    if escuchando or hablando:
        return AMARILLO
    if feliz:
        return ROSA
    return base if base is not None else CIAN

# Perfiles de expresión y rasgos faciales (delegados a cara_emociones)
PERFILES_EMOCION = cara_emociones.RASGOS_FACIALES


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

    # Suavizado de transición emocional orgánico (factor ~0.14 por cuadro para evitar cambios bruscos)
    emo_clave = getattr(self, "emocion_objetivo", "neutral") or "neutral"
    t_cejas_y, t_cejas_ang, t_ojos_ap, t_boca_curva, t_boca_ancho, t_rubor, t_color = (
        cara_emociones.obtener_rasgos(emo_clave)
    )

    factor = 0.14
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

    color = color_estado(
        self.viva, self.escuchando, getattr(self, "hablando", False),
        feliz, color_emocion,
    )

    p = QPainter(self)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        c = w / 2.0
        esc = (w / 280.0)

        # Microgestos de reposo, microexpresiones al escuchar y asentimiento suave
        inclinacion = 0.0
        y_asentir = 0.0
        asentir_limite = getattr(self, "asentir_hasta", 0.0)
        if asentir_limite > ahora:
            t_asentir = ahora - (asentir_limite - 0.55)
            y_asentir = 4.2 * math.sin(max(0.0, min(1.0, t_asentir / 0.55)) * math.pi)

        if self.escuchando and self.viva and not bailando:
            # Leve inclinación atenta y curiosa al escuchar al dueño
            inclinacion = 2.6 * math.sin(t * 0.9)
            y_resp = 1.8 * math.sin(t * 1.0) * esc
            resp_escala = esc * (1 + 0.007 * math.sin(t * 1.0))
        elif not self.hablando and self.viva and not bailando:
            # Respiración sutil y pausada en reposo
            inclinacion = 1.0 * math.sin(t * 0.6) * math.sin(t * 0.25)
            y_resp = 2.2 * math.sin(t * 0.9) * esc
            resp_escala = esc * (1 + 0.008 * math.sin(t * 1.1))
        else:
            y_resp = 3.6 * math.sin(t * 1.1) * esc
            resp_escala = esc * (1 + 0.012 * math.sin(t * 1.5))

        b_dx = getattr(self, "baile_dx", 0.0) if bailando else 0.0
        b_dy = getattr(self, "baile_dy", 0.0) if bailando else 0.0
        p.translate(c + b_dx, c + y_resp + y_asentir + b_dy)
        p.scale(resp_escala, resp_escala)

        tilt_mov = getattr(self, "tilt", 0.0)
        tilt_baile = getattr(self, "baile_tilt", 0.0)
        if bailando:
            p.rotate(tilt_baile or (6.0 * math.sin(t * 9)))
        elif abs(tilt_mov) > 0.1:
            p.rotate(tilt_mov)
        elif inclinacion:
            p.rotate(inclinacion)

        # Resplandor
        g = QRadialGradient(QPointF(0, 0), 135)
        g.setColorAt(0.55, con_alpha(color, 60))
        g.setColorAt(1.0, con_alpha(color, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), 135, 135)

        # Anillos HUD reactivos por modo operativo y ritmo (100% en memoria)
        modo_act = getattr(self, "modo_activo", "normal")
        silvestra = getattr(self, "silvestra_app", None) or getattr(self, "_ref_app", None)
        if silvestra and hasattr(silvestra, "modo_activo") and silvestra.modo_activo:
            modo_act = silvestra.modo_activo
            self.modo_activo = modo_act

        esta_activa = bool(self.escuchando or self.hablando or pensando or bailando)
        c_a1, c_a2, vel_a, pulso_a = cara_baile.obtener_estilo_anillos(modo_act, bailando, t)

        if not self.viva:
            c_a1, c_a2, vel_a, pulso_a = GRIS, GRIS, 6.0, 0.1
        elif not esta_activa:
            # En reposo o con micrófono inactivo: aros cian/verde calmados
            c_a1, c_a2 = CIAN, QColor(16, 185, 129)
            vel_a = 24.0
            pulso_a = 0.3 + 0.2 * math.sin(t * 1.4)
        elif pensando:
            c_a1, c_a2 = AMARILLO, CIAN
            vel_a = 160.0
            pulso_a = 0.8 + 0.2 * math.sin(t * 8.0)
        elif self.escuchando:
            c_a1, c_a2 = AMARILLO, QColor(245, 158, 11)
            vel_a = 75.0
            pulso_a = 0.7 + 0.3 * math.sin(t * 5.0)
        elif self.hablando:
            c_a1, c_a2 = AMARILLO, QColor(245, 158, 11)
            vel_a = 90.0
            pulso_a = 0.6 + 0.4 * math.sin(t * 6.5)

        for radio, grosor, sentido, largo, use_c2 in [
            (118, 3.0, 1.0, 110, False),
            (106, 2.2, -1.4, 70, True),
            (128, 1.6, 0.7, 50, False),
        ]:
            c_sel = c_a2 if use_c2 else c_a1
            pluma = QPen(con_alpha(c_sel, 140 + 90 * pulso_a), grosor)
            pluma.setCapStyle(Qt.RoundCap)
            p.setPen(pluma)
            p.setBrush(Qt.NoBrush)
            ini = (t * vel_a * sentido) % 360
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

        # Hacia dónde mira: seguimiento suave de rostro (cámara) o cursor con límites naturales
        ref_cam = getattr(self, "_ref_camara", None)
        rostro_pos = getattr(ref_cam, "ult_pos_rostro", None) if ref_cam else None
        t_rostro = getattr(ref_cam, "t_ult_pos_rostro", 0.0) if ref_cam else 0.0

        if rostro_pos and (ahora - t_rostro < 3.0) and not pensando and self.viva and not bailando:
            # Rostro detectado por cámara: movimiento hacia el dueño
            rx, ry = rostro_pos
            dx = max(-1.0, min(1.0, -rx)) * 0.85
            dy = max(-1.0, min(1.0, ry)) * 0.75
        elif (self.escuchando or self.hablando) and not pensando and self.viva:
            # Al escuchar o hablar, centra la mirada al frente
            dx, dy = 0.0, 0.0
        elif not pensando and self.viva and not bailando:
            # Seguimiento suave del cursor acotado dentro de los límites del ojo (cálculo directo en memoria)
            cur = QCursor.pos()
            ctr_x = self.x() + c
            ctr_y = self.y() + c
            raw_dx = (cur.x() - ctr_x) / 420.0
            raw_dy = (cur.y() - ctr_y) / 350.0
            dist_sq = (raw_dx / 1.0) ** 2 + (raw_dy / 0.8) ** 2
            if dist_sq > 1.0:
                dist = math.sqrt(dist_sq)
                dx = raw_dx / dist
                dy = (raw_dy / dist) * 0.8
            else:
                dx = raw_dx
                dy = raw_dy
        else:
            dx, dy = 0.0, 0.0

        if not pensando and self.viva:
            if ahora >= self.prox_micro_sac:
                self.micro_sac_x = random.uniform(-1.2, 1.2)
                self.micro_sac_y = random.uniform(-0.8, 0.8)
                self.prox_micro_sac = ahora + random.uniform(2.5, 5.5)
        else:
            self.micro_sac_x = 0.0
            self.micro_sac_y = 0.0

        if self.mx:
            dx = self.mx / 5.0
        if pensando:
            dx, dy = 0.5 * math.sin(t * 2), -0.7

        # Transición suave (factor 0.12) para mirada fluida y orgánica sin saltos
        self.ojo_x += ((dx * 7.5 + self.micro_sac_x) - self.ojo_x) * 0.12
        self.ojo_y += ((dy * 5.2 + self.micro_sac_y) - self.ojo_y) * 0.12

        # Parpadeo natural cada 2.5 a 6 s con variación de duración y parpadeo doble
        if self.parpadeo_ini is None and ahora >= self.prox_parpadeo:
            self.parpadeo_ini = ahora
            self.dur_parpadeo = random.uniform(0.14, 0.20)

        cierre = 0.0
        if self.parpadeo_ini is not None:
            dur = getattr(self, "dur_parpadeo", 0.17)
            f = (ahora - self.parpadeo_ini) / dur
            if f >= 1:
                self.parpadeo_ini = None
                # 20% probabilidad de parpadeo doble
                if random.random() < 0.20:
                    self.prox_parpadeo = ahora + random.uniform(0.16, 0.30)
                else:
                    self.prox_parpadeo = ahora + random.uniform(2.5, 6.0)
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

        # El estado y la forma los calcula la sincronía; Qt solo dibuja.
        moviendo, apertura, ancho_boca = cara_sincronia.forma_boca(self, t, ahora)
        if moviendo:
            self.boca_abre = apertura
            p.setBrush(QColor(200, 80, 100))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 38), ancho_boca, max(2.5, apertura))
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

        # Partículas musicales cuando baila
        if bailando:
            gestor_b = getattr(self, "_gestor_baile", None)
            if gestor_b is None:
                gestor_b = cara_baile.obtener_gestor_baile()
                self._gestor_baile = gestor_b
            gestor_b.actualizar_particulas(ahora)
            gestor_b.dibujar_particulas(p)
    finally:
        p.end()
