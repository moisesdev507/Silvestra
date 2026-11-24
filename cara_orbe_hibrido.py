"""Renderizador Holograma 2.0: Esfera Fresnel 3D + Plasma Aditivo + Halo Táctico HUD.

Vectorial ligero con QPainter (sin QGraphicsBlurEffect ni shaders por píxel).
Pintado con CompositionMode_Plus para filamentos tipo Siri y HUD táctico J.A.R.V.I.S.
"""
import math
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

PALETAS = {
    "reposo": {
        "centro": QColor(140, 245, 255), "medio": QColor(34, 211, 238),
        "borde": QColor(14, 116, 144), "halo": QColor(56, 189, 248),
        "acento": QColor(186, 230, 253), "plasma1": QColor(6, 182, 212),
        "plasma2": QColor(14, 165, 233), "plasma3": QColor(99, 102, 241),
    },
    "escuchando": {
        "centro": QColor(254, 243, 199), "medio": QColor(45, 212, 191),
        "borde": QColor(13, 148, 136), "halo": QColor(52, 211, 153),
        "acento": QColor(251, 191, 36), "plasma1": QColor(20, 184, 166),
        "plasma2": QColor(16, 185, 129), "plasma3": QColor(245, 158, 11),
    },
    "pensando": {
        "centro": QColor(224, 242, 254), "medio": QColor(14, 165, 233),
        "borde": QColor(3, 105, 161), "halo": QColor(56, 189, 248),
        "acento": QColor(255, 255, 255), "plasma1": QColor(3, 105, 161),
        "plasma2": QColor(56, 189, 248), "plasma3": QColor(129, 140, 248),
    },
    "experto": {
        "centro": QColor(253, 230, 138), "medio": QColor(168, 85, 247),
        "borde": QColor(107, 33, 168), "halo": QColor(217, 70, 239),
        "acento": QColor(245, 158, 11), "plasma1": QColor(192, 38, 211),
        "plasma2": QColor(147, 51, 234), "plasma3": QColor(234, 179, 8),
    },
    "hablando": {
        "centro": QColor(255, 251, 235), "medio": QColor(245, 158, 11),
        "borde": QColor(180, 83, 9), "halo": QColor(251, 191, 36),
        "acento": QColor(254, 240, 138), "plasma1": QColor(234, 88, 12),
        "plasma2": QColor(245, 158, 11), "plasma3": QColor(251, 191, 36),
    },
    "bailando": {
        "centro": QColor(255, 240, 245), "medio": QColor(244, 63, 94),
        "borde": QColor(168, 85, 247), "halo": QColor(6, 182, 212),
        "acento": QColor(250, 204, 21), "plasma1": QColor(244, 63, 94),
        "plasma2": QColor(168, 85, 247), "plasma3": QColor(6, 182, 212),
    },
    "silenciada": {
        "centro": QColor(148, 163, 184), "medio": QColor(100, 116, 139),
        "borde": QColor(51, 65, 85), "halo": QColor(71, 85, 105),
        "acento": QColor(148, 163, 184), "plasma1": QColor(71, 85, 105),
        "plasma2": QColor(100, 116, 139), "plasma3": QColor(148, 163, 184),
    },
}

_ABISMO = QColor(6, 12, 24, 215)  # Cristal abisal ~84% opaco


def _interp_col(c1: QColor, c2: QColor, f: float) -> QColor:
    f = max(0.0, min(1.0, f))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * f),
        int(c1.green() + (c2.green() - c1.green()) * f),
        int(c1.blue() + (c2.blue() - c1.blue()) * f),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * f),
    )


def _alpha(c: QColor, a: int) -> QColor:
    cl = QColor(c)
    cl.setAlpha(max(0, min(255, int(a))))
    return cl


