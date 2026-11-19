"""Gestión de datos del panel de información y reloj de mesa para la tablet."""
import datetime
import json
import os
import threading
import time

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

import estado

RUTA_RECORDATORIOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordatorios.json")


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [pantalla_remota]."""
    print(f"[pantalla_remota] {mensaje}", flush=True)


class GestorPanelRemoto:
    """Recolecta clima, próximos recordatorios, saludo matutino y hora sin consultas de red extras."""

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._detener = threading.Event()
        self.cache_panel = {
            "clima": "",
            "recordatorios": [],
            "saludo": "",
            "modo_privado": False,
            "es_noche": False,
            "hora_12": "",
            "ampm": "",
            "fecha": "",
            "ts": 0,
        }
        self.actualizar_cache()
        self._hilo = threading.Thread(target=self._bucle_actualizacion, daemon=True, name="PanelRemotoLoop")
        self._hilo.start()

    def _bucle_actualizacion(self):
        """Actualiza los datos del panel cada 15 segundos en segundo plano."""
        while not self._detener.is_set():
            try:
                self.actualizar_cache()
            except Exception as e:
                log(f"Error actualizando panel remoto: {e}")
            for _ in range(15):
                if self._detener.is_set():
                    break
                time.sleep(1)

    def actualizar_cache(self):
        """Obtiene de memoria y disco los datos del panel con manejo tolerante a fallos."""
        with self._lock:
            ahora = datetime.datetime.now()

            # 1. Hora 12h y fecha en español (hora local de Panamá)
            h_int = ahora.hour % 12
            if h_int == 0:
                h_int = 12
            hora_12 = f"{h_int}:{ahora.strftime('%M')}"
            ampm = "AM" if ahora.hour < 12 else "PM"

            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            fecha = f"{dias[ahora.weekday()]}, {ahora.day} de {meses[ahora.month - 1]}"

            # 2. Modo noche (entre las 10 PM y las 6 AM)
            es_noche = (ahora.hour >= 22 or ahora.hour < 6)

            # 3. Estado persistente (modo privado y último saludo)
            est = estado.cargar()
            modo_privado = bool(est.get("tablet_modo_privado", False))
            ultimo_saludo = est.get("ultimo_saludo", "")
            saludo_corto = ""
            if ultimo_saludo:
                saludo_corto = str(ultimo_saludo).strip().replace("\n", " ")
                if len(saludo_corto) > 110:
                    saludo_corto = saludo_corto[:107] + "..."

            # 4. Clima (reutilizado desde hud.py sin consultas de red)
            clima_txt = ""
            if hasattr(self.app, "ultimo_clima") and self.app.ultimo_clima:
                clima_txt = str(self.app.ultimo_clima).strip()
            elif hasattr(self.app, "hud") and self.app.hud and hasattr(self.app.hud, "lbl_clima"):
                try:
                    clima_txt = self.app.hud.lbl_clima.text().strip()
                except Exception:
                    pass

            # 5. Próximos recordatorios (máx 3 con hora y título corto)
            recs_lista = []
            if not modo_privado and os.path.exists(RUTA_RECORDATORIOS):
                try:
                    with open(RUTA_RECORDATORIOS, "r", encoding="utf-8") as f:
                        todos = json.load(f)
                    ahora_ts = time.time()
                    pendientes = [
                        r for r in todos
                        if not r.get("completado") and r.get("timestamp", 0) >= ahora_ts - 300
                    ]
                    pendientes.sort(key=lambda x: x.get("timestamp", 0))
                    for r in pendientes[:3]:
                        txt = r.get("texto", "Recordatorio").strip()
                        if len(txt) > 34:
                            txt = txt[:31] + "..."
                        recs_lista.append({
                            "hora": r.get("hora_exacta", "--:--"),
                            "texto": txt,
                        })
                except Exception:
                    recs_lista = []

            self.cache_panel = {
                "clima": clima_txt,
                "recordatorios": recs_lista,
                "saludo": saludo_corto,
                "modo_privado": modo_privado,
                "es_noche": es_noche,
                "hora_12": hora_12,
                "ampm": ampm,
                "fecha": fecha,
                "ts": ahora.timestamp(),
            }

    def obtener_datos(self):
        """Retorna una copia de los datos del panel en caché."""
        with self._lock:
            return dict(self.cache_panel)

    def fijar_modo_privado(self, privado):
        """Guarda y actualiza el modo privado de la tablet."""
        with self._lock:
            est = estado.cargar()
            est["tablet_modo_privado"] = bool(privado)
            estado.guardar(est)
            self.cache_panel["modo_privado"] = bool(privado)
            if privado:
                self.cache_panel["recordatorios"] = []
            log(f"Modo privado {'activado' if privado else 'desactivado'}.")
            return bool(privado)


def generar_qr_pixmap(texto):
    """Genera un QPixmap con el código QR usando OpenCV sin librerías externas."""
    try:
        import cv2
        if hasattr(cv2, "QRCodeEncoder_create"):
            enc = cv2.QRCodeEncoder_create()
            qr_img = enc.encode(texto)
            borde = 4
            qr_con_borde = cv2.copyMakeBorder(qr_img, borde, borde, borde, borde, cv2.BORDER_CONSTANT, value=255)
            qr_escalado = cv2.resize(qr_con_borde, (260, 260), interpolation=cv2.INTER_NEAREST)
            h, w = qr_escalado.shape
            app_qt = QApplication.instance() or QApplication([])
            qimg = QImage(qr_escalado.data, w, h, w, QImage.Format_Grayscale8)
            return QPixmap.fromImage(qimg)
    except Exception as e:
        log(f"No se pudo generar código QR con OpenCV: {e}")
    return None


class VentanaQR(QDialog):
    """Ventana emergente que muestra el código QR y la URL de la tablet."""

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Silvestra - Pantalla Remota Tablet")
        self.setStyleSheet("background-color: #131824; color: #ffffff; font-family: 'Segoe UI', sans-serif;")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(360, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        lbl_tit = QLabel("📱 Silvestra en tu Tablet")
        lbl_tit.setStyleSheet("font-size: 18px; font-weight: bold; color: #4fd1c5;")
        lbl_tit.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_tit)

        lbl_desc = QLabel("Escanea este código QR con la cámara de tu tablet o abre el enlace en Google Chrome:")
        lbl_desc.setStyleSheet("font-size: 13px; color: #a0aec0;")
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
            self.lbl_qr.setStyleSheet("color: #718096; font-size: 14px;")
        lay.addWidget(self.lbl_qr)

        lbl_url = QLabel(url)
        lbl_url.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #ffd166; background: #1b2333; padding: 8px; border-radius: 6px; border: 1px solid #2d3748;")
        lbl_url.setWordWrap(True)
        lbl_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(lbl_url)

        lay_btn = QHBoxLayout()
        btn_copiar = QPushButton("Copiar enlace")
        btn_copiar.setStyleSheet("background: #2b6cb0; color: white; padding: 8px 14px; border-radius: 6px; font-weight: bold;")
        btn_copiar.clicked.connect(lambda: QApplication.clipboard().setText(url))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setStyleSheet("background: #4a5568; color: white; padding: 8px 14px; border-radius: 6px;")
        btn_cerrar.clicked.connect(self.close)

        lay_btn.addWidget(btn_copiar)
        lay_btn.addWidget(btn_cerrar)
        lay.addLayout(lay_btn)

