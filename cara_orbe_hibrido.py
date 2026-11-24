"""Renderizador Híbrido: Núcleo Vivo + Halo Técnico para la esfera de Lyris.

Vectorial ligero con QPainter, QPainterPath y QRadialGradient (sin QGraphicsBlurEffect).
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
        "acento": QColor(186, 230, 253),
    },
    "escuchando": {
        "centro": QColor(254, 243, 199), "medio": QColor(45, 212, 191),
        "borde": QColor(13, 148, 136), "halo": QColor(52, 211, 153),
        "acento": QColor(251, 191, 36),
    },
    "pensando": {
        "centro": QColor(224, 242, 254), "medio": QColor(14, 165, 233),
        "borde": QColor(3, 105, 161), "halo": QColor(56, 189, 248),
        "acento": QColor(255, 255, 255),
    },
    "experto": {
        "centro": QColor(253, 230, 138), "medio": QColor(168, 85, 247),
        "borde": QColor(107, 33, 168), "halo": QColor(217, 70, 239),
        "acento": QColor(245, 158, 11),
    },
    "hablando": {
        "centro": QColor(255, 251, 235), "medio": QColor(245, 158, 11),
        "borde": QColor(180, 83, 9), "halo": QColor(251, 191, 36),
        "acento": QColor(254, 240, 138),
    },
    "bailando": {
        "centro": QColor(255, 240, 245), "medio": QColor(244, 63, 94),
        "borde": QColor(168, 85, 247), "halo": QColor(6, 182, 212),
        "acento": QColor(250, 204, 21),
    },
    "silenciada": {
        "centro": QColor(148, 163, 184), "medio": QColor(100, 116, 139),
        "borde": QColor(51, 65, 85), "halo": QColor(71, 85, 105),
        "acento": QColor(148, 163, 184),
    },
}


def _interp_col(c1: QColor, c2: QColor, f: float) -> QColor:
    f = max(0.0, min(1.0, f))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * f),
        int(c1.green() + (c2.green() - c1.green()) * f),
        int(c1.blue() + (c2.blue() - c1.blue()) * f),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * f),
    )


def _alpha(color: QColor, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


class GestorOrbeHibrido:
    def __init__(self):
        self.estado_actual = "reposo"
        self.modo_experto_activo = False
        self.area_experto = "general"
        self.rms_suave = 0.0
        self.radio_suave = 52.0
        self.ang_halo_1 = 0.0
        self.ang_halo_2 = 180.0
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

        if est == "silenciada": vel_1, vel_2 = 0.0, 0.0
        elif est == "reposo": vel_1, vel_2 = 18.0, -14.0
        elif est == "escuchando": vel_1, vel_2 = 45.0, -38.0
        elif est in ("pensando", "experto"): vel_1, vel_2 = 85.0, -70.0
        elif est == "hablando": vel_1, vel_2 = 35.0 + 90.0 * self.rms_suave, -(30.0 + 80.0 * self.rms_suave)
        else: vel_1, vel_2 = 120.0, -110.0

        self.ang_halo_1 = (self.ang_halo_1 + vel_1 * dt) % 360.0
        self.ang_halo_2 = (self.ang_halo_2 + vel_2 * dt) % 360.0
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
        r_base = 50.0 + (3.0 * resp if est == "reposo" else 0.0)
        if est == "hablando": r_base += 12.0 * self.rms_suave
        elif est == "experto": r_base += 4.0 + 2.0 * math.sin(t * 3.0)

        self.radio_suave += (r_base - self.radio_suave) * 0.15
        r_nucleo = self.radio_suave

        # Halo Técnico y Núcleo Vivo
        self._dibujar_halo(p, col, est, r_nucleo)
        self._dibujar_nucleo(p, col, est, t, r_nucleo)

        if est == "hablando" and self.rms_suave > 0.15:
            r_pulso = r_nucleo + 8.0 + 35.0 * self.rms_suave
            alfa = int(140 * (1.0 - min(1.0, self.rms_suave * 0.8)))
            p.setPen(QPen(_alpha(col["acento"], alfa), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(-r_pulso, -r_pulso, r_pulso * 2, r_pulso * 2))

        p.restore()

    def _dibujar_halo(self, p: QPainter, col: dict, est: str, r_nucleo: float):
        r_h1 = r_nucleo + 22.0
        r_h2 = r_nucleo + 32.0
        opac = 60 if est == "reposo" else (220 if est in ("experto", "pensando") else 140)
        ancho = 1.6 if est != "experto" else 2.2

        pluma1 = QPen(_alpha(col["halo"], opac), ancho)
        pluma1.setCapStyle(Qt.RoundCap)
        p.setPen(pluma1)
        p.setBrush(Qt.NoBrush)
        rect1 = QRectF(-r_h1, -r_h1, r_h1 * 2, r_h1 * 2)
        largo1 = 110.0 if est != "experto" else 135.0
        p.drawArc(rect1, int(self.ang_halo_1 * 16), int(largo1 * 16))
        p.drawArc(rect1, int((self.ang_halo_1 + 180) * 16), int(largo1 * 16))

        pluma2 = QPen(_alpha(col["acento"], int(opac * 0.85)), 1.2)
        pluma2.setCapStyle(Qt.RoundCap)
        p.setPen(pluma2)
        rect2 = QRectF(-r_h2, -r_h2, r_h2 * 2, r_h2 * 2)
        largo2 = 70.0 if est != "experto" else 95.0
        p.drawArc(rect2, int(self.ang_halo_2 * 16), int(largo2 * 16))
        p.drawArc(rect2, int((self.ang_halo_2 + 180) * 16), int(largo2 * 16))

        if est in ("experto", "pensando", "escuchando"):
            p.setPen(QPen(_alpha(col["acento"], 90), 1.0))
            for k in range(8):
                ang = math.radians(k * 45 + self.ang_halo_1 * 0.5)
                c, s = math.cos(ang), math.sin(ang)
                p.drawLine(QPointF(r_h1 * c, r_h1 * s), QPointF((r_h1 + 4.0) * c, (r_h1 + 4.0) * s))

    def _dibujar_nucleo(self, p: QPainter, col: dict, est: str, t: float, r_base: float):
        puntos = 32
        step = math.tau / puntos
        path = QPainterPath()
        amp = 2.0 if est == "reposo" else (4.0 + 8.0 * self.rms_suave if est == "hablando" else 3.5)
        frec = 1.8 if est == "reposo" else (4.5 if est == "hablando" else 2.6)

        coords = []
        for i in range(puntos):
            ang = i * step
            onda = (math.sin(ang * 3.0 + t * frec) * 0.65 + math.cos(ang * 5.0 - t * (frec * 0.8)) * 0.35)
            r = r_base + amp * onda
            coords.append((r * math.cos(ang), r * math.sin(ang)))

        path.moveTo(coords[0][0], coords[0][1])
        for x, y in coords[1:]: path.lineTo(x, y)
        path.closeSubpath()

        grad = QRadialGradient(QPointF(-r_base * 0.2, -r_base * 0.25), r_base * 1.15)
        grad.setColorAt(0.0, _alpha(col["centro"], 255))
        grad.setColorAt(0.40, _alpha(col["medio"], 230))
        grad.setColorAt(0.85, _alpha(col["borde"], 180))
        grad.setColorAt(1.0, _alpha(col["borde"], 30))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_alpha(col["halo"], 45 if est != "experto" else 75)))
        p.drawEllipse(QRectF(-r_base * 1.22, -r_base * 1.22, r_base * 2.44, r_base * 2.44))

        p.setBrush(QBrush(grad))
        p.setPen(QPen(_alpha(col["centro"], 160), 1.5))
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        r_spec = r_base * 0.22
        p.setBrush(QBrush(_alpha(QColor(255, 255, 255), 180)))
        p.drawEllipse(QPointF(-r_base * 0.18, -r_base * 0.22), r_spec, r_spec * 0.75)


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
