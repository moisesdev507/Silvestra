"""Holograma Giroscópico 3D: Cristal Obsidiana + Red Neuronal + Anillos 3D + Ecualizador.

Renderizado multicapa en orden Z real con QPainter ligero en CPU (sin QGraphicsBlurEffect).
Centro oscuro no saturado, profundidad 3D mediante giroscopios divididos y seguimiento del cursor.
"""
import math
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

import cara_holo_3d as h3d

PALETAS = {
    "reposo": {
        "centro": QColor(191, 219, 254), "medio": QColor(29, 78, 216),
        "borde": QColor(30, 64, 175), "halo": QColor(56, 189, 248),
        "acento": QColor(147, 197, 253), "plasma1": QColor(37, 99, 235),
        "plasma2": QColor(59, 130, 246), "plasma3": QColor(139, 92, 246),
    },
    "escuchando": {
        "centro": QColor(254, 243, 199), "medio": QColor(245, 158, 11),
        "borde": QColor(180, 83, 9), "halo": QColor(251, 191, 36),
        "acento": QColor(253, 224, 71), "plasma1": QColor(217, 119, 6),
        "plasma2": QColor(245, 158, 11), "plasma3": QColor(139, 92, 246),
    },
    "pensando": {
        "centro": QColor(237, 233, 254), "medio": QColor(139, 92, 246),
        "borde": QColor(109, 40, 217), "halo": QColor(167, 139, 250),
        "acento": QColor(196, 181, 253), "plasma1": QColor(124, 58, 237),
        "plasma2": QColor(139, 92, 246), "plasma3": QColor(56, 189, 248),
    },
    "experto": {
        "centro": QColor(243, 232, 255), "medio": QColor(139, 92, 246),
        "borde": QColor(91, 33, 182), "halo": QColor(192, 132, 252),
        "acento": QColor(250, 204, 21), "plasma1": QColor(168, 85, 247),
        "plasma2": QColor(124, 58, 237), "plasma3": QColor(245, 158, 11),
    },
    "hablando": {
        "centro": QColor(207, 250, 254), "medio": QColor(6, 182, 212),
        "borde": QColor(8, 145, 178), "halo": QColor(56, 189, 248),
        "acento": QColor(224, 242, 254), "plasma1": QColor(6, 182, 212),
        "plasma2": QColor(34, 211, 238), "plasma3": QColor(56, 189, 248),
    },
    "hablando_calido": {
        "centro": QColor(254, 243, 199), "medio": QColor(245, 158, 11),
        "borde": QColor(180, 83, 9), "halo": QColor(251, 191, 36),
        "acento": QColor(255, 110, 150), "plasma1": QColor(251, 146, 60),
        "plasma2": QColor(244, 63, 94), "plasma3": QColor(253, 224, 71),
    },
    "bailando": {
        "centro": QColor(255, 240, 245), "medio": QColor(244, 63, 94),
        "borde": QColor(139, 92, 246), "halo": QColor(6, 182, 212),
        "acento": QColor(250, 204, 21), "plasma1": QColor(244, 63, 94),
        "plasma2": QColor(139, 92, 246), "plasma3": QColor(6, 182, 212),
    },
    "silenciada": {
        "centro": QColor(148, 163, 184), "medio": QColor(100, 116, 139),
        "borde": QColor(51, 65, 85), "halo": QColor(71, 85, 105),
        "acento": QColor(148, 163, 184), "plasma1": QColor(71, 85, 105),
        "plasma2": QColor(100, 116, 139), "plasma3": QColor(148, 163, 184),
    },
}

