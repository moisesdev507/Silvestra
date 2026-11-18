"""Cara de Silvestra con PySide6: suave, con anillos de luz, lacito y emociones.

Tiene la misma interfaz que cara.py, así que main.py la usa sin más cambios.
"""
import math
import random
import time
import unicodedata

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

import acciones
from cara_dibujo import TAM, pintar

# Palabras amables: si se las dices, se pone contenta.
AMABLES = ["gracias", "linda", "bonita", "hermosa", "preciosa", "guapa", "te quiero",
           "te amo", "genial", "eres la mejor", "tierna", "bien hecho", "felicidades", "increible"]


def _normal(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class _Raiz:
    """Imita lo poquito que main.py y presentacion.py usan de Tk (after, destroy)."""

    def after(self, ms, fn):
        QTimer.singleShot(int(ms), fn)

    def destroy(self):
        QApplication.quit()


class Burbuja(QWidget):
    def __init__(self, texto):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(texto)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(320)
        self.label.setStyleSheet(
            "background-color:#1b2333;color:white;border:2px solid #4fd1c5;"
            "border-radius:14px;padding:10px 14px;font-size:14px;font-family:'Segoe UI';"
        )
        lay.addWidget(self.label)
        self.adjustSize()


class Entrada(QWidget):
    def __init__(self, titulo, al_cerrar):
        super().__init__()
        self.al_cerrar = al_cerrar
        self.setWindowTitle(titulo)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        lay = QVBoxLayout(self)
        self.campo = QLineEdit()
        self.campo.setMinimumWidth(480)
        self.campo.setStyleSheet("font-size:16px;padding:6px;")
        lay.addWidget(self.campo)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.al_cerrar(self)
        super().closeEvent(e)


class Cara(QWidget):
    """El rostro flotante: dibujo, parpadeo, boca, burbuja de texto y menú."""

    IDLE_PASEO = 6
    PRIMERA_PAUSA = (2, 5)
    PAUSA = (4, 12)
    PAUSA_ORDEN = (1, 3)

    def __init__(self, al_escribir, al_conversar, al_renacer, al_descansar):
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        super().__init__()
        self.app = app
        self.root = _Raiz()

        self.hablando = False
        self.burbuja = None
        self.ventana_entrada = None
        self.viva = False
        self.escuchando = False
        self.pensando = False
        self.pensando_hasta = 0.0
        self.feliz_hasta = 0.0
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
        self._libre_hasta = 0.0
        self.arrastre = None
        self.ojo_x = 0.0
        self.ojo_y = 0.0
        self.t0 = time.time()
        self.prox_parpadeo = time.time() + 2
        self.parpadeo_ini = None
        self._al_escribir = al_escribir

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(TAM, TAM)
        ancho, alto = self._pantalla()
        self.move(ancho - TAM - 40, alto - TAM - 100)

        # Menú (clic derecho)
        self.menu = QMenu()
        self.menu.addAction("Escribirle").triggered.connect(lambda *_: al_escribir())
        self.menu.addAction("Conversar con voz (activar/desactivar)").triggered.connect(
            lambda *_: al_conversar()
        )
        self.accion_paseo = QAction("Pasearse por la pantalla", self.menu)
        self.accion_paseo.setCheckable(True)
        self.accion_paseo.setChecked(True)
        self.accion_paseo.triggered.connect(lambda *_: self._tocar())
        self.menu.addAction(self.accion_paseo)
        self.menu.addAction("Descansar (desaparece hasta que la llames)").triggered.connect(
            lambda *_: al_descansar()
        )
        self.menu.addAction("Renacer (borrar su memoria)").triggered.connect(lambda *_: al_renacer())
        self.menu.addSeparator()
        self.menu.addAction("Salir").triggered.connect(lambda *_: QApplication.quit())

        # Relojes: dibujo (~40 cuadros/s) y movimiento
        self.reloj_dibujo = QTimer(self)
        self.reloj_dibujo.timeout.connect(self.update)
        self.reloj_dibujo.start(25)
        self.reloj_mover = QTimer(self)
        self.reloj_mover.timeout.connect(self._mover)
        self.reloj_mover.start(30)

        # Cosas que se le pueden pedir por voz
        acciones.registrar("pasear", self.pasear_ahora, "se pasea por toda la pantalla un buen rato (úsala si te piden pasearte, moverte o caminar)")
        acciones.registrar("quedarse_quieta", self.quedarse_quieta, "se queda quieta en su lugar y deja de pasearse")
        acciones.registrar("ir_esquina_derecha", lambda: self.ir_a("derecha"), "va a la esquina inferior derecha")
        acciones.registrar("ir_esquina_izquierda", lambda: self.ir_a("izquierda"), "va a la esquina inferior izquierda")
        acciones.registrar("ir_centro", lambda: self.ir_a("centro"), "va al centro de la pantalla")
        acciones.registrar("seguir_mouse", self.seguir_mouse, "sigue el cursor del mouse un rato (úsala si te piden que te siga)")
        acciones.registrar("bailar", self.bailar, "baila unos segundos")

        self.show()

    # ---------- Utilidades ----------
    def _pantalla(self):
        g = QApplication.primaryScreen().geometry()
        return g.width(), g.height()

    def poner_viva(self, viva):
        self.viva = viva

    def poner_escuchando(self, escuchando):
        self.escuchando = escuchando

    # ---------- Dibujo ----------
    def paintEvent(self, _):
        pintar(self)

    # ---------- Paseo ----------
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
        self.accion_paseo.setChecked(True)
        self.paseo_hasta = time.time() + segundos
        self.pausa_hasta = 0.0
        self.sincronizar = True

    def quedarse_quieta(self):
        self._tocar()
        self.accion_paseo.setChecked(False)

    def ir_a(self, lugar):
        self._tocar()
        ancho, alto = self._pantalla()
        puntos = {
            "derecha": (ancho - TAM - 40, alto - TAM - 100),
            "izquierda": (40, alto - TAM - 100),
            "centro": ((ancho - TAM) // 2, (alto - TAM) // 2),
        }
        self.destino = puntos[lugar]
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
            self.accion_paseo.isChecked()
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

    def decir(self, texto, ms=None):
        self.ultima_interaccion = time.time()
        if ms is None:
            ms = max(3000, len(texto) * 80)
        self._emocion(texto)
        if getattr(self, "silenciar_burbuja", False):
            # En modo escenario los subtítulos se muestran abajo, sin burbuja flotante
            if self.burbuja is not None:
                self.burbuja.close()
                self.burbuja.deleteLater()
                self.burbuja = None
            self.hablando = True
            QTimer.singleShot(int(ms), lambda: setattr(self, "hablando", False))
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
        self.show()
        self.raise_()

    def iniciar(self):
        self.app.exec()