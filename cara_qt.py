import math
import random
import time
import unicodedata

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

import acciones
import cara_nucleo
from burbuja import Burbuja, Entrada
from cara_dibujo import TAM, pintar
from cara_movimiento import CaraMovimientoMixin

AMABLES = ("gracias","linda","bonita","hermosa","preciosa","guapa","te quiero","te amo","genial","eres la mejor","tierna","bien hecho","felicidades","increible")


def _normal(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class _Raiz:
    def after(self, ms, fn):
        QTimer.singleShot(int(ms), fn)

    def destroy(self):
        QApplication.quit()


class Cara(CaraMovimientoMixin, QWidget):
    IDLE_PASEO = 6
    PRIMERA_PAUSA = (2, 5)
    PAUSA = (4, 12)
    PAUSA_ORDEN = (1, 3)

    def __init__(self, al_escribir, al_conversar, al_renacer, al_descansar):
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        super().__init__()
        self.app = app
        self.silvestra_app = None
        self._ref_app = None
        self.modo_activo = "normal"
        self.root = _Raiz()

        self.hablando = False
        self.burbuja = None
        self.ventana_entrada = None
        self.viva = False
        self.escuchando = False
        self.pensando = False
        self.pensando_hasta = 0.0
        self.feliz_hasta = 0.0
        self.emocion_actual = "neutral"
        self.emocion_objetivo = "neutral"
        self._ref_voz = None
        self._timer_retorno_neutral = None
        self._nivel_volumen_manual = 0.0
        self.mx = 0
        self.my = 0
        self.destino = None
        self.sincronizar = True
        self.ultima_interaccion = time.time()
        self.pausa_hasta = time.time() + 10
        self.fx = 0.0
        self.fy = 0.0
        self.paseo_hasta = 0.0
        self.forzado_destino = False
        self.seguir_hasta = 0.0
        self.baile_hasta = 0.0
        self.baile_tilt = 0.0
        self.baile_dx = 0.0
        self.baile_dy = 0.0
        self._libre_hasta = 0.0
        self.arrastre = None
        self.ojo_x = 0.0
        self.ojo_y = 0.0
        self.t0 = time.time()
        self.prox_parpadeo = time.time() + 2
        self.parpadeo_ini = None
        self._al_escribir = al_escribir
        self.asentir_hasta = 0.0
        self._ref_camara = None
        self._fps_cuadros = 0
        self._fps_t0 = time.time()
        self._tiempo_dibujo_acum = 0.0
        self._en_reposo = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Lyris")
        self.resize(TAM, TAM)
        ancho, alto = self._pantalla()
        self.move(ancho - TAM - 40, alto - TAM - 100)

        self.menu = QMenu()
        self.menu.addAction("Escribirle").triggered.connect(lambda *_: al_escribir())
        self.menu.addAction("Silenciar / reanudar voz").triggered.connect(
            lambda *_: al_conversar()
        )
        self.accion_paseo = QAction("Pasearse por la pantalla", self.menu)
        self.accion_paseo.setCheckable(True)
        self.accion_paseo.setChecked(True)
        self.accion_paseo.triggered.connect(lambda *_: self._tocar())
        self.menu.addAction(self.accion_paseo)
        import qt_estabilidad_ui
        self.accion_descansar = qt_estabilidad_ui.crear_accion_segura(
            self.menu,
            "Descansar (desaparece hasta que la llames)", "¿Confirmar descanso? (3s)", al_descansar
        )
        self.accion_renacer = qt_estabilidad_ui.crear_accion_segura(
            self.menu,
            "Renacer (borrar su memoria)",
            "¿Confirmar renacer? (3s)",
            al_renacer,
        )
        self.menu.addSeparator()
        self.menu.addAction("Salir").triggered.connect(lambda *_: QApplication.quit())

        self.reloj_dibujo = QTimer(self)
        self.reloj_dibujo.timeout.connect(self.update)
        self.reloj_dibujo.start(33)
        self.reloj_mover = QTimer(self)
        self.reloj_mover.timeout.connect(self._mover)
        self.reloj_mover.start(30)

        acciones.registrar("pasear", self.pasear_ahora, "se pasea por toda la pantalla un buen rato (úsala si te piden pasearte, moverte o caminar)")
        acciones.registrar("quedarse_quieta", self.quedarse_quieta, "se queda quieta en su lugar y deja de pasearse")
        acciones.registrar("ir_esquina_derecha", lambda: self.ir_a("derecha"), "va a la esquina inferior derecha")
        acciones.registrar("ir_esquina_izquierda", lambda: self.ir_a("izquierda"), "va a la esquina inferior izquierda")
        acciones.registrar("ir_centro", lambda: self.ir_a("centro"), "va al centro de la pantalla")
        acciones.registrar("seguir_mouse", self.seguir_mouse, "sigue el cursor del mouse un rato (úsala si te piden que te siga)")
        acciones.registrar(
            "bailar",
            self.ejecutar_baile,
            "baila coreografías (groove, salsa, fiesta o parar) con música opcional. Escribe: ACCION: bailar | estilo",
            con_texto=True,
        )

        self.show()

    def ejecutar_baile(self, arg=None):
        import cara_baile
        estilo, con_musica, cancion = cara_baile.parsear_comando_baile(arg)
        app_ref = getattr(self, "silvestra_app", None) or getattr(self, "_ref_app", None)
        return self.bailar(estilo=estilo, segundos=cara_baile.DURACION_BAILE_SEG, con_musica=con_musica, app=app_ref, consulta_usuario=cancion)

    # ---------- Utilidades ----------
    def _pantalla(self):
        g = QApplication.primaryScreen().geometry()
        return g.width(), g.height()

    def poner_viva(self, viva):
        self.viva = viva

    def poner_escuchando(self, escuchando):
        self.escuchando = bool(escuchando)
        self.update()

    def poner_hablando(self, hablando):
        self.hablando = bool(hablando)
        self.update()

    def color_estado(self):
        return cara_nucleo.color_estado(
            self.viva, self.escuchando, self.hablando,
            silenciada=cara_nucleo.esta_silenciada(self))

    def changeEvent(self, evento):
        if evento.type() in (QEvent.WindowStateChange, QEvent.ActivationChange):
            import qt_estabilidad_ui
            qt_estabilidad_ui.aplicar_estado_cara(
                self,
                minimizada=bool(self.isMinimized()),
                visible=bool(self.isVisible()),
            )
        super().changeEvent(evento)

    def hideEvent(self, evento):
        import qt_estabilidad_ui
        qt_estabilidad_ui.aplicar_estado_cara(
            self, minimizada=bool(self.isMinimized()), visible=False
        )
        super().hideEvent(evento)

    def showEvent(self, evento):
        import qt_estabilidad_ui
        qt_estabilidad_ui.aplicar_estado_cara(
            self,
            minimizada=bool(self.isMinimized()),
            visible=True,
        )
        super().showEvent(evento)

    @property
    def nivel_volumen(self):
        if self._ref_voz is not None:
            return getattr(self._ref_voz, "nivel_volumen", 0.0)
        return self._nivel_volumen_manual

    @nivel_volumen.setter
    def nivel_volumen(self, val):
        self._nivel_volumen_manual = float(val)

    def fijar_emocion(self, emocion):
        emo = str(emocion or "neutral").strip().lower().replace("á", "a")
        if emo not in ("neutral", "alegre", "animada", "calida", "seria", "preocupada"):
            emo = "neutral"
        self.emocion_objetivo = emo
        self.emocion_actual = emo

    def programar_retorno_neutral(self, delay_ms=3000):
        if self._timer_retorno_neutral is not None:
            self._timer_retorno_neutral.stop()
        self._timer_retorno_neutral = QTimer(self)
        self._timer_retorno_neutral.setSingleShot(True)
        self._timer_retorno_neutral.timeout.connect(
            lambda: self.fijar_emocion("neutral") if not self.hablando else None
        )
        self._timer_retorno_neutral.start(int(delay_ms))

    def asentir(self, duracion=0.6):
        self.asentir_hasta = time.time() + float(duracion)

    # ---------- Dibujo ----------
    def paintEvent(self, _):
        t0 = time.time()
        pintar(self)
        cara_nucleo.registrar_cuadro(self, time.time() - t0)
        ahora = time.time()

        # Reducción de tasa de refresco en reposo para mantener baja la CPU
        reposo_ahora = (
            not self.hablando
            and not self.escuchando
            and not self._activo()
            and self.burbuja is None
            and (ahora - self.ultima_interaccion > 8.0)
        )
        if reposo_ahora != self._en_reposo:
            self._en_reposo = reposo_ahora
            self.reloj_dibujo.setInterval(50 if self._en_reposo else 33)

    # ---------- Ratón ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.arrastre = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._tocar()

    def mouseMoveEvent(self, e):
        if self.arrastre is not None:
            self.move(e.globalPosition().toPoint() - self.arrastre)
            self.ultima_interaccion = time.time()

    def mouseReleaseEvent(self, e):
        self.arrastre = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._al_escribir()

    def contextMenuEvent(self, e):
        self._tocar()
        self.menu.exec(e.globalPos())

    def moveEvent(self, e):
        self._colocar_burbuja()
        super().moveEvent(e)

    # ---------- Burbuja ----------
    def _emocion(self, texto):
        ahora = time.time()
        if texto.startswith("«"):
            self.pensando = True
            self.pensando_hasta = ahora + 25
            n = _normal(texto)
            if any(w in n for w in AMABLES):
                self.feliz_hasta = ahora + 6
        else:
            self.pensando = False

    def decir(self, texto, ms=None, emocion=None):
        self.ultima_interaccion = time.time()
        try:
            import qt_estabilidad_ui
            ui_activa = qt_estabilidad_ui.puede_actualizar_ui()
        except Exception:
            ui_activa = True
        if emocion:
            self.fijar_emocion(emocion)
        if ms is None:
            ms = max(3000, len(texto) * 80)
        self._emocion(texto)
        if not ui_activa:
            self.hablando = True
            return
        if getattr(self, "silenciar_burbuja", False):
            # En modo escenario los subtítulos se muestran abajo, sin burbuja flotante
            if self.burbuja is not None:
                self.burbuja.close()
                self.burbuja.deleteLater()
                self.burbuja = None
            self.hablando = True
            def _terminar_silencio():
                self.hablando = False
                self.programar_retorno_neutral(2500)
            QTimer.singleShot(int(ms), _terminar_silencio)
            return
        if self.burbuja is not None:
            self.burbuja.close()
            self.burbuja.deleteLater()
        b = Burbuja(texto)
        self.burbuja = b
        self.hablando = True
        self._colocar_burbuja()
        b.show()
        b.raise_()
        self._colocar_burbuja()
        QTimer.singleShot(int(ms), lambda: self._cerrar_burbuja(b))

    def _colocar_burbuja(self):
        b = self.burbuja
        if b is None:
            return
        try:
            import qt_estabilidad_ui
            if not qt_estabilidad_ui.puede_actualizar_ui():
                return
        except Exception:
            pass
        b.adjustSize()
        x = max(10, self.x() - b.width() + 40)
        y = self.y() - b.height() + 60
        if y < 10:
            y = self.y() + self.height() - 30  # no cabe arriba: va debajo
        b.move(x, y)

    def _cerrar_burbuja(self, b):
        if self.burbuja is b:
            b.close()
            b.deleteLater()
            self.burbuja = None
            self.hablando = False
            self.programar_retorno_neutral(2500)

    # ---------- Diálogos ----------
    def preguntar(self, titulo, texto):
        d = QInputDialog()
        d.setWindowTitle(titulo)
        d.setLabelText(texto)
        d.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        return d.textValue() if d.exec() else None

    def confirmar(self, titulo, texto):
        m = QMessageBox()
        m.setWindowTitle(titulo)
        m.setText(texto)
        m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        m.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        return m.exec() == QMessageBox.Yes

    def abrir_entrada(self, titulo, al_enviar):
        try:
            import qt_estabilidad_ui
            if not qt_estabilidad_ui.puede_actualizar_ui():
                return
        except Exception:
            pass
        self._tocar()
        if self.ventana_entrada is not None:
            self.ventana_entrada.activateWindow()
            return

        def al_cerrar(v):
            if self.ventana_entrada is v:
                self.ventana_entrada = None

        v = Entrada(titulo, al_cerrar)

        def enviar():
            texto = v.campo.text().strip()
            v.close()
            if texto:
                al_enviar(texto)

        v.campo.returnPressed.connect(enviar)
        self.ventana_entrada = v
        v.show()
        v.raise_()
        v.activateWindow()
        v.campo.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            try:
                import voz_dueno_registro
                voz_dueno_registro.cancelar()
            except Exception:
                pass
        super().keyPressEvent(e)

    def ocultar(self):
        if self.burbuja is not None:
            self.burbuja.close()
            self.burbuja.deleteLater()
            self.burbuja = None
        self.hablando = False
        self.hide()

    def mostrar(self):
        try:
            import qt_estabilidad_ui
            if not qt_estabilidad_ui.puede_actualizar_ui():
                return
        except Exception:
            pass
        self.show()
        self.raise_()

    def iniciar(self):
        self.app.exec()