_OBSIDIANA = QColor(7, 11, 20, 235)  # #070B14: núcleo abisal sin transparencias sucias


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
        self.radio_suave = 45.0
        self.ang_halo_1 = 0.0
        self.ang_halo_2 = 180.0
        self.t_anterior = 0.0
        self.pitch_suave = 0.0
        self.yaw_suave = 0.0
        self.factor_exp_suave = 1.0
        self.fase_giro = 0.0
        self.flotacion_y = 0.0
        self.ripples: list[float] = []
        self._pico_rms = 0.0
        self._colores_suaves = dict(PALETAS["reposo"])

    def fijar_modo_experto(self, activo: bool, area: str = "general"):
        self.modo_experto_activo = bool(activo)
        self.area_experto = str(area or "general")

    def _vivo(self, est: str) -> bool:
        """Deformación activa al hablar o con energía de voz perceptible."""
        return est != "silenciada" and ("hablando" in est or self.rms_suave > 0.02)

    def deducir_estado(self, cara) -> str:
        if getattr(cara, "voz_silenciada", False): return "silenciada"
        ahora = time.time()
        if ahora < getattr(cara, "baile_hasta", 0.0): return "bailando"
        if getattr(cara, "hablando", False):
            emo = str(getattr(cara, "emocion_objetivo", "") or "").lower()
            if emo in ("alegre", "feliz", "calida", "amorosa", "entusiasta"):
                return "hablando_calido"
            return "hablando"
        if getattr(cara, "escuchando", False): return "escuchando"
        if self.modo_experto_activo or getattr(cara, "modo_experto", False): return "experto"
        if getattr(cara, "pensando", False) or ahora < getattr(cara, "pensando_hasta", 0.0): return "pensando"
        return "reposo"

    def actualizar(self, cara, t: float, nivel_rms: float, p: Optional[QPainter] = None) -> str:
        dt = 0.016 if not self.t_anterior else max(0.001, min(0.1, t - self.t_anterior))
        self.t_anterior = t
        est = self.deducir_estado(cara)
        self.estado_actual = est

        factor_rms = 0.35 if nivel_rms > self.rms_suave else 0.15
        self.rms_suave += (max(0.0, min(1.0, nivel_rms)) - self.rms_suave) * factor_rms

        v = self.rms_suave
        if v > 0.10 and v >= self._pico_rms + 0.05:
            self.ripples.append(0.0)
            self._pico_rms = v
        elif v < self._pico_rms - 0.03:
            self._pico_rms = v
        self.ripples = [f + dt / 0.9 for f in self.ripples if f + dt / 0.9 < 1.0][-4:]

        # Seguimiento del cursor si hay QPainter disponible
        if p is not None:
            p_cur, y_cur = h3d.obtener_inclinacion_cursor(p)
            self.pitch_suave += (p_cur - self.pitch_suave) * 0.12
            self.yaw_suave += (y_cur - self.yaw_suave) * 0.12

        target_exp = 1.25 if est == "experto" else 1.0
        self.factor_exp_suave += (target_exp - self.factor_exp_suave) * 0.10

        pal_dest = PALETAS.get(est, PALETAS["reposo"])
        for k in self._colores_suaves:
            self._colores_suaves[k] = _interp_col(self._colores_suaves[k], pal_dest[k], 0.12)

        if est == "silenciada": vel_1, vel_2 = 0.0, 0.0
        elif est == "reposo": vel_1, vel_2 = 18.0, -14.0
        elif est == "escuchando": vel_1, vel_2 = 45.0, -38.0
        elif est in ("pensando", "experto"): vel_1, vel_2 = 92.0, -80.0
        elif est == "hablando":
            v = self.rms_suave
            vel_1, vel_2 = 35.0 + 90.0 * v, -(30.0 + 80.0 * v)
        else: vel_1, vel_2 = 130.0, -115.0

        self.ang_halo_1 = (self.ang_halo_1 + vel_1 * dt) % 360.0
        self.ang_halo_2 = (self.ang_halo_2 + vel_2 * dt) % 360.0

        if est == "silenciada": vel_giro = 0.0
        elif "hablando" in est: vel_giro = 2.2 + 3.0 * v
        elif est in ("pensando", "experto"): vel_giro = 1.9
        elif est == "bailando": vel_giro = 2.6
        else: vel_giro = 0.8
        self.fase_giro += dt * vel_giro
        return est

    def dibujar_orbe(self, p: QPainter, cara, t: float, tam: float):
        nivel_raw = float(getattr(cara, "nivel_volumen", 0.0) or 0.0)
        if getattr(cara, "voz_silenciada", False): nivel_raw = 0.0
        est = self.actualizar(cara, t, nivel_raw, p=p)

        esc = tam / 280.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(tam / 2.0, tam / 2.0)
        self.flotacion_y = 2.6 * math.sin(t * (math.tau / 4.8))
        if est == "silenciada": self.flotacion_y *= 0.4
        p.translate(0.0, self.flotacion_y)
        p.scale(esc, esc)

        col = self._colores_suaves
        resp = 0.5 + 0.5 * math.sin(t * (math.tau / 3.5))
        # Núcleo proporcionado (~66% del radio útil) para dar amplio aire a los anillos y ecualizador
        r_base = 45.0 + (2.0 * resp if est == "reposo" else 0.0)
        if "hablando" in est: r_base += 7.5 * self.rms_suave
        elif est == "experto": r_base += 3.5 + 1.8 * math.sin(t * 3.2)

        self.radio_suave += (r_base - self.radio_suave) * 0.15
        r_n = self.radio_suave

        # CAPA 1: Giroscopios 3D traseros (detrás de la esfera)
        h3d.dibujar_giroscopios_traseros(p, col, est, t, r_n, self.pitch_suave, self.yaw_suave, self.factor_exp_suave, self.fase_giro)

        # CAPA 2: Base cristal obsidiana + Red neuronal 3D interna + filamentos
        self._dibujar_cristal_obsidiana(p, col, est, t, r_n)
        h3d.dibujar_red_neuronal_3d(p, col, est, t, r_n, self.pitch_suave, self.yaw_suave, self.rms_suave, self.fase_giro)
        self._dibujar_filamentos_suaves(p, col, est, t, r_n)
        self._dibujar_especular(p, col, r_n)

        # CAPA 3: Borde Fresnel + Ecualizador radial reactivo + ondas
        self._dibujar_borde_fresnel(p, col, est, t, r_n)
        h3d.dibujar_ecualizador_radial(p, col, est, t, r_n, self.rms_suave)
        self._dibujar_ondas_reactivas(p, col, est, t, r_n)

        # CAPA 4: Giroscopios 3D delanteros + partículas orbitales
        h3d.dibujar_giroscopios_delanteros(p, col, est, t, r_n, self.pitch_suave, self.yaw_suave, self.factor_exp_suave, self.fase_giro)
        h3d.dibujar_particulas_3d(p, col, est, t, r_n, self.pitch_suave, self.yaw_suave)

        p.restore()

    def _dibujar_cristal_obsidiana(self, p: QPainter, col: dict, est: str, t: float, r: float):
        """Base #070B14 con grad radial profundo: el fondo nunca se transparenta."""
        p.setPen(Qt.NoPen)
        base = QRadialGradient(QPointF(0, 0), r)
        base.setColorAt(0.0, QColor(7, 11, 20, 255))
        base.setColorAt(0.72, QColor(7, 11, 20, 250))
        base.setColorAt(1.0, QColor(7, 11, 20, 235))
        p.setBrush(QBrush(base))
        p.drawPath(h3d.path_organico(r, t, self.rms_suave, self._vivo(est)))

        fresnel = QRadialGradient(QPointF(0, 0), r)
        fresnel.setColorAt(0.0, _alpha(col["borde"], 25))
        fresnel.setColorAt(0.65, _alpha(col["medio"], 60))
        fresnel.setColorAt(0.92, _alpha(col["centro"], 135))
        fresnel.setColorAt(1.0, _alpha(col["halo"], 190))
        p.setBrush(QBrush(fresnel))
        p.drawPath(h3d.path_organico(r, t, self.rms_suave, self._vivo(est)))

    def _dibujar_borde_fresnel(self, p: QPainter, col: dict, est: str, t: float, r: float):
        """Aro perimetral orgánico con doble halo que vibra con la voz."""
        vivo = self._vivo(est)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_alpha(col["halo"], 45 if est != "silenciada" else 20), 2.2))
        p.drawPath(h3d.path_organico(r + 0.8, t, self.rms_suave, vivo))
        p.setPen(QPen(_alpha(col["centro"], 150 if est != "silenciada" else 55), 1.2))
        p.drawPath(h3d.path_organico(r, t, self.rms_suave, vivo))

    def _dibujar_filamentos_suaves(self, p: QPainter, col: dict, est: str, t: float, r: float):
        """2 filamentos orgánicos a baja opacidad para complementar la red 3D sin saturar."""
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(0, 0), r - 1.5, r - 1.5)
        p.save()
        p.setClipPath(clip_path)
        p.setCompositionMode(QPainter.CompositionMode_Plus)

        v = self.rms_suave
        capas = [
            (col["plasma1"], 1.0, 2.0, 3.0, 4.0, 45 + int(35 * v)),
            (col["plasma2"], -0.9, 2.6, 4.0, 3.0, 40 + int(30 * v)),
        ]
        puntos = 24
        step = math.tau / puntos
        for color_capa, dir_rot, frec, f1, f2, alfa in capas:
            if est == "silenciada": alfa = 15
            path = QPainterPath()
            amp = (2.2 + 8.5 * v) if self._vivo(est) else 2.5
            r_c = r * 0.70
            coords = []
            for i in range(puntos):
                ang = i * step
                onda = (0.5 * math.sin(ang * f1 + t * frec * dir_rot)
                        + 0.3 * math.cos(ang * f2 - t * frec)
                        + 0.2 * math.sin(ang * 7.0 + t * 13.0))
                rc = r_c + amp * onda
                coords.append((rc * math.cos(ang), rc * math.sin(ang)))
            path.moveTo(coords[0][0], coords[0][1])
            for x, y in coords[1:]: path.lineTo(x, y)
            path.closeSubpath()

            grad = QRadialGradient(QPointF(0, 0), r_c * 1.05)
            grad.setColorAt(0.0, _alpha(color_capa, alfa))
            grad.setColorAt(1.0, _alpha(color_capa, 0))
            p.setPen(QPen(_alpha(color_capa, int(alfa * 0.8)), 1.0))
            p.setBrush(QBrush(grad))
            p.drawPath(path)
        p.restore()

    def _dibujar_especular(self, p: QPainter, col: dict, r: float):
        """Reflejo curvo superior izquierdo sutil para volumen esférico 3D."""
        p.setPen(Qt.NoPen)
        r_spec = r * 0.28
        spec_pos = QPointF(-r * 0.32, -r * 0.34)
        grad_spec = QRadialGradient(spec_pos, r_spec)
        grad_spec.setColorAt(0.0, _alpha(QColor(255, 255, 255), 95))
        grad_spec.setColorAt(0.55, _alpha(col["acento"], 60))
        grad_spec.setColorAt(1.0, _alpha(col["acento"], 0))
        p.setBrush(QBrush(grad_spec))
        p.drawEllipse(spec_pos, r_spec, r_spec * 0.70)

    def _dibujar_ondas_reactivas(self, p: QPainter, col: dict, est: str, t: float, r: float):
        c_onda = col["acento"] if "hablando" in est else col["halo"]
        for fase in self.ripples:
            r_o = r + 3.0 + 46.0 * fase
            alfa = int(155 * (1.0 - fase) * min(1.0, 0.4 + self.rms_suave))
            p.setPen(QPen(_alpha(c_onda, alfa), 1.3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(-r_o, -r_o, r_o * 2, r_o * 2))
        if est == "escuchando":
            ang_rad = math.radians((self.ang_halo_1 * 1.4) % 360.0)
            r_rad = r + 26.0
            p.setPen(QPen(_alpha(col["halo"], 135), 1.2))
            p.drawLine(QPointF(0, 0), QPointF(r_rad * math.cos(ang_rad), r_rad * math.sin(ang_rad)))


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
