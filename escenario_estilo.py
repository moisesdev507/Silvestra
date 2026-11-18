"""Estilo visual de ciencia ficción y cálculo de zonas proporcionales para el Modo Escenario."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient

# Paleta Sci-Fi sobria y cinematográfica
COLOR_FONDO_BASE = QColor(4, 8, 18)
COLOR_CIAN_BRILLO = QColor(56, 189, 248)
COLOR_CIAN_MEDIO = QColor(6, 182, 212)
COLOR_AZUL_BORDE = QColor(14, 116, 144)
COLOR_TEXTO_BLANCO = QColor(248, 250, 252)
COLOR_TEXTO_ATENUADO = QColor(148, 163, 184)
COLOR_AMBAR_ACENTO = QColor(245, 158, 11)


def calcular_zonas(w, h):
    """Calcula las zonas proporcionales para que nunca se superpongan en 1080p, 768p o cualquier resolución."""
    h_barras = max(24.0, h * 0.04)

    # Zona Silvestra (Izquierda)
    cara_tam = int(min(w * 0.24, h * 0.42))
    cara_cx = w * 0.18
    cara_cy = h * 0.48
    cara_rect = QRectF(cara_cx - cara_tam / 2.0, cara_cy - cara_tam / 2.0, cara_tam, cara_tam)

    # Zona Nodos (Arco en la parte superior-derecha)
    nodos_rect = QRectF(w * 0.38, h * 0.09, w * 0.58, h * 0.10)

    # Zona Panel de Escena (Centro-Derecha, sin tocar a Silvestra)
    panel_x = w * 0.38
    panel_y = h * 0.20
    panel_w = w * 0.58
    panel_h = h * 0.59
    panel_rect = QRectF(panel_x, panel_y, panel_w, panel_h)

    # Zona Subtítulos (Abajo de extremo a extremo)
    sub_w = w * 0.92
    sub_h = max(58.0, h * 0.09)
    sub_x = (w - sub_w) / 2.0
    sub_y = h - h_barras - sub_h - max(8.0, h * 0.015)
    sub_rect = QRectF(sub_x, sub_y, sub_w, sub_h)

    return {
        "h_barras": h_barras,
        "cara_tam": cara_tam,
        "cara_cx": cara_cx,
        "cara_cy": cara_cy,
        "cara_rect": cara_rect,
        "nodos_rect": nodos_rect,
        "panel_rect": panel_rect,
        "sub_rect": sub_rect,
    }


def dibujar_cinematica(p: QPainter, w, h, h_barras):
    """Dibuja barras negras de película (cinemascope) y viñeta suave en esquinas."""
    # Barras letterbox
    p.fillRect(0, 0, w, int(h_barras), QColor(0, 0, 0))
    p.fillRect(0, int(h - h_barras), w, int(h_barras), QColor(0, 0, 0))

    p.setPen(QPen(QColor(14, 165, 233, 40), 1))
    p.drawLine(0, int(h_barras), w, int(h_barras))
    p.drawLine(0, int(h - h_barras), w, int(h - h_barras))

    # Viñeta suave
    cx, cy = w / 2.0, h / 2.0
    diag = math.hypot(cx, cy)
    vineta = QRadialGradient(cx, cy, diag)
    vineta.setColorAt(0.0, QColor(0, 0, 0, 0))
    vineta.setColorAt(0.70, QColor(0, 0, 0, 40))
    vineta.setColorAt(1.0, QColor(2, 4, 10, 190))
    p.setPen(Qt.NoPen)
    p.setBrush(vineta)
    p.drawRect(0, 0, w, h)


def dibujar_panel_marco(p: QPainter, rect: QRectF, brillo_intenso=False):
    """Dibuja un panel de cristal oscuro con esquinas angulares y resplandor cian."""
    p.save()
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

    # Fondo de cristal oscuro con gradiente
    grad = QLinearGradient(x, y, x, y + h)
    grad.setColorAt(0.0, QColor(10, 18, 34, 235))
    grad.setColorAt(1.0, QColor(4, 9, 20, 245))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(rect, 14, 14)

    # Borde de resplandor
    col_borde = QColor(56, 189, 248, 120 if brillo_intenso else 65)
    p.setPen(QPen(col_borde, 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect, 14, 14)

    # Escuadras angulares en las 4 esquinas (estilo visor táctico)
    c_len = 16.0
    p.setPen(QPen(COLOR_CIAN_BRILLO, 2.0))
    # Superior izquierda
    p.drawLine(QPointF(x, y + c_len), QPointF(x, y))
    p.drawLine(QPointF(x, y), QPointF(x + c_len, y))
    # Superior derecha
    p.drawLine(QPointF(x + w - c_len, y), QPointF(x + w, y))
    p.drawLine(QPointF(x + w, y), QPointF(x + w, y + c_len))
    # Inferior izquierda
    p.drawLine(QPointF(x, y + h - c_len), QPointF(x, y + h))
    p.drawLine(QPointF(x, y + h), QPointF(x + c_len, y + h))
    # Inferior derecha
    p.drawLine(QPointF(x + w - c_len, y + h), QPointF(x + w, y + h))
    p.drawLine(QPointF(x + w, y + h), QPointF(x + w, y + h - c_len))

    p.restore()
import math
