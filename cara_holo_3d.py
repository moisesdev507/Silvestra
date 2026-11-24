"""Motor Holográfico Giroscópico 3D para Lyris.

Proyección 3D en perspectiva con ordenamiento Z, red neuronal interna,
anillos giroscópicos con separación delantera/trasera y ecualizador radial reactivo.
"""
import math
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QRadialGradient

DIST_CAM = 340.0
N_NODOS = 28

# 1. Nodos de Fibonacci y aristas geodésicas en esfera unitaria
_NODOS_BASE: list[tuple[float, float, float]] = []
_PHI = (1.0 + math.sqrt(5.0)) / 2.0
_ANG_DORADO = math.tau / (_PHI * _PHI)

for i in range(N_NODOS):
    y = 1.0 - (i / float(N_NODOS - 1)) * 2.0
    r_xy = math.sqrt(max(0.0, 1.0 - y * y))
    theta = i * _ANG_DORADO
    _NODOS_BASE.append((r_xy * math.cos(theta), y, r_xy * math.sin(theta)))

_ARISTAS_BASE: list[tuple[int, int]] = []
for i in range(N_NODOS):
    for j in range(i + 1, N_NODOS):
        xi, yi, zi = _NODOS_BASE[i]
        xj, yj, zj = _NODOS_BASE[j]
        d2 = (xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2
        if d2 < 0.68:  # Conexión vecina cercana en esfera unitaria
            _ARISTAS_BASE.append((i, j))


def _alpha(c: QColor, a: int) -> QColor:
    cl = QColor(c)
    cl.setAlpha(max(0, min(255, int(a))))
    return cl


def rotar_3d(x: float, y: float, z: float, pitch: float, yaw: float, roll: float = 0.0) -> tuple[float, float, float]:
    if roll:
        cr, sr = math.cos(roll), math.sin(roll)
        x, y = x * cr - y * sr, x * sr + y * cr
    if pitch:
        cp, sp = math.cos(pitch), math.sin(pitch)
        y, z = y * cp - z * sp, y * sp + z * cp
    if yaw:
        cy, sy = math.cos(yaw), math.sin(yaw)
        x, z = x * cy + z * sy, -x * sy + z * cy
    return x, y, z


def proyectar_3d(x: float, y: float, z: float) -> tuple[float, float, float, float]:
    k = DIST_CAM / (DIST_CAM + z)
    return x * k, y * k, k, z


def obtener_inclinacion_cursor(p: QPainter) -> tuple[float, float]:
    """Seguimiento físico del mouse: calcula pitch y yaw sin tocar cara_qt.py."""
    try:
        dev = p.device()
        if dev is not None and hasattr(dev, "mapToGlobal"):
            w = int(getattr(dev, "width", lambda: 208)())
            h = int(getattr(dev, "height", lambda: 208)())
            centro = dev.mapToGlobal(QPoint(w // 2, h // 2))
            cur = QCursor.pos()
            dx = (cur.x() - centro.x()) / 380.0
            dy = (cur.y() - centro.y()) / 380.0
            return max(-0.35, min(0.35, -dy)), max(-0.35, min(0.35, dx))
    except Exception:
        pass
    return 0.0, 0.0


def _calcular_segmentos_anillo(r_anillo: float, pitch_anillo: float, yaw_anillo: float,
                               vel_roll: float, t: float, pitch_cur: float, yaw_cur: float):
    n_pts = 32
    step = math.tau / n_pts
    pts_3d = []
    for i in range(n_pts + 1):
        ang = (i % n_pts) * step
        x = r_anillo * math.cos(ang)
        y = r_anillo * math.sin(ang)
        z = 0.0
        x, y, z = rotar_3d(x, y, z, pitch_anillo, yaw_anillo, t * vel_roll)
        x, y, z = rotar_3d(x, y, z, pitch_cur, yaw_cur)
        px, py, k, pz = proyectar_3d(x, y, z)
        pts_3d.append((px, py, k, pz, ang))

    seg_traseros = []
    seg_delanteros = []
    for i in range(n_pts):
        p1 = pts_3d[i]
        p2 = pts_3d[i + 1]
        z_med = (p1[3] + p2[3]) * 0.5
        if z_med < 0.0:
            seg_traseros.append((p1, p2, z_med))
        else:
            seg_delanteros.append((p1, p2, z_med))
    return seg_traseros, seg_delanteros


def dibujar_giroscopios_traseros(p: QPainter, col: dict, est: str, t: float, r: float,
                                 pitch: float, yaw: float, factor_exp: float = 1.0):
    """Dibuja los arcos 3D que caen detrás de la esfera (z < 0)."""
    p.save()
    anillos = [
        (r + 14.0 * factor_exp, 0.42, 0.20, 1.35, col["halo"], 1.1),
        (r + 25.0 * factor_exp, -0.50, -0.35, -1.05, col["acento"], 1.4),
        (r + 36.0 * factor_exp, 0.30, 0.60, 0.80, col["centro"], 1.0),
    ]
    for r_a, p_a, y_a, v_r, c_pen, w_pen in anillos:
        traseros, _ = _calcular_segmentos_anillo(r_a, p_a, y_a, v_r, t, pitch, yaw)
        for p1, p2, z_med in traseros:
            alfa = int(35 + 30 * (1.0 + z_med / (r_a * 1.5)))
            p.setPen(QPen(_alpha(c_pen, alfa), w_pen, Qt.DashLine if est in ("pensando", "experto") else Qt.SolidLine))
            p.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))
    p.restore()


def dibujar_giroscopios_delanteros(p: QPainter, col: dict, est: str, t: float, r: float,
                                   pitch: float, yaw: float, factor_exp: float = 1.0):
    """Dibuja los arcos técnicos luminosos y cabezas que pasan por delante (z >= 0)."""
    p.save()
    anillos = [
        (r + 14.0 * factor_exp, 0.42, 0.20, 1.35, col["halo"], 1.6),
        (r + 25.0 * factor_exp, -0.50, -0.35, -1.05, col["acento"], 2.0),
        (r + 36.0 * factor_exp, 0.30, 0.60, 0.80, col["centro"], 1.4),
    ]
    for r_a, p_a, y_a, v_r, c_pen, w_pen in anillos:
        _, delanteros = _calcular_segmentos_anillo(r_a, p_a, y_a, v_r, t, pitch, yaw)
        if not delanteros:
            continue
        max_z_pt = max(delanteros, key=lambda s: s[2])
        for p1, p2, z_med in delanteros:
            prof = max(0.0, min(1.0, z_med / r_a))
            alfa = int(100 + 140 * prof)
            p.setPen(QPen(_alpha(c_pen, alfa), w_pen * (0.8 + 0.4 * prof), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))

        # Nodo brillante delantero (cabeza del giroscopio)
        pt_cabeza = max_z_pt[0]
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_alpha(col["acento"], 245)))
        p.drawEllipse(QPointF(pt_cabeza[0], pt_cabeza[1]), 2.2 * pt_cabeza[2], 2.2 * pt_cabeza[2])
    p.restore()


