"""Controles del diálogo QR para activar TLS sin bloquear su hilo Qt."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton
import threading


class SenalesQR(QObject):
    codigo = Signal(str)
    red = Signal(str)


def codigo_async(signals, generar):
    def run():
        try: signals.codigo.emit(generar())
        except Exception: signals.codigo.emit("")
    threading.Thread(target=run, daemon=True).start()


def agregar_tls(dialogo, layout, activar):
    signal = dialogo._signals.red
    signal.connect(dialogo._actualizar_url)
    dialogo.lbl_red = QLabel("Enlace local; la tablet requiere activar TLS en red.")
    dialogo.lbl_red.setWordWrap(True); layout.addWidget(dialogo.lbl_red)
    boton = QPushButton("Activar acceso de red con TLS")
    boton.clicked.connect(lambda: _seleccionar(dialogo, activar, signal))
    layout.addWidget(boton)


def _seleccionar(dialogo, activar, signal):
    cert, _ = QFileDialog.getOpenFileName(dialogo, "Certificado TLS", "", "Certificados (*.pem *.crt)")
    key, _ = QFileDialog.getOpenFileName(dialogo, "Clave TLS", "", "Claves (*.pem *.key)")
    if not cert or not key: return
    def run():
        try: result = activar(cert, key) or ""
        except Exception: result = ""
        signal.emit(result)
    threading.Thread(target=run, daemon=True).start()
