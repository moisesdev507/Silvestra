"""Panel del Anillo Inteligente con renderizado 3D holográfico para el Modo Escenario."""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient

from escenario_estilo import (
    COLOR_CIAN_BRILLO, COLOR_CIAN_MEDIO, COLOR_TEXTO_BLANCO,
    COLOR_TEXTO_ATENUADO, COLOR_AMBAR_ACENTO, dibujar_panel_marco
)
from escenario_paneles import _dibujar_encabezado_animado

ICONOS_GESTOS = {
    "palma": "🖐️",
    "puno": "✊",
    "paz": "✌️",
    "uno": "☝️",
}

TEXTO_ACCION = {
    "encender_luz": "Luz encendida",
    "apagar_luz": "Luz apagada",
    "encender_ventilador": "Ventilador encendido",
    "apagar_ventilador": "Ventilador apagado",
    "abrir_puerta": "Puerta abierta",
    "cerrar_puerta": "Puerta cerrada",
}


class PanelAnillo:
    """Maneja la escena del anillo inteligente: rotación 3D, ondas y reacción a gestos."""

    def __init__(self):
        self.angulo = 0.0
        self.pulso = 0.0
        self.onda = 0.0
        self.ultimo_gesto = None  # (gesto, accion, nombre, es_manual)
        self.tiempo_gesto = 0.0

    def avanzar(self):
        """Avanza los fotogramas de animación a 30 FPS."""
        self.angulo = (self.angulo + 0.035) % (2.0 * math.pi)
        self.pulso = (self.pulso + 0.06) % (2.0 * math.pi)
        if self.onda > 0.0:
            self.onda = max(0.0, self.onda - 0.025)

    def registrar_gesto(self, datos):
        """Registra un gesto detectado (por cámara o manual) para hacer reaccionar el anillo."""
        self.ultimo_gesto = datos
        self.tiempo_gesto = time.time()
        self.onda = 1.0

    def dibujar(self, p: QPainter, rect: QRectF, app, anim_fase: float):
        dibujar_panel_marco(p, rect, brillo_intenso=(self.onda > 0.2))
        _dibujar_encabezado_animado(
            p, rect,
            "ANILLO INTELIGENTE // CONTROL GESTUAL Y DOMÓTICA",
            "Prototipo wearable de interacción espacial y domótica",
            anim_fase
        )

        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

        # 1. ZONA IZQUIERDA: Anillo holográfico 3D
        rw = w * 0.40
        rcx = x + rw * 0.52
        rcy = y + h * 0.54
        self._dibujar_anillo_3d(p, rcx, rcy, min(rw * 0.44, h * 0.36))

        # 2. ZONA DERECHA: Datos en vivo, gestos y domótica
        dx = x + rw + 10
        dw = w - rw - 35
        self._dibujar_tarjetas(p, dx, y + 80, dw, h - 100, app)

    def _dibujar_anillo_3d(self, p: QPainter, cx: float, cy: float, r_base: float):
        """Renderiza el anillo holográfico con inclinación en perspectiva y rotación continua."""
        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        # Efecto de pulso y onda de choque si hubo gesto
        factor_pulso = 1.0 + 0.03 * math.sin(self.pulso)
        r = r_base * factor_pulso

        # Halo resplandeciente exterior
        g_halo = QRadialGradient(cx, cy, r * 1.6)
        col_halo = QColor(6, 182, 212, int(45 + 50 * self.onda))
        g_halo.setColorAt(0.0, col_halo)
        g_halo.setColorAt(1.0, QColor(4, 8, 18, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g_halo)
        p.drawEllipse(QPointF(cx, cy), r * 1.6, r * 1.3)

        # Onda expansiva al detectar gesto
        if self.onda > 0.0:
            r_onda = r * (1.1 + 0.7 * (1.0 - self.onda))
            col_onda = QColor(56, 189, 248, int(180 * self.onda))
            p.setPen(QPen(col_onda, 2.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r_onda, r_onda * 0.65)

        # Geometría con perspectiva (inclinación ~62 grados)
        rx, ry = r, r * 0.52
        rx_int, ry_int = rx * 0.74, ry * 0.74

        # Grosor metálico
        g_cuerpo = QLinearGradient(cx - rx, cy - ry, cx + rx, cy + ry)
        fase_luz = (math.sin(self.angulo) + 1.0) / 2.0
        g_cuerpo.setColorAt(0.0, QColor(14, 116, 144, 160))
        g_cuerpo.setColorAt(max(0.0, min(1.0, fase_luz * 0.8)), COLOR_CIAN_BRILLO)
        g_cuerpo.setColorAt(1.0, QColor(6, 78, 99, 180))

        # Elipse exterior
        p.setPen(QPen(COLOR_CIAN_BRILLO, 2.5))
        p.setBrush(g_cuerpo)
        p.drawEllipse(QPointF(cx, cy), rx, ry)

        # Elipse interior (hueco del dedo)
        p.setPen(QPen(QColor(14, 116, 144), 1.5))
        p.setBrush(QColor(8, 14, 28, 240))
        p.drawEllipse(QPointF(cx, cy), rx_int, ry_int)

        # Sensor joya / LED emisor en la superficie del anillo
        gem_ang = self.angulo
        gem_x = cx + rx * math.cos(gem_ang) * 0.88
        gem_y = cy + ry * math.sin(gem_ang) * 0.88

        # Resplandor de la joya
        g_joya = QRadialGradient(gem_x, gem_y, 16)
        col_joya = COLOR_AMBAR_ACENTO if self.onda > 0.1 else COLOR_CIAN_BRILLO
        g_joya.setColorAt(0.0, col_joya)
        g_joya.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g_joya)
        p.drawEllipse(QPointF(gem_x, gem_y), 16, 16)

        p.setBrush(COLOR_TEXTO_BLANCO)
        p.drawEllipse(QPointF(gem_x, gem_y), 3.5, 3.5)

        # Etiqueta bajo el anillo
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.setPen(COLOR_CIAN_BRILLO)
        p.drawText(QRectF(cx - 100, cy + ry + 16, 200, 22), Qt.AlignCenter, "SILVESTRA WEARABLE // ESP32")
        p.restore()

    def _dibujar_tarjetas(self, p: QPainter, x: float, y: float, w: float, h: float, app):
        """Dibuja el panel de estado gestual, domótica y modo manual."""
        camara_activa = bool(hasattr(app, "camara") and getattr(app.camara, "activa", False))

        # Tarjeta 1: Último gesto detectado
        p.setPen(QPen(COLOR_AMBAR_ACENTO if self.onda > 0.2 else QColor(51, 65, 85), 1.5))
        p.setBrush(QColor(15, 23, 42, 230))
        p.drawRoundedRect(QRectF(x, y, w, 82), 10, 10)

        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.setPen(COLOR_TEXTO_ATENUADO)
        p.drawText(QRectF(x + 16, y + 8, w - 32, 20), Qt.AlignLeft, "ESTADO GESTUAL // INTERACCIÓN EN VIVO")

        if self.ultimo_gesto and (time.time() - self.tiempo_gesto < 9.0):
            g, acc, nom, es_man = self.ultimo_gesto
            icono = ICONOS_GESTOS.get(g, "✨")
            accion_txt = TEXTO_ACCION.get(acc, acc.replace("_", " ").title())
            origen = " [TECLADO]" if es_man else " [CÁMARA]"

            p.setFont(QFont("Segoe UI Emoji", 20))
            p.drawText(int(x + 16), int(y + 32), 40, 40, Qt.AlignCenter, icono)

            p.setFont(QFont("Segoe UI", 13, QFont.Bold))
            p.setPen(COLOR_AMBAR_ACENTO if es_man else COLOR_CIAN_BRILLO)
            p.drawText(QRectF(x + 64, y + 34, w - 74, 24), Qt.AlignLeft, f"{nom.upper()}{origen} ➔ {accion_txt}")

            p.setFont(QFont("Segoe UI", 9))
            p.setPen(COLOR_TEXTO_BLANCO)
            p.drawText(QRectF(x + 64, y + 56, w - 74, 18), Qt.AlignLeft, "Acción domótica ejecutada con éxito")
        else:
            p.setFont(QFont("Segoe UI", 11))
            p.setPen(COLOR_TEXTO_ATENUADO)
            msg = "Esperando gesto frente a la cámara o presiona teclas 1, 2 o 3..." if camara_activa else "Modo manual listo: presiona teclas [1], [2] o [3] para controlar..."
            p.drawText(QRectF(x + 16, y + 36, w - 32, 26), Qt.AlignLeft, msg)

        # Tarjeta 2: Dispositivos domóticos reales
        ty2 = y + 92
        p.setPen(QPen(QColor(51, 65, 85), 1.0))
        p.setBrush(QColor(10, 16, 28, 200))
        p.drawRoundedRect(QRectF(x, ty2, w, 70), 10, 10)

        luz = getattr(app.casa, "luz", False) if hasattr(app, "casa") else False
        vent = getattr(app.casa, "ventilador", False) if hasattr(app, "casa") else False
        puerta = getattr(app.casa, "puerta", False) if hasattr(app, "casa") else False

        col_w = (w - 24) / 3.0
        dispositivos = [
            ("Luz Sala", luz, "💡", "ENCENDIDA" if luz else "APAGADA"),
            ("Ventilador", vent, "🌀", "ACTIVO" if vent else "APAGADO"),
            ("Puerta", puerta, "🚪", "ABIERTA" if puerta else "CERRADA"),
        ]
        for i, (nombre, enc, icono, st_txt) in enumerate(dispositivos):
            cx_d = x + 12 + i * col_w
            col_st = COLOR_AMBAR_ACENTO if enc else COLOR_TEXTO_ATENUADO
            p.setFont(QFont("Segoe UI", 10, QFont.Bold))
            p.setPen(COLOR_TEXTO_BLANCO)
            p.drawText(QRectF(cx_d, ty2 + 10, col_w, 20), Qt.AlignCenter, f"{icono} {nombre}")
            p.setFont(QFont("Segoe UI", 11, QFont.Bold))
            p.setPen(col_st)
            p.drawText(QRectF(cx_d, ty2 + 34, col_w, 22), Qt.AlignCenter, st_txt)

        # Tarjeta 3: Explicación de arquitectura y hardware wearable
        ty3 = ty2 + 80
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.setPen(COLOR_CIAN_BRILLO if camara_activa else COLOR_AMBAR_ACENTO)
        st_sensor = "• SENSOR: CÁMARA ACTIVA (MediaPipe Hands en vivo)" if camara_activa else "• SENSOR: MODO MANUAL ACTIVO (Cámara apagada)"
        p.drawText(QRectF(x + 4, ty3, w - 8, 20), Qt.AlignLeft, st_sensor)

        p.setFont(QFont("Segoe UI", 10))
        p.setPen(COLOR_TEXTO_BLANCO)
        p.drawText(QRectF(x + 4, ty3 + 24, w - 8, 38), Qt.AlignLeft,
                   "Visión de investigación: El anillo integrará sensor inercial (IMU 6 ejes) y Bluetooth Low Energy.\n"
                   "Hoy la visión por computadora simula con precisión los mismos comandos de control del hogar.")

        # Respaldo manual en texto discreto al pie
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.setPen(COLOR_TEXTO_ATENUADO)
        p.drawText(QRectF(x + 4, y + h - 22, w - 8, 18), Qt.AlignRight, "(modo manual: teclas 1-2-3)")