class GestorOrbeHibrido:
    def __init__(self):
        self.estado_actual = "reposo"
        self.modo_experto_activo = False
        self.area_experto = "general"
        self.rms_suave = 0.0
        self.radio_suave = 52.0
        self.ang_halo_1 = 0.0
        self.ang_halo_2 = 180.0
        self.ang_ticks = 0.0
        self.t_anterior = 0.0
        self._colores_suaves = dict(PALETAS["reposo"])

    def fijar_modo_experto(self, activo: bool, area: str = "general"):
        self.modo_experto_activo = bool(activo)
        self.area_experto = str(area or "general")

    def deducir_estado(self, cara) -> str:
        if getattr(cara, "voz_silenciada", False): return "silenciada"
        ahora = time.time()
        if ahora < getattr(cara, "baile_hasta", 0.0): return "bailando"
        if getattr(cara, "hablando", False): return "hablando"
        if getattr(cara, "escuchando", False): return "escuchando"
        if self.modo_experto_activo or getattr(cara, "modo_experto", False): return "experto"
        if getattr(cara, "pensando", False) or ahora < getattr(cara, "pensando_hasta", 0.0): return "pensando"
        return "reposo"

    def actualizar(self, cara, t: float, nivel_rms: float) -> str:
        dt = 0.016 if not self.t_anterior else max(0.001, min(0.1, t - self.t_anterior))
        self.t_anterior = t
        est = self.deducir_estado(cara)
        self.estado_actual = est

        factor_rms = 0.35 if nivel_rms > self.rms_suave else 0.15
        self.rms_suave += (max(0.0, min(1.0, nivel_rms)) - self.rms_suave) * factor_rms

        pal_dest = PALETAS.get(est, PALETAS["reposo"])
        for k in self._colores_suaves:
            self._colores_suaves[k] = _interp_col(self._colores_suaves[k], pal_dest[k], 0.12)

        if est == "silenciada": vel_1, vel_2, vel_t = 0.0, 0.0, 0.0
        elif est == "reposo": vel_1, vel_2, vel_t = 16.0, -12.0, 4.0
        elif est == "escuchando": vel_1, vel_2, vel_t = 42.0, -36.0, 12.0
        elif est in ("pensando", "experto"): vel_1, vel_2, vel_t = 88.0, -75.0, 24.0
        elif est == "hablando":
            v = self.rms_suave
            vel_1, vel_2, vel_t = 32.0 + 85.0 * v, -(28.0 + 75.0 * v), 8.0 + 20.0 * v
        else: vel_1, vel_2, vel_t = 120.0, -110.0, 35.0

        self.ang_halo_1 = (self.ang_halo_1 + vel_1 * dt) % 360.0
        self.ang_halo_2 = (self.ang_halo_2 + vel_2 * dt) % 360.0
        self.ang_ticks = (self.ang_ticks + vel_t * dt) % 360.0
        return est

    def dibujar_orbe(self, p: QPainter, cara, t: float, tam: float):
        nivel_raw = float(getattr(cara, "nivel_volumen", 0.0) or 0.0)
        if getattr(cara, "voz_silenciada", False): nivel_raw = 0.0
        est = self.actualizar(cara, t, nivel_raw)

        esc = tam / 280.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(tam / 2.0, tam / 2.0)
        p.scale(esc, esc)

        col = self._colores_suaves
        resp = 0.5 + 0.5 * math.sin(t * (math.tau / 3.5))
        r_base = 51.0 + (2.5 * resp if est == "reposo" else 0.0)
        if est == "hablando": r_base += 11.0 * self.rms_suave
        elif est == "experto": r_base += 4.0 + 2.0 * math.sin(t * 3.2)

        self.radio_suave += (r_base - self.radio_suave) * 0.15
        r_n = self.radio_suave

        self._dibujar_hud_tactico(p, col, est, t, r_n)
        self._dibujar_cristal_fresnel(p, col, est, r_n)
        self._dibujar_plasma_aditivo(p, col, est, t, r_n)
        self._dibujar_especular(p, col, r_n)
        self._dibujar_ondas_reactivas(p, col, est, t, r_n)

        p.restore()

    def _dibujar_cristal_fresnel(self, p: QPainter, col: dict, est: str, r: float):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_ABISMO))
        p.drawEllipse(QPointF(0, 0), r, r)

        fresnel = QRadialGradient(QPointF(0, 0), r)
        fresnel.setColorAt(0.0, _alpha(col["borde"], 25))
        fresnel.setColorAt(0.65, _alpha(col["medio"], 60))
        fresnel.setColorAt(0.92, _alpha(col["centro"], 165))
        fresnel.setColorAt(1.0, _alpha(col["halo"], 230))
        p.setBrush(QBrush(fresnel))
        p.drawEllipse(QPointF(0, 0), r, r)

        p.setPen(QPen(_alpha(col["centro"], 180 if est != "silenciada" else 70), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), r, r)

    def _dibujar_plasma_aditivo(self, p: QPainter, col: dict, est: str, t: float, r: float):
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(0, 0), r - 1.0, r - 1.0)

        p.save()
        p.setClipPath(clip_path)
        p.setCompositionMode(QPainter.CompositionMode_Plus)

        puntos = 28
        step = math.tau / puntos
        v = self.rms_suave

        capas = [
            (col["plasma1"], 1.0, 2.2 + 3.0 * v, 3.0, 5.0, 80 + int(90 * v)),
            (col["plasma2"], -0.85, 2.8 + 3.5 * v, 4.0, 3.0, 75 + int(85 * v)),
            (col["plasma3"], 1.3, 3.4 + 4.0 * v, 2.0, 6.0, 70 + int(80 * v)),
        ]

        for color_capa, dir_rot, frec_t, f1, f2, alpha_capa in capas:
            if est == "silenciada": alpha_capa = 20
            path_capa = QPainterPath()
            amp = (3.5 + 8.5 * v) if est == "hablando" else (4.5 if est in ("experto", "pensando") else 2.8)
            r_capa = r * 0.72

            coords = []
            for i in range(puntos):
                ang = i * step
                onda = (math.sin(ang * f1 + t * frec_t * dir_rot) * 0.60
                        + math.cos(ang * f2 - t * (frec_t * 0.75)) * 0.40)
                rc = r_capa + amp * onda
                coords.append((rc * math.cos(ang), rc * math.sin(ang)))

            path_capa.moveTo(coords[0][0], coords[0][1])
            for x, y in coords[1:]: path_capa.lineTo(x, y)
            path_capa.closeSubpath()

            grad_plasma = QRadialGradient(QPointF(0, 0), r_capa * 1.1)
            grad_plasma.setColorAt(0.0, _alpha(color_capa, alpha_capa))
            grad_plasma.setColorAt(0.6, _alpha(color_capa, int(alpha_capa * 0.7)))
            grad_plasma.setColorAt(1.0, _alpha(color_capa, 0))

            p.setPen(QPen(_alpha(color_capa, int(alpha_capa * 0.9)), 1.2))
            p.setBrush(QBrush(grad_plasma))
            p.drawPath(path_capa)

        p.restore()

    def _dibujar_especular(self, p: QPainter, col: dict, r: float):
        p.setPen(Qt.NoPen)
        r_spec = r * 0.28
        spec_pos = QPointF(-r * 0.32, -r * 0.34)
        grad_spec = QRadialGradient(spec_pos, r_spec)
        grad_spec.setColorAt(0.0, _alpha(QColor(255, 255, 255), 185))
        grad_spec.setColorAt(0.5, _alpha(col["acento"], 90))
        grad_spec.setColorAt(1.0, _alpha(col["acento"], 0))
        p.setBrush(QBrush(grad_spec))
        p.drawEllipse(spec_pos, r_spec, r_spec * 0.70)

    def _dibujar_hud_tactico(self, p: QPainter, col: dict, est: str, t: float, r: float):
        r_in = r + 16.0
        r_out1 = r + 26.0
        r_out2 = r + 36.0

        p.setPen(QPen(_alpha(col["halo"], 65 if est != "experto" else 115), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(-r_in, -r_in, r_in * 2, r_in * 2))

        n_ticks = 16
        for k in range(n_ticks):
            ang = math.radians(k * (360.0 / n_ticks) + self.ang_ticks)
            c, s = math.cos(ang), math.sin(ang)
            len_tick = 3.5 if (k % 4 == 0) else 1.8
            p.drawLine(QPointF(r_in * c, r_in * s), QPointF((r_in + len_tick) * c, (r_in + len_tick) * s))

        ancho_cometa = 2.0 if est != "experto" else 2.6
        pluma_c1 = QPen(_alpha(col["acento"] if est == "experto" else col["halo"], 190), ancho_cometa)
        pluma_c1.setCapStyle(Qt.RoundCap)
        p.setPen(pluma_c1)
        rect_c1 = QRectF(-r_out1, -r_out1, r_out1 * 2, r_out1 * 2)
        largo1 = 115.0 if est != "experto" else 135.0
        p.drawArc(rect_c1, int(self.ang_halo_1 * 16), int(largo1 * 16))

        ang_punta1 = math.radians(self.ang_halo_1 + largo1)
        pt1 = QPointF(r_out1 * math.cos(ang_punta1), -r_out1 * math.sin(ang_punta1))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_alpha(col["acento"], 240)))
        p.drawEllipse(pt1, 2.2, 2.2)

        pluma_c2 = QPen(_alpha(col["acento"], 165), 1.4)
        pluma_c2.setCapStyle(Qt.RoundCap)
        p.setPen(pluma_c2)
        rect_c2 = QRectF(-r_out2, -r_out2, r_out2 * 2, r_out2 * 2)
        largo2 = 85.0 if est != "experto" else 105.0
        p.drawArc(rect_c2, int(self.ang_halo_2 * 16), int(largo2 * 16))

        ang_punta2 = math.radians(self.ang_halo_2 + largo2)
        pt2 = QPointF(r_out2 * math.cos(ang_punta2), -r_out2 * math.sin(ang_punta2))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_alpha(col["centro"], 230)))
        p.drawEllipse(pt2, 1.8, 1.8)

        if est != "silenciada":
            for i in range(10):
                vel_p = 0.28 + 0.04 * (i % 4)
                ang_p = t * vel_p + i * (math.tau / 10.0)
                r_p = r_in + 4.0 + (i % 5) * 4.2 + 2.0 * math.sin(t * 1.5 + i)
                alfa_p = 50 + int(90 * (0.5 + 0.5 * math.sin(t * 2.2 + i * 1.3)))
                p.setBrush(QBrush(_alpha(col["acento"], alfa_p)))
                p.drawEllipse(QPointF(r_p * math.cos(ang_p), r_p * math.sin(ang_p)), 1.2, 1.2)

    def _dibujar_ondas_reactivas(self, p: QPainter, col: dict, est: str, t: float, r: float):
        if est == "hablando" and self.rms_suave > 0.12:
            fase_onda = (t * 2.5) % 1.0
            r_onda = r + 4.0 + 38.0 * fase_onda
            alfa_o = int(170 * (1.0 - fase_onda) * min(1.0, self.rms_suave * 1.8))
            p.setPen(QPen(_alpha(col["acento"], alfa_o), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(-r_onda, -r_onda, r_onda * 2, r_onda * 2))

        elif est == "escuchando":
            ang_radar = math.radians((self.ang_halo_1 * 1.4) % 360.0)
            r_rad = r + 28.0
            p.setPen(QPen(_alpha(col["halo"], 140), 1.2))
            p.drawLine(QPointF(0, 0), QPointF(r_rad * math.cos(ang_radar), r_rad * math.sin(ang_radar)))


_ORBE_GLOBAL: Optional[GestorOrbeHibrido] = None


def obtener_orbe() -> GestorOrbeHibrido:
    global _ORBE_GLOBAL
    if _ORBE_GLOBAL is None:
        _ORBE_GLOBAL = GestorOrbeHibrido()
    return _ORBE_GLOBAL


def fijar_modo_experto(activo: bool, area: str = "general"):
    obtener_orbe().fijar_modo_experto(activo, area)


def dibujar_orbe_hibrido(p: QPainter, cara, t: float, tam: float):
    obtener_orbe().dibujar_orbe(p, cara, t, tam)
