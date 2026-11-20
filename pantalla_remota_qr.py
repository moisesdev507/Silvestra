"""Ventana de diálogo emergente y generador de código QR para la pantalla remota."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


def generar_qr_pixmap(texto):
    """Genera un QPixmap con el código QR usando OpenCV sin librerías externas."""
    try:
        import cv2
        if hasattr(cv2, "QRCodeEncoder_create"):
            enc = cv2.QRCodeEncoder_create()
            qr_img = enc.encode(texto)
            borde = 4
            qr_con_borde = cv2.copyMakeBorder(
                qr_img, borde, borde, borde, borde, cv2.BORDER_CONSTANT, value=255
            )
            qr_escalado = cv2.resize(qr_con_borde, (260, 260), interpolation=cv2.INTER_NEAREST)
            h, w = qr_escalado.shape
            qimg = QImage(qr_escalado.data, w, h, w, QImage.Format_Grayscale8)
            return QPixmap.fromImage(qimg)
    except Exception as e:
        print(f"[pantalla_remota] Error generando código QR: {e}", flush=True)
    return None


class VentanaQR(QDialog):
    """Ventana emergente que muestra el código QR y la URL de la tablet."""

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Silvestra - Pantalla Remota Tablet")
        self.setStyleSheet(
            "background-color: #070b14; color: #ffffff; font-family: 'Segoe UI', sans-serif;"
        )
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(360, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        lbl_tit = QLabel("📱 Silvestra Jarvis HUD")
        lbl_tit.setStyleSheet("font-size: 18px; font-weight: bold; color: #00f0ff;")
        lbl_tit.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_tit)

        lbl_desc = QLabel("Escanea este código con tu tablet o abre el enlace en Google Chrome:")
        lbl_desc.setStyleSheet("font-size: 13px; color: #94a3b8;")
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_desc)

        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        pix = generar_qr_pixmap(url)
        if pix:
            self.lbl_qr.setPixmap(pix)
        else:
            self.lbl_qr.setText("(Código QR no disponible)")
            self.lbl_qr.setStyleSheet("color: #64748b; font-size: 14px;")
        lay.addWidget(self.lbl_qr)

        lbl_url = QLabel(url)
        lbl_url.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; color: #ffd166; "
            "background: #0f172a; padding: 8px; border-radius: 6px; border: 1px solid #1e293b;"
        )
        lbl_url.setWordWrap(True)
        lbl_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(lbl_url)

        lay_btn = QHBoxLayout()
        btn_copiar = QPushButton("Copiar enlace")
        btn_copiar.setStyleSheet(
            "background: #0284c7; color: white; padding: 8px 14px; border-radius: 6px; font-weight: bold;"
        )
        btn_copiar.clicked.connect(lambda: QApplication.clipboard().setText(url))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setStyleSheet(
            "background: #334155; color: white; padding: 8px 14px; border-radius: 6px;"
        )
        btn_cerrar.clicked.connect(self.close)

        lay_btn.addWidget(btn_copiar)
        lay_btn.addWidget(btn_cerrar)
        lay.addLayout(lay_btn)
