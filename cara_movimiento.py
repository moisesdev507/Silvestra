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

    def bailar(self, estilo="aleatorio", segundos=15.0, con_musica=True, consulta_usuario=None, app=None):
        """Inicia una de las coreografías rítmicas con música opcional o detiene el baile."""
        import cara_baile
        self._tocar()
        gestor = getattr(self, "_gestor_baile", None)
        if gestor is None:
            gestor = cara_baile.obtener_gestor_baile()
            self._gestor_baile = gestor

        self.sincronizar = True
        self.fx = float(self.x())
        self.fy = float(self.y())

        app_ref = app or getattr(self, "silvestra_app", None) or getattr(self, "_ref_app", None)
        ok, msg = gestor.iniciar(
            estilo=estilo,
            segundos=segundos,
            app=app_ref,
            con_musica=con_musica,
            consulta_usuario=consulta_usuario,
        )
        if ok:
            self.baile_hasta = gestor.baile_hasta
        else:
            self.baile_hasta = 0.0
            self.baile_tilt = 0.0
        return ok, msg

    def parar_baile(self):
        """Detiene la coreografía actual y devuelve la cara a su posición base."""
        import cara_baile
        gestor = getattr(self, "_gestor_baile", None)
        if gestor:
            app_ref = getattr(self, "silvestra_app", None) or getattr(self, "_ref_app", None)
            gestor.detener(app=app_ref)
        self.baile_hasta = 0.0
        self.baile_tilt = 0.0
        self.baile_dx = 0.0
        self.baile_dy = 0.0
        self._actualizar_tilt(0.0)
        if hasattr(self, "fijar_emocion") and getattr(self, "emocion_objetivo", "neutral") != "neutral":
            self.fijar_emocion("neutral")

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

    def _actualizar_tilt(self, vx=0.0):
        tilt_target = max(-12.0, min(12.0, -vx * 1.6)) if abs(vx) > 0.05 else 0.0
        tilt_act = getattr(self, "tilt", 0.0)
        self.tilt = tilt_act + (tilt_target - tilt_act) * 0.22
        if abs(self.tilt) < 0.02:
            self.tilt = 0.0

    def _poner(self, x, y):
        vx = x - getattr(self, "_fx_prev", x)
        self._fx_prev = x
        self._actualizar_tilt(vx)
        self.move(int(x), int(y))

    def _mover(self):
        ahora = time.time()
        if ahora < self._libre_hasta:
            self._actualizar_tilt(0.0)
            return
        if not self._puede_mover():
            self.destino = None
            self.sincronizar = True
            self.mx = 0
            self._libre_hasta = ahora + 0.3
            self._actualizar_tilt(0.0)
            return
        if self.sincronizar:
            self.fx = float(self.x())
            self.fy = float(self.y())
            self._fx_prev = self.fx
            self.sincronizar = False
            if ahora < self.paseo_hasta:
                self.pausa_hasta = 0.0
            else:
                self.pausa_hasta = ahora + random.uniform(*self.PRIMERA_PAUSA)

        ancho, alto = self._pantalla()

        # Baile con gestor de coreografías
        if ahora < self.baile_hasta:
            import cara_baile
            gestor = getattr(self, "_gestor_baile", None)
            if gestor is None:
                gestor = cara_baile.obtener_gestor_baile()
                self._gestor_baile = gestor
            dx, dy, tilt, emo = gestor.actualizar_fisica(ahora, self.fx, self.fy, ancho, alto, TAM)
            self.baile_tilt = tilt
            self.baile_dx = dx
            self.baile_dy = dy
            if emo and hasattr(self, "emocion_objetivo") and self.emocion_objetivo != emo:
                self.fijar_emocion(emo)
            return

        if self.baile_hasta:
            self.parar_baile()
            self._poner(self.fx, self.fy)

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
                self._actualizar_tilt(0.0)
            return
        self.seguir_hasta = 0.0

        # Paseo o ida a un lugar
        if self.destino is None:
            if ahora < self.pausa_hasta:
                self._libre_hasta = ahora + 0.2
                self._actualizar_tilt(0.0)
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
            self._actualizar_tilt(0.0)
            return
        paso = min(dist, max(2.5, dist * 0.06))
        self.fx += dx / dist * paso
        self.fy += dy / dist * paso
        self.mx = 5 if dx > 0 else -5
        self._poner(self.fx, self.fy)
