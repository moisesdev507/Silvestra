"""Secuencia de arranque de ciencia ficción al iniciar el Modo Escenario."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen

from escenario_estilo import COLOR_CIAN_BRILLO, COLOR_TEXTO_BLANCO, COLOR_TEXTO_ATENUADO

PASOS_BOOT = [
    (12, "01", "CEREBRO LLM (Groq / Gemini / OpenRouter) .... ONLINE"),
    (28, "02", "SÍNTESIS DE VOZ NEURONAL (Edge-TTS) ......... ONLINE"),
    (44, "03", "RECONOCIMIENTO OÍDO (Whisper + Vosk) ........ ONLINE"),
    (60, "04", "VISIÓN MULTIMODAL (Qwen / YuNet / MediaPipe)  ONLINE"),
    (76, "05", "DOMÓTICA IOT (Casa Inteligente) ............. ONLINE"),
    (92, "06", "MEMORIA DURADERA Y APRENDIZAJE .............. ONLINE"),
    (108, "07", "NÚCLEO PRINCIPAL AUTÓNOMO ................. 100%"),
]


class SecuenciaArranque:
    """Maneja los ~4 segundos de animación de arranque inicial del escenario."""

    def __init__(self, duracion_cuadros=120):
        self.duracion = duracion_cuadros
        self.cuadro = 0
        self.activo = True

    def reiniciar(self):
        self.cuadro = 0
        self.activo = True

    def avanzar(self):
        if self.activo:
            self.cuadro += 1
            if self.cuadro >= self.duracion:
                self.activo = False

    def terminado(self):
        return not self.activo

    def dibujar(self, p: QPainter, w, h):
        """Dibuja la consola cinematográfica de arranque en el centro de la pantalla."""
        p.save()
        cx, cy = w / 2.0, h / 2.0
        bw, bh = min(w * 0.72, 780.0), min(h * 0.58, 380.0)
        bx, by = cx - bw / 2.0, cy - bh / 2.0
        rect_boot = QRectF(bx, by, bw, bh)

        # Fondo oscuro del terminal
        p.setPen(QPen(QColor(14, 165, 233, 90), 1.5))
        p.setBrush(QColor(6, 11, 24, 245))
        p.drawRoundedRect(rect_boot, 12, 12)

        # Encabezado terminal
        p.setFont(QFont("Segoe UI", 12, QFont.Bold))
        p.setPen(COLOR_CIAN_BRILLO)
        p.drawText(QRectF(bx + 25, by + 18, bw - 50, 26), Qt.AlignLeft,
                   "// SILVESTRA ARCHITECTURE // INICIALIZANDO PROTOCOLO DEMO")

        # Porcentaje de carga y barra
        pct = min(100, int((self.cuadro / float(self.duracion - 10)) * 100))
        p.setFont(QFont("Segoe UI", 24, QFont.Bold))
        p.setPen(COLOR_TEXTO_BLANCO)
        p.drawText(QRectF(bx + bw - 130, by + 12, 105, 36), Qt.AlignRight, f"{pct}%")

        # Barra de progreso estilizada
        bar_x, bar_y, bar_w, bar_h = bx + 25, by + 52, bw - 50, 8.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(15, 23, 42))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)

        if pct > 0:
            prog_w = (bar_w * pct) / 100.0
            grad_bar = QLinearGradient(bar_x, bar_y, bar_x + prog_w, bar_y)
            grad_bar.setColorAt(0.0, QColor(6, 182, 212))
            grad_bar.setColorAt(1.0, COLOR_CIAN_BRILLO)
            p.setBrush(grad_bar)
            p.drawRoundedRect(QRectF(bar_x, bar_y, prog_w, bar_h), 4, 4)

        # Líneas de diagnóstico que se van marcando
        p.setFont(QFont("Lucida Console", 10))
        line_y = by + 76
        for f_act, num, desc in PASOS_BOOT:
            if self.cuadro >= f_act:
                p.setPen(COLOR_CIAN_BRILLO)
                p.drawText(QRectF(bx + 25, line_y, 45, 20), Qt.AlignLeft, f"[{num}]")
                p.setPen(COLOR_TEXTO_BLANCO)
                p.drawText(QRectF(bx + 75, line_y, bw - 100, 20), Qt.AlignLeft, desc)
            else:
                p.setPen(QColor(51, 65, 85))
                p.drawText(QRectF(bx + 25, line_y, 45, 20), Qt.AlignLeft, f"[{num}]")
                p.drawText(QRectF(bx + 75, line_y, bw - 100, 20), Qt.AlignLeft, "PENDIENTE ...")
            line_y += 26

        # Estado inferior
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(COLOR_TEXTO_ATENUADO)
        msg_sub = "Cargando modelos y calibrando sensores..." if pct < 100 else "¡TODOS LOS SISTEMAS OPERATIVOS!"
        p.drawText(QRectF(bx + 25, by + bh - 32, bw - 50, 22), Qt.AlignCenter, msg_sub)

        p.restore()
