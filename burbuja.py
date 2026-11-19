"""Widgets auxiliares para la cara de Silvestra: Burbuja de texto flotante y ventana de Entrada."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget


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
