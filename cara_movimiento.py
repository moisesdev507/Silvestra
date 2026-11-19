"""Lógica de desplazamiento, paseo autónomo, seguimiento de mouse y baile de la cara."""
import math
import random
import time

from PySide6.QtGui import QCursor

TAM = 250


class CaraMovimientoMixin:
    """Mixin que añade movimiento, paseo por la pantalla y baile a la Cara de Silvestra."""

    IDLE_PASEO = 6
    PRIMERA_PAUSA = (2, 5)
    PAUSA = (4, 12)
    PAUSA_ORDEN = (1, 3)

    def _tocar(self):
        """El usuario tomó el control: se cancelan las órdenes de movimiento."""
        self.ultima_interaccion = time.time()
        self.destino = None
        self.forzado_destino = False
        self.paseo_hasta = 0.0
        self.seguir_hasta = 0.0
        self.baile_hasta = 0.0

    def pasear_ahora(self, segundos=180):
        self._tocar()
        if hasattr(self, "accion_paseo"):
            self.accion_paseo.setChecked(True)
        self.paseo_hasta = time.time() + segundos
        self.pausa_hasta = 0.0
        self.sincronizar = True

    def quedarse_quieta(self):
        self._tocar()
        if hasattr(self, "accion_paseo"):
            self.accion_paseo.setChecked(False)

    def ir_a(self, lugar):
        self._tocar()
        ancho, alto = self._pantalla()
        puntos = {
            "derecha": (ancho - TAM - 40, alto - TAM - 100),
            "izquierda": (40, alto - TAM - 100),
            "centro": ((ancho - TAM) // 2, (alto - TAM) // 2),
        }
        self.destino = puntos.get(lugar, puntos["centro"])
        self.forzado_destino = True
        self.sincronizar = True

    def seguir_mouse(self, segundos=90):
        self._tocar()
        self.seguir_hasta = time.time() + segundos
        self.sincronizar = True

    def bailar(self, segundos=4):
        self._tocar()
        self.baile_hasta = time.time() + segundos
        self.sincronizar = True

    def _activo(self):
        ahora = time.time()
        return (
            (self.forzado_destino and self.destino is not None)
            or ahora < self.paseo_hasta
            or ahora < self.seguir_hasta
            or ahora < self.baile_hasta
        )

    def _puede_mover(self):
        if not (self.viva and self.ventana_entrada is None and self.isVisible()):
            return False
        if self._activo():
            return True
        return (
            hasattr(self, "accion_paseo")
            and self.accion_paseo.isChecked()
            and not self.hablando
            and not self.escuchando
            and self.burbuja is None
            and time.time() - self.ultima_interaccion > self.IDLE_PASEO
        )

    def _elegir_destino(self):
        ancho, alto = self._pantalla()
        for _ in range(6):
            x = random.randint(0, max(0, ancho - TAM))
            y = random.randint(int(alto * 0.25), max(int(alto * 0.25), alto - TAM - 70))
            if abs(x - self.fx) + abs(y - self.fy) > 200:
                break
        self.destino = (x, y)

    def _poner(self, x, y):
        self.move(int(x), int(y))

    def _mover(self):
        ahora = time.time()
        if ahora < self._libre_hasta:
            return
        if not self._puede_mover():
            self.destino = None
            self.sincronizar = True
            self.mx = 0
            self._libre_hasta = ahora + 0.3
            return
        if self.sincronizar:
            self.fx = float(self.x())
            self.fy = float(self.y())
            self.sincronizar = False
            if ahora < self.paseo_hasta:
                self.pausa_hasta = 0.0
            else:
                self.pausa_hasta = ahora + random.uniform(*self.PRIMERA_PAUSA)

        # Baile
        if ahora < self.baile_hasta:
            fase = math.sin(ahora * 9)
            self._poner(self.fx + 25 * fase, self.fy - 10 * abs(fase))
            return
        if self.baile_hasta:
            self.baile_hasta = 0.0
            self._poner(self.fx, self.fy)

        ancho, alto = self._pantalla()

        # Seguir al mouse
        if ahora < self.seguir_hasta:
            cur = QCursor.pos()
            tx = min(max(cur.x() + 40, 0), ancho - TAM)
            ty = min(max(cur.y() + 40, 0), alto - TAM - 70)
            dx, dy = tx - self.fx, ty - self.fy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 60:
                paso = max(3.0, dist * 0.08)
                self.fx += dx / dist * paso
                self.fy += dy / dist * paso
                self.mx = 5 if dx > 0 else -5
                self._poner(self.fx, self.fy)
            else:
                self.mx = 0
            return
        self.seguir_hasta = 0.0

        # Paseo o ida a un lugar
        if self.destino is None:
            if ahora < self.pausa_hasta:
                self._libre_hasta = ahora + 0.2
                return
            self._elegir_destino()
        dx = self.destino[0] - self.fx
        dy = self.destino[1] - self.fy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 2:
            self.destino = None
            self.forzado_destino = False
            self.mx = self.my = 0
            pausa = self.PAUSA_ORDEN if ahora < self.paseo_hasta else self.PAUSA
            self.pausa_hasta = ahora + random.uniform(*pausa)
            self._libre_hasta = ahora + 0.2
            return
        paso = min(dist, max(2.5, dist * 0.06))
        self.fx += dx / dist * paso
        self.fy += dy / dist * paso
        self.mx = 5 if dx > 0 else -5
        self._poner(self.fx, self.fy)
