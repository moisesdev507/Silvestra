"""Casa inteligente de juguete: un panel que Silvestra controla por voz y por gestos."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

import acciones


class Casa(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Casa inteligente - Silvestra")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(430, 200)
        self.luz = False
        self.ventilador = False
        self.puerta = False
        self.angulo = 0.0
        g = QApplication.primaryScreen().geometry()
        self.move(30, g.height() - 300)
        self.reloj = QTimer(self)
        self.reloj.timeout.connect(self._tic)
        self.reloj.start(40)

    def poner(self, que, valor):
        setattr(self, que, valor)
        if not self.isVisible():
            self.show()
        self.update()

    def _tic(self):
        if self.ventilador:
            self.angulo = (self.angulo + 14) % 360
        if self.isVisible():
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor("#1b2333"))
            p.setPen(QColor("#4fd1c5"))
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            p.drawText(QRectF(0, 6, 430, 28), Qt.AlignCenter, "Casa inteligente")
            tarjetas = [("Luz", self.luz), ("Ventilador", self.ventilador), ("Puerta", self.puerta)]
            for i, (nombre, on) in enumerate(tarjetas):
                x = 12 + i * 138
                p.setPen(QPen(QColor("#4fd1c5") if on else QColor("#3a4358"), 2))
                p.setBrush(QColor("#232d42"))
                p.drawRoundedRect(QRectF(x, 40, 128, 150), 14, 14)
                cx, cy = x + 64, 95
                if i == 0:
                    self._luz(p, cx, cy, on)
                elif i == 1:
                    self._ventilador(p, cx, cy, on)
                else:
                    self._puerta(p, cx, cy, on)
                p.setPen(QColor("white"))
                p.setFont(QFont("Segoe UI", 10, QFont.Bold))
                p.drawText(QRectF(x, 140, 128, 22), Qt.AlignCenter, nombre)
                p.setPen(QColor("#ffd166") if on else QColor("#7d8aa6"))
                p.setFont(QFont("Segoe UI", 9))
                estado = ("ABIERTA" if on else "CERRADA") if i == 2 else ("ENCENDIDO" if on else "APAGADO")
                p.drawText(QRectF(x, 160, 128, 20), Qt.AlignCenter, estado)
        finally:
            p.end()

    @staticmethod
    def _luz(p, cx, cy, on):
        if on:
            g = QRadialGradient(QPointF(cx, cy), 48)
            g.setColorAt(0.0, QColor(255, 220, 120, 200))
            g.setColorAt(1.0, QColor(255, 220, 120, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, cy), 48, 48)
        p.setPen(QPen(QColor("#8b95ad"), 2))
        p.setBrush(QColor("#ffd166") if on else QColor("#3a4358"))
        p.drawEllipse(QPointF(cx, cy - 4), 22, 22)
        p.setBrush(QColor("#8b95ad"))
        p.drawRect(QRectF(cx - 9, cy + 16, 18, 10))

    def _ventilador(self, p, cx, cy, on):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4fd1c5") if on else QColor("#3a4358"))
        for k in range(3):
            p.save()
            p.translate(cx, cy)
            p.rotate(self.angulo + k * 120)
            p.drawEllipse(QPointF(0, -18), 8, 18)
            p.restore()
        p.setBrush(QColor("#8b95ad"))
        p.drawEllipse(QPointF(cx, cy), 6, 6)

    @staticmethod
    def _puerta(p, cx, cy, on):
        p.setPen(QPen(QColor("#8b95ad"), 2))
        p.setBrush(QColor("#10151f"))
        p.drawRect(QRectF(cx - 20, cy - 32, 40, 64))
        p.setBrush(QColor("#a9743f"))
        if on:
            p.drawRect(QRectF(cx - 20, cy - 32, 12, 64))
        else:
            p.drawRect(QRectF(cx - 20, cy - 32, 40, 64))
            p.setBrush(QColor("#ffd166"))
            p.drawEllipse(QPointF(cx + 12, cy + 2), 3, 3)


def instalar(app):
    casa = Casa()

    def reg(nombre, funcion, descripcion):
        acciones.registrar(nombre, funcion, descripcion)

    reg("mostrar_casa", casa.show, "muestra el panel de la casa inteligente")
    reg("ocultar_casa", casa.hide, "oculta el panel de la casa inteligente")
    reg("encender_luz", lambda: casa.poner("luz", True), "enciende la luz de la casa inteligente")
    reg("apagar_luz", lambda: casa.poner("luz", False), "apaga la luz de la casa inteligente")
    reg("encender_ventilador", lambda: casa.poner("ventilador", True), "enciende el ventilador de la casa inteligente")
    reg("apagar_ventilador", lambda: casa.poner("ventilador", False), "apaga el ventilador de la casa inteligente")
    reg("abrir_puerta", lambda: casa.poner("puerta", True), "abre la puerta de la casa inteligente")
    reg("cerrar_puerta", lambda: casa.poner("puerta", False), "cierra la puerta de la casa inteligente")

    def apagar_todo():
        casa.luz = casa.ventilador = casa.puerta = False
        casa.show()
        casa.update()

    reg("apagar_todo", apagar_todo, "apaga todo en la casa inteligente y cierra la puerta")
    return casa