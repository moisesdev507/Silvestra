"""Servidor local HTTP y SSE para mostrar la cara de Silvestra en una tablet."""
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse

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

import acciones
import estado
from pantalla_remota_web import PAGINA_HTML

PUERTO_DEFECTO = 8765
_lock = threading.Lock()


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [pantalla_remota]."""
    print(f"[pantalla_remota] {mensaje}", flush=True)


def obtener_ip_local():
    """Obtiene la dirección IP de la laptop en la red local WiFi o Ethernet."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


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


class PantallaRemotaHandler(http.server.BaseHTTPRequestHandler):
    """Manejador HTTP que valida token, sirve la página web y emite eventos SSE."""

    def log_message(self, format, *args):
        # Desactivar logs por defecto de BaseHTTPRequestHandler en consola
        pass

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url_parsed.query)
        token_cliente = query.get("token", [""])[0]

        if token_cliente != self.server.token_autorizado:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Acceso denegado: token inválido o no suministrado.".encode("utf-8"))
            log(f"Intento de acceso rechazado desde {self.client_address[0]}")
            return

        if url_parsed.path in ("/", "/index.html"):
            contenido = PAGINA_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(contenido)
            log(f"Página servida a cliente en {self.client_address[0]}")
            return

        if url_parsed.path == "/eventos":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            log(f"Conexión de eventos SSE establecida desde {self.client_address[0]}")
            try:
                while not self.server.detener_event.is_set():
                    datos = self.server.gestor.obtener_estado_dict()
                    payload = json.dumps(datos, ensure_ascii=False)
                    msg = f"data: {payload}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                log(f"Fin de flujo SSE con {self.client_address[0]}: {e}")
            finally:
                log(f"Conexión SSE cerrada desde {self.client_address[0]}")
            return

        self.send_response(404)
        self.end_headers()


class GestorPantallaRemota:
    """Orquesta el ciclo de vida del servidor HTTP local y la publicación de estado."""

    def __init__(self, app):
        self.app = app
        self._servidor = None
        self._hilo = None
        self._detener_event = threading.Event()
        self.ventana_qr = None

        d = estado.cargar()
        self.token = d.get("remota_token")
        if not self.token:
            self.token = secrets.token_urlsafe(24)
            d["remota_token"] = self.token
            estado.guardar(d)

        self.puerto = d.get("remota_puerto", PUERTO_DEFECTO)
        self.activa = d.get("remota_activa", False)

        if self.activa:
            self.iniciar_servidor()

    def obtener_url_completa(self):
        """Devuelve la URL accesible desde la red local para la tablet."""
        ip = obtener_ip_local()
        return f"http://{ip}:{self.puerto}/?token={self.token}"

    def obtener_estado_dict(self):
        """Lee el estado en vivo de Silvestra sin bloquear ni invocar métodos Qt."""
        with _lock:
            descansando = getattr(self.app, "descansando", False)
            escuchando = getattr(self.app, "escuchando", False)
            pensando = getattr(self.app.cara, "pensando", False)
            hablando = False
            voz = getattr(self.app, "voz", None)
            if voz and hasattr(voz, "ocupada"):
                try:
                    hablando = voz.ocupada()
                except Exception:
                    hablando = False

            if descansando:
                est = "dormida"
            elif hablando:
                est = "hablando"
            elif pensando:
                est = "pensando"
            elif escuchando:
                est = "escuchando"
            else:
                est = "reposo"

            emocion = getattr(self.app.cara, "emocion_objetivo", "neutral") or "neutral"
            vol = float(getattr(voz, "nivel_volumen", 0.0) if voz else 0.0)
            subtitulo = getattr(self.app, "ultimo_dicho", "") if hablando else ""

            return {
                "estado": est,
                "emocion": emocion,
                "volumen": vol,
                "subtitulo": subtitulo,
                "t": time.time(),
            }

    def iniciar_servidor(self):
        """Inicia el servidor HTTP en un hilo secundario daemon."""
        if self._servidor is not None:
            return True

        self._detener_event.clear()
        try:
            servidor = http.server.ThreadingHTTPServer(("0.0.0.0", self.puerto), PantallaRemotaHandler)
            servidor.token_autorizado = self.token
            servidor.detener_event = self._detener_event
            servidor.gestor = self
            self._servidor = servidor

            def _correr():
                log(f"Servidor iniciado en http://0.0.0.0:{self.puerto}")
                try:
                    servidor.serve_forever()
                except Exception as ex:
                    log(f"Servidor finalizado: {ex}")

            self._hilo = threading.Thread(target=_correr, daemon=True, name="ServidorPantallaRemota")
            self._hilo.start()
            return True
        except Exception as e:
            log(f"Error al iniciar servidor en puerto {self.puerto}: {e}")
            self._servidor = None
            return False

    def detener_servidor(self):
        """Detiene el servidor HTTP y cierra los sockets activos."""
        if self._servidor is None:
            return

        self._detener_event.set()
        try:
            self._servidor.shutdown()
            self._servidor.server_close()
        except Exception as e:
            log(f"Error deteniendo servidor: {e}")
        finally:
            self._servidor = None
            self._hilo = None
            log("Servidor detenido correctamente.")

    def accion_mostrar_en_tablet(self):
        """Inicia la pantalla remota, copia la URL y abre la ventana con el código QR."""
        ok = self.iniciar_servidor()
        d = estado.cargar()
        d["remota_activa"] = True
        estado.guardar(d)

        url = self.obtener_url_completa()

        self.app.cola.put(("copiar_portapapeles", url))
        msg_voz = "Pantalla remota lista en tu red local. Ya copié la dirección al portapapeles."
        burbuja = f"📱 PANTALLA REMOTA:\n{url}\n\n(Enlace copiado al portapapeles)"
        self.app.cola.put(("hablar_registro", (msg_voz, burbuja)))

        def _mostrar_dialogo():
            try:
                if self.ventana_qr is not None:
                    self.ventana_qr.close()
                self.ventana_qr = VentanaQR(url)
                self.ventana_qr.show()
                self.ventana_qr.raise_()
                self.ventana_qr.activateWindow()
            except Exception as e:
                log(f"Error abriendo ventana QR: {e}")

        # Programar la apertura de la ventana de forma segura en el hilo de Qt
        if hasattr(self.app.cara, "root") and hasattr(self.app.cara.root, "after"):
            self.app.cara.root.after(100, _mostrar_dialogo)

    def accion_ocultar_en_tablet(self):
        """Detiene el servidor y actualiza estado.json."""
        self.detener_servidor()
        d = estado.cargar()
        d["remota_activa"] = False
        estado.guardar(d)
        if self.ventana_qr is not None:
            try:
                self.ventana_qr.close()
                self.ventana_qr = None
            except Exception:
                pass
        self.app.cola.put(("hablar", "Pantalla remota desactivada."))


def instalar(app):
    """Instala el módulo de pantalla remota y registra sus acciones en Silvestra."""
    gestor = GestorPantallaRemota(app)
    app.pantalla_remota = gestor

    acciones.registrar(
        "mostrar_en_tablet",
        lambda: gestor.accion_mostrar_en_tablet(),
        "muestra la cara de Silvestra en una tablet o pantalla remota de la red local con un código QR y enlace.",
    )
    acciones.registrar(
        "ocultar_en_tablet",
        lambda: gestor.accion_ocultar_en_tablet(),
        "apaga el servidor de pantalla remota para tablet.",
    )

    log("Módulo de pantalla remota instalado.")
    return gestor
