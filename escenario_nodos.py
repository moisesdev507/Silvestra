"""Arco de nodos discreto y paquetes de datos animados hacia Silvestra."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient

from escenario_estilo import COLOR_CIAN_BRILLO, COLOR_TEXTO_BLANCO, COLOR_TEXTO_ATENUADO

LISTA_NODOS = [
    ("cerebro", "CEREBRO", "🧠"),
    ("voz", "VOZ", "🗣"),
    ("oido", "OÍDO", "👂"),
    ("vision", "VISIÓN", "👁"),
    ("casa", "CASA", "🏠"),
    ("memoria", "MEMORIA", "💾"),
    ("estudio", "ESTUDIO", "📚"),
]


class ArcoNodos:
    """Renderiza el arco de nodos horizontal superior y los impulsos de datos."""

    def __init__(self):
        self.pulso_t = 0.0

    def avanzar(self):
        self.pulso_t = (self.pulso_t + 0.04) % 1.0

    def dibujar(self, p: QPainter, rect: QRectF, nodo_activo, voz_hablando, silv_cx, silv_cy):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        n = len(LISTA_NODOS)
        step_x = rect.width() / float(n)
        cy = rect.center().y()

        nodo_activo_pos = None

        # Línea guía horizontal del arco
        p.setPen(QPen(QColor(14, 116, 144, 45), 1.5, Qt.DashLine))
        p.drawLine(rect.left(), cy, rect.right(), cy)

        for i, (clave, titulo, icono) in enumerate(LISTA_NODOS):
            nx = rect.left() + (i + 0.5) * step_x
            esta_activo = (nodo_activo == clave) or (clave == "voz" and voz_hablando)

            if esta_activo:
                nodo_activo_pos = (nx, cy)

            # Píldora del nodo
            pw, ph = min(step_x - 8.0, 78.0), 30.0
            px, py = nx - pw / 2.0, cy - ph / 2.0
            r_nodo = QRectF(px, py, pw, ph)

            if esta_activo:
                # Resplandor activo
                p.setPen(QPen(COLOR_CIAN_BRILLO, 2.0))
                p.setBrush(QColor(8, 51, 68, 240))
                p.drawRoundedRect(r_nodo, 8, 8)

                # Punto baliza luminoso
                p.setPen(Qt.NoPen)
                p.setBrush(COLOR_CIAN_BRILLO)
                p.drawEllipse(QPointF(px + 10, cy), 3.5, 3.5)

                p.setFont(QFont("Segoe UI", 9, QFont.Bold))
                p.setPen(COLOR_TEXTO_BLANCO)
                p.drawText(QRectF(px + 16, py, pw - 20, ph), Qt.AlignCenter, titulo)
            else:
                p.setPen(QPen(QColor(30, 41, 59, 120), 1.0))
                p.setBrush(QColor(10, 16, 28, 180))
                p.drawRoundedRect(r_nodo, 8, 8)

                p.setFont(QFont("Segoe UI", 8))
                p.setPen(COLOR_TEXTO_ATENUADO)
                p.drawText(r_nodo, Qt.AlignCenter, titulo)

        # Paquete de datos que viaja del nodo activo hacia Silvestra
        if nodo_activo_pos is not None:
            nx, ny = nodo_activo_pos
            # Línea de traza hacia Silvestra
            p.setPen(QPen(QColor(6, 182, 212, 60), 1.5, Qt.DotLine))
            ctrl_x = (nx + silv_cx) / 2.0
            ctrl_y = min(ny, silv_cy) - 40.0
            p.drawLine(QPointF(nx, ny), QPointF(silv_cx, silv_cy))

            # Impulso de luz animado
            t = self.pulso_t
            px = nx + (silv_cx - nx) * t
            py = ny + (silv_cy - ny) * t
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_CIAN_BRILLO)
            p.drawEllipse(QPointF(px, py), 4.5, 4.5)

        p.restore()
