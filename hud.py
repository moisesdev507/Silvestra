"""Panel HUD estilo Jarvis para Silvestra (PySide6).

Ventana flotante translúcida, sin bordes, siempre visible y arrastrable.
Muestra hora, fecha, clima de Panamá, uso de CPU y RAM, y un orbe animado
que reacciona en tiempo real al estado de Silvestra.
"""
import datetime
import json
import threading
import time
import urllib.request

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

import acciones
import estado
import hud_orbe

CIUDAD = "Ciudad de Panamá"
LAT = 8.98
LON = -79.52

CIELO = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado",
    3: "nublado", 45: "neblina", 48: "neblina", 51: "llovizna",
    53: "llovizna", 55: "llovizna", 61: "lluvia ligera", 63: "lluvia",
    65: "lluvia fuerte", 80: "chubascos", 81: "chubascos", 82: "chubascos fuertes",
    95: "tormenta", 96: "tormenta", 99: "tormenta",
}


class PanelHUD(QWidget):
    """Ventana HUD translúcida estilo Jarvis."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.arrastre = None
        self.vivo = True

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(300, 142)

        self.caja = QFrame(self)
        self.caja.setGeometry(0, 0, 300, 142)
        self.caja.setStyleSheet(
            "QFrame { background-color: rgba(10, 15, 29, 0.88); "
            "border: 1px solid rgba(34, 211, 238, 0.45); border-radius: 12px; }"
        )

        layout = QVBoxLayout(self.caja)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Fila superior: Orbe + Hora y Fecha
        fila_sup = QHBoxLayout()
        self.orbe = hud_orbe.OrbeJarvis(app, self.caja)
        fila_sup.addWidget(self.orbe)

        col_hora = QVBoxLayout()
        col_hora.setSpacing(0)
        self.lbl_hora = QLabel("00:00", self.caja)
        self.lbl_hora.setStyleSheet("QLabel { color: #22d3ee; font-size: 20pt; font-weight: bold; border: none; }")
        self.lbl_fecha = QLabel("Cargando...", self.caja)
        self.lbl_fecha.setStyleSheet("QLabel { color: #94a3b8; font-size: 8pt; border: none; }")
        col_hora.addWidget(self.lbl_hora)
        col_hora.addWidget(self.lbl_fecha)
        fila_sup.addLayout(col_hora)
        layout.addLayout(fila_sup)

        # Fila media: Clima
        self.lbl_clima = QLabel(f"--°C · {CIUDAD}", self.caja)
        self.lbl_clima.setStyleSheet("QLabel { color: #bae6fd; font-size: 8.5pt; border: none; }")
        layout.addWidget(self.lbl_clima)

        # Fila inferior: CPU y RAM
        fila_inf = QHBoxLayout()
        self.lbl_cpu = QLabel("CPU: 0%", self.caja)
        self.lbl_cpu.setStyleSheet("QLabel { color: #38bdf8; font-size: 8pt; border: none; }")
        self.bar_cpu = QProgressBar(self.caja)
        self.bar_cpu.setRange(0, 100)
        self.bar_cpu.setFixedHeight(5)
        self.bar_cpu.setTextVisible(False)
        self.bar_cpu.setStyleSheet(
            "QProgressBar { background: rgba(30, 41, 59, 0.8); border: none; border-radius: 2px; } "
            "QProgressBar::chunk { background: #06b6d4; border-radius: 2px; }"
        )

        self.lbl_ram = QLabel("RAM: 0%", self.caja)
        self.lbl_ram.setStyleSheet("QLabel { color: #38bdf8; font-size: 8pt; border: none; }")
        self.bar_ram = QProgressBar(self.caja)
        self.bar_ram.setRange(0, 100)
        self.bar_ram.setFixedHeight(5)
        self.bar_ram.setTextVisible(False)
        self.bar_ram.setStyleSheet(
            "QProgressBar { background: rgba(30, 41, 59, 0.8); border: none; border-radius: 2px; } "
            "QProgressBar::chunk { background: #3b82f6; border-radius: 2px; }"
        )

        fila_inf.addWidget(self.lbl_cpu)
        fila_inf.addWidget(self.bar_cpu)
        fila_inf.addSpacing(8)
        fila_inf.addWidget(self.lbl_ram)
        fila_inf.addWidget(self.bar_ram)
        layout.addLayout(fila_inf)

        # Ubicar en esquina superior derecha
        pantalla = QApplication.primaryScreen().geometry()
        self.move(max(20, pantalla.width() - 330), 40)

        # Relojes: orbe (40ms), hora (1s) y métricas (2s)
        self.timer_orbe = QTimer(self)
        self.timer_orbe.timeout.connect(self.orbe.avanzar)
        self.timer_reloj = QTimer(self)
        self.timer_reloj.timeout.connect(self._actualizar_reloj)
        self.timer_metricas = QTimer(self)
        self.timer_metricas.timeout.connect(self._actualizar_metricas)

        # Hilo secundario para clima cada 10 min
        threading.Thread(target=self._hilo_clima, daemon=True).start()

    def _actualizar_reloj(self):
        ahora = datetime.datetime.now()
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
        self.lbl_hora.setText(ahora.strftime("%H:%M"))
        txt_fecha = f"{dias[ahora.weekday()]}, {ahora.day} de {meses[ahora.month - 1]}."
        self.lbl_fecha.setText(txt_fecha)

    def _actualizar_metricas(self):
        cpu, ram = hud_orbe.obtener_metricas()
        self.lbl_cpu.setText(f"CPU: {cpu}%")
        self.bar_cpu.setValue(cpu)
        self.lbl_ram.setText(f"RAM: {ram}%")
        self.bar_ram.setValue(ram)

    def actualizar_clima(self, texto):
        self.lbl_clima.setText(texto)

    def _hilo_clima(self):
        while self.vivo:
            try:
                url = (
                    "https://api.open-meteo.com/v1/forecast"
                    f"?latitude={LAT}&longitude={LON}&current=temperature_2m,weather_code&timezone=auto"
                )
                with urllib.request.urlopen(url, timeout=8) as r:
                    datos = json.load(r)["current"]
                grados = int(round(datos["temperature_2m"]))
                cielo = CIELO.get(int(datos["weather_code"]), "cielo variable")
                txt = f"{grados}°C · {cielo.capitalize()} ({CIUDAD})"
                self.app.cola.put(("hud_clima", txt))
            except Exception:
                self.app.cola.put(("hud_clima", f"--°C · {CIUDAD} (sin conexión)"))

            for _ in range(600):
                if not self.vivo:
                    break
                time.sleep(1)

    def mostrar(self):
        self._actualizar_reloj()
        self._actualizar_metricas()
        self.show()
        self.timer_orbe.start(40)
        self.timer_reloj.start(1000)
        self.timer_metricas.start(2000)

    def ocultar(self):
        self.hide()
        self.timer_orbe.stop()
        self.timer_reloj.stop()
        self.timer_metricas.stop()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            pos_global = e.globalPosition().toPoint() if hasattr(e, "globalPosition") else e.globalPos()
            self.arrastre = pos_global - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self.arrastre is not None and e.buttons() & Qt.LeftButton:
            pos_global = e.globalPosition().toPoint() if hasattr(e, "globalPosition") else e.globalPos()
            self.move(pos_global - self.arrastre)
            e.accept()

    def mouseReleaseEvent(self, _):
        self.arrastre = None


class HUD:
    """Controlador del panel HUD con persistencia y registro de acciones."""

    def __init__(self, app):
        self.app = app
        self.panel = PanelHUD(app)
        self.activo = estado.cargar().get("hud", False)

        if self.activo:
            self.panel.mostrar()
        else:
            self.panel.ocultar()

    def mostrar(self):
        self.activo = True
        try:
            est = estado.cargar()
            est["hud"] = True
            estado.guardar(est)
        except Exception:
            pass
        self.panel.mostrar()
        if not getattr(self.app, "ultimo_dicho", ""):
            self.app.cara.decir("Panel HUD activado.", 2500)

    def ocultar(self):
        self.activo = False
        try:
            est = estado.cargar()
            est["hud"] = False
            estado.guardar(est)
        except Exception:
            pass
        self.panel.ocultar()
        if not getattr(self.app, "ultimo_dicho", ""):
            self.app.cara.decir("Panel HUD ocultado.", 2500)

    def actualizar_clima(self, texto):
        self.panel.actualizar_clima(texto)

    def detener(self):
        self.panel.vivo = False
        self.panel.ocultar()


def instalar(app):
    controlador = HUD(app)
    acciones.registrar(
        "mostrar_hud",
        controlador.mostrar,
        "muestra el panel HUD de Jarvis con la hora, clima, uso de CPU y RAM y el orbe animado.",
    )
    acciones.registrar(
        "ocultar_hud",
        controlador.ocultar,
        "oculta el panel HUD de la pantalla.",
    )

    if hasattr(app, "cara") and hasattr(app.cara, "app"):
        try:
            app.cara.app.aboutToQuit.connect(controlador.detener)
        except Exception:
            pass

    return controlador