def dibujar_red_neuronal_3d(p: QPainter, col: dict, est: str, t: float, r: float,
                            pitch: float, yaw: float, rms: float):
    """Núcleo geodésico 3D: 28 nodos de Fibonacci y sinapsis ordenadas por profundidad."""
    r_red = r * 0.66
    vel_red = 0.55 if est != "pensando" else 1.35
    if est == "silenciada": vel_red = 0.05

    # 1. Proyectar todos los nodos
    nodos_proj = []
    for i, (bx, by, bz) in enumerate(_NODOS_BASE):
        # Pulsación orgánica según RMS y estado
        radio_i = r_red * (1.0 + 0.15 * rms * math.sin(t * 8.0 + i))
        x, y, z = bx * radio_i, by * radio_i, bz * radio_i
        x, y, z = rotar_3d(x, y, z, 0.25, t * vel_red)
        x, y, z = rotar_3d(x, y, z, pitch, yaw)
        px, py, k, pz = proyectar_3d(x, y, z)
        nodos_proj.append((px, py, k, pz))

    # 2. Dibujar aristas ordenadas por profundidad media
    aristas_ordenadas = []
    for i, j in _ARISTAS_BASE:
        p1, p2 = nodos_proj[i], nodos_proj[j]
        aristas_ordenadas.append((p1, p2, (p1[3] + p2[3]) * 0.5))
    aristas_ordenadas.sort(key=lambda item: item[2])

    p.save()
    for p1, p2, z_med in aristas_ordenadas:
        norm_z = (z_med + r_red) / (2.0 * r_red)
        norm_z = max(0.0, min(1.0, norm_z))
        alfa_linea = int(25 + 130 * norm_z)
        if est == "silenciada": alfa_linea = int(alfa_linea * 0.4)
        c_linea = col["plasma2"] if z_med < 0 else col["plasma1"]
        p.setPen(QPen(_alpha(c_linea, alfa_linea), 0.9 + 0.6 * norm_z))
        p.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))

    # 3. Dibujar nodos (círculos) con luminosidad según z
    nodos_proj.sort(key=lambda n: n[3])
    for px, py, k, pz in nodos_proj:
        norm_z = max(0.0, min(1.0, (pz + r_red) / (2.0 * r_red)))
        alfa_nodo = int(40 + 200 * norm_z)
        radio_nodo = (1.2 + 1.4 * norm_z) * k
        if est == "experto":
            col_nodo = col["acento"] if pz > 0 else col["centro"]
        else:
            col_nodo = col["centro"] if pz > 0 else col["medio"]
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_alpha(col_nodo, alfa_nodo)))
        p.drawEllipse(QPointF(px, py), radio_nodo, radio_nodo)
    p.restore()


