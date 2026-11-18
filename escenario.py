"""Ventana principal cinematográfica del Modo Escenario para la presentación."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

import acciones
from escenario_estilo import (
    COLOR_CIAN_BRILLO, COLOR_TEXTO_BLANCO, COLOR_TEXTO_ATENUADO,
    calcular_zonas, dibujar_cinematica, dibujar_panel_marco
)
from escenario_fondo import FondoEscenario
from escenario_intro import SecuenciaArranque
from escenario_nodos import ArcoNodos
from escenario_escenas import EscenasEscenario
from hud_orbe import OrbeJarvis
from proveedores import forzar_utf8


class Escenario(QWidget):
    """Escenario cinematográfico a pantalla completa con zonas fijas sin superposición."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Silvestra - Modo Escenario Cinematográfico")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self.fondo = FondoEscenario()
        self.intro = SecuenciaArranque()
        self.nodos = ArcoNodos()
        self.escenas = EscenasEscenario(app)

        self.nodo_activo = "cerebro"
        self.subtitulo_texto = ""
        self._cara_tam_orig = None
        self._cara_pos_orig = None
        self._cara_paseo_orig = None

        # Orbe Jarvis decorativo
        self.orbe = OrbeJarvis(app, self, tamano=80)

        self.reloj = QTimer(self)
        self.reloj.timeout.connect(self._tic)

    def mostrar(self):
        """Abre el escenario, calcula zonas proporcionales y posiciona a Silvestra sin superposiciones."""
        g = QApplication.primaryScreen().geometry()
        w, h = g.width(), g.height()
        self.setGeometry(g)
        self.fondo.inicializar(w, h)
        self.intro.reiniciar()

        zonas = calcular_zonas(w, h)

        # Ubicar orbe decorativo discretamente en la zona superior izquierda
        self.orbe.move(int(zonas["cara_cx"] - 40), int(zonas["cara_cy"] - zonas["cara_tam"] / 2.0 - 55))
        self.showFullScreen()
        self.raise_()

        # Posicionar a Silvestra en la zona izquierda exclusiva (sin tocar el panel derecho)
        if hasattr(self.app, "cara") and self.app.cara:
            c = self.app.cara
            c.silenciar_burbuja = True  # Ocultar burbuja flotante: texto solo en subtítulos
            self._cara_tam_orig = (c.width(), c.height())
            self._cara_pos_orig = (c.x(), c.y())
            self._cara_paseo_orig = bool(getattr(c, "accion_paseo", None) and c.accion_paseo.isChecked())
            if hasattr(c, "accion_paseo"):
                c.accion_paseo.setChecked(False)

            tam = zonas["cara_tam"]
            c.resize(tam, tam)
            c.move(int(zonas["cara_rect"].x()), int(zonas["cara_rect"].y()))
            c.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            c.show()
            c.raise_()

        self.activateWindow()
        self.setFocus()
        if not self.reloj.isActive():
            self.reloj.start(33)

    def cerrar(self):
        """Cierra el escenario y restaura la cara a su estado y posición normales."""
        if hasattr(self.app, "presentacion_activa"):
            self.app.presentacion_activa = False
        if self.reloj.isActive():
            self.reloj.stop()
        self.escenas.cerrar()
        self.hide()

        if hasattr(self.app, "cara") and self.app.cara:
            c = self.app.cara
            c.silenciar_burbuja = False  # Restaurar burbuja normal de conversación
            if self._cara_tam_orig:
                c.resize(self._cara_tam_orig[0], self._cara_tam_orig[1])
            if self._cara_pos_orig:
                c.move(self._cara_pos_orig[0], self._cara_pos_orig[1])
            if self._cara_paseo_orig is not None and hasattr(c, "accion_paseo"):
                c.accion_paseo.setChecked(self._cara_paseo_orig)
            c.raise_()
            if hasattr(c, "activateWindow"):
                c.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cerrar()
        elif event.key() == Qt.Key_1:
            self.simular_gesto("palma")
        elif event.key() == Qt.Key_2:
            self.simular_gesto("puno")
        elif event.key() == Qt.Key_3:
            self.simular_gesto("paz")
        else:
            super().keyPressEvent(event)

    def simular_gesto(self, g):
        """Simula un gesto mediante el teclado (1: palma, 2: puño, 3: dos dedos)."""
        from camara import GESTOS, NOMBRES
        accion = GESTOS.get(g)
        if accion:
            acciones.ejecutar(accion)
            if hasattr(self, "escenas") and self.escenas:
                self.escenas.registrar_gesto((g, accion, NOMBRES.get(g, g), True))
            self.update()

    def registrar_gesto(self, datos):
        """Registra un gesto detectado por la cámara o manual y repinta el escenario."""
        if hasattr(self, "escenas") and self.escenas:
            self.escenas.registrar_gesto(datos)
        self.update()

    def avanzar_paso(self, datos_paso):
        """Actualiza el nodo activo, la escena y re-sube la cara de Silvestra."""
        if isinstance(datos_paso, (tuple, list)) and len(datos_paso) >= 2:
            escena, nodo = datos_paso[0], datos_paso[1]
        else:
            escena = str(datos_paso)
            nodo = escena

        self.nodo_activo = nodo
        self.escenas.fijar_escena(escena)

        if hasattr(self.app, "cara") and self.app.cara:
            self.app.cara.raise_()

        self.update()

    def actualizar_subtitulo(self, texto):
        self.subtitulo_texto = forzar_utf8(texto).strip()
        if hasattr(self.app, "cara") and self.app.cara:
            self.app.cara.raise_()
        self.update()

    def fijar_captura(self, qimg):
        self.escenas.fijar_captura(qimg)
        self.update()

    def _tic(self):
        w, h = self.width(), self.height()
        if w > 0 and h > 0:
            self.fondo.avanzar(w, h)
            self.intro.avanzar()
            self.nodos.avanzar()
            self.escenas.avanzar()
            self.orbe.avanzar()
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            zonas = calcular_zonas(w, h)

            # 1. Fondo espacial animado y anillo de energía en Silvestra
            voz_ocupada = bool(hasattr(self.app, "voz") and self.app.voz.ocupada())
            self.fondo.dibujar(p, w, h, zonas["cara_cx"], zonas["cara_cy"], zonas["cara_tam"], voz_ocupada)

            # 2. Arco de nodos y paquetes de datos hacia Silvestra
            self.nodos.dibujar(p, zonas["nodos_rect"], self.nodo_activo, voz_ocupada, zonas["cara_cx"], zonas["cara_cy"])

            # 3. Zona Central-Derecha: Secuencia de arranque o Panel de Escena
            if not self.intro.terminado():
                self.intro.dibujar(p, w, h)
            else:
                self.escenas.dibujar(p, zonas["panel_rect"])

            # 4. Barra Superior (Cinemática y título)
            p.setFont(QFont("Segoe UI", 11, QFont.Bold))
            p.setPen(COLOR_CIAN_BRILLO)
            p.drawText(int(w * 0.04), int(zonas["h_barras"] + 18), "SILVESTRA ARCHITECTURE // PRESENTACIÓN AUTÓNOMA EN VIVO")

            p.setFont(QFont("Segoe UI", 9))
            p.setPen(COLOR_TEXTO_ATENUADO)
            p.drawText(QRectF(w - 230, zonas["h_barras"] + 4, 190, 20), Qt.AlignRight, "Presiona [Esc] para salir")

            # 5. Barra Inferior de Subtítulos (Tipografía grande, nítida y legible)
            sub_r = zonas["sub_rect"]
            dibujar_panel_marco(p, sub_r, brillo_intenso=bool(self.subtitulo_texto))

            if self.subtitulo_texto:
                p.setFont(QFont("Segoe UI", 15, QFont.Bold))
                p.setPen(COLOR_TEXTO_BLANCO)
                p.drawText(QRectF(sub_r.x() + 24, sub_r.y() + 8, sub_r.width() - 48, sub_r.height() - 16),
                           Qt.AlignCenter, f"« {self.subtitulo_texto} »")
            else:
                p.setFont(QFont("Segoe UI", 11))
                p.setPen(COLOR_TEXTO_ATENUADO)
                p.drawText(sub_r, Qt.AlignCenter, "— EN ESPERA DE INTERVENCIÓN VOCAL —")

            # 6. Barras negras superior e inferior y viñeta en bordes
            dibujar_cinematica(p, w, h, zonas["h_barras"])
        finally:
            p.end()


def instalar(app):
    app.escenario = Escenario(app)
    app.abrir_escenario = app.escenario.mostrar
    app.cerrar_escenario = app.escenario.cerrar

    acciones.registrar(
        "cerrar_escenario",
        lambda: app.cerrar_escenario(),
        "cierra el modo escenario a pantalla completa y regresa al escritorio",
    )