def dibujar_ecualizador_radial(p: QPainter, col: dict, est: str, t: float, r: float, rms: float):
    """32 barras radiales alrededor del núcleo que laten con el audio RMS y micro-armónicos."""
    n_barras = 32
    step = math.tau / n_barras
    r_in = r + 2.0
    p.save()
    for i in range(n_barras):
        ang = i * step + t * 0.20
        c, s = math.cos(ang), math.sin(ang)
        # Altura dinámica: base sutil en reposo, saltos vivos al hablar con RMS
        onda = 0.5 + 0.5 * math.sin(i * 1.8 + t * 14.0)
        longitud = 1.6 + (14.0 * rms) * (0.35 + 0.65 * onda)
        if est == "pensando":
            longitud += 2.0 * (0.5 + 0.5 * math.sin(i * 3.0 + t * 6.0))
        elif est == "experto":
            longitud += 3.0 * (0.5 + 0.5 * math.cos(i * 2.0 + t * 4.0))

        alfa = int(60 + 180 * min(1.0, rms * 1.5 + 0.2))
        if est == "silenciada": alfa = 30; longitud = 1.0
        p1 = QPointF(r_in * c, r_in * s)
        p2 = QPointF((r_in + longitud) * c, (r_in + longitud) * s)
        c_barra = col["acento"] if (i % 4 == 0) else col["halo"]
        p.setPen(QPen(_alpha(c_barra, alfa), 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(p1, p2)
    p.restore()


def dibujar_particulas_3d(p: QPainter, col: dict, est: str, t: float, r: float, pitch: float, yaw: float):
    """Micro-partículas que orbitan en 3D con halo difuso delantero."""
    if est == "silenciada": return
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(10):
        vel = 0.65 + (i % 4) * 0.18
        ang = t * vel + i * (math.tau / 10.0)
        r_orb = r + 16.0 + (i % 4) * 6.5
        incl = (i - 5) * 0.14
        x = r_orb * math.cos(ang)
        y = r_orb * math.sin(ang) * math.cos(incl)
        z = r_orb * math.sin(ang) * math.sin(incl)
        x, y, z = rotar_3d(x, y, z, pitch, yaw)
        px, py, k, pz = proyectar_3d(x, y, z)
        if pz > -10.0:  # Mostrar partículas frontales y laterales
            alfa = int(80 + 160 * max(0.0, min(1.0, (pz + 10.0) / (r_orb * 0.8))))
            p.setBrush(QBrush(_alpha(col["acento"], alfa)))
            p.drawEllipse(QPointF(px, py), 1.3 * k, 1.3 * k)
    p.restore()
