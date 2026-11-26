"""Diálogo único de configuración de Kaya, con calibración de voz opcional."""
from __future__ import annotations

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

ESTILO = """
QDialog { background: #08121E; color: #E2E8F0; border: 1px solid #22D3EE;
          border-radius: 12px; font-size: 12px; }
QLabel#titulo { color: #22D3EE; font-size: 17px; font-weight: bold;
                padding: 12px 14px 4px 14px; letter-spacing: 1px; }
QLabel { color: #94A3B8; }
QLabel#estado { color: #FBBF24; }
QLineEdit, QComboBox { background: #0F2233; color: #E2E8F0; border: 1px solid #164E63;
                       border-radius: 6px; padding: 5px 8px; min-height: 24px; }
QPushButton { background: #0F2233; color: #E2E8F0; border: 1px solid #22D3EE;
              border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #16364A; }
QPushButton:disabled { color: #64748B; border-color: #334155; }
QPushButton#guardar { background: #22D3EE; color: #06121C; font-weight: bold; }
QLabel a { color: #67E8F9; }
"""

FRASES_VOZ = (
    "Kaya, esta es mi voz y quiero que me reconozcas.",
    "Hoy estoy configurando mi asistente en mi propia laptop.",
    "Recuerda mi nombre y responde solo cuando me escuches.",
)


class _Calibrador(QThread):
    """Graba 3 frases en hilo secundario; nunca toca widgets directamente."""

    progreso = Signal(str)
    terminado = Signal(bool, str)

    def __init__(self, frases):
        super().__init__()
        self.frases = tuple(frases)
        self._cancelar = None

    def cancelar(self):
        if self._cancelar is not None:
            self._cancelar.set()

    def _grabar(self, sd, segundos=3.0):
        import threading
        if self._cancelar is None:
            self._cancelar = threading.Event()
        trozos = []
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                            blocksize=1600) as flujo:
            for _ in range(int(segundos * 10)):
                if self._cancelar.is_set():
                    return None
                datos, _ = flujo.read(1600)
                trozos.append(datos.copy())
        import numpy as np
        return np.concatenate(trozos) if trozos else None

    def run(self):
        try:
            import numpy as np
            import sounddevice as sd
            import voz_dueno
            from voz_dueno_banco import guardar_banco, preparar_audio_biometria
            if not os.path.exists(voz_dueno.MODELO_ONNX):
                self.terminado.emit(False, "Falta el modelo local de voz; puedes omitir este paso.")
                return
            if self._cancelar is None:
                import threading
                self._cancelar = threading.Event()
            embeddings = []
            for i, frase in enumerate(self.frases):
                if self._cancelar.is_set():
                    break
                self.progreso.emit(f"Frase {i + 1}/3 · di: «{frase}»")
                audio = self._grabar(sd)
                if audio is None:
                    break
                limpio, duracion = preparar_audio_biometria(audio)
                if limpio is None or duracion < 0.6:
                    self.progreso.emit("No te escuché bien; repite la frase.")
                    audio = self._grabar(sd)
                    if audio is None:
                        break
                    limpio, duracion = preparar_audio_biometria(audio)
                if limpio is None or duracion < 0.6:
                    break
                embeddings.append(voz_dueno.extraer_embedding(limpio))
            if self._cancelar.is_set() or len(embeddings) != len(self.frases):
                self.terminado.emit(False, "Calibración cancelada; puedes repetirla cuando quieras.")
                return
            guardar_banco(voz_dueno.ARCHIVO_VOZ, np.asarray(embeddings, dtype=np.float32))
            import estado
            datos = estado.cargar()
            datos["verificacion_voz_activa"] = True
            estado.guardar(datos)
            self.terminado.emit(True, "Huella de voz guardada en esta laptop.")
        except Exception as e:
            self.terminado.emit(False, f"No se pudo calibrar ({type(e).__name__}). Puedes omitirlo.")


class ConfigKayaDialog(QDialog):
    """Ventana limpia de Kaya: nombre, claves, tecla de encendido y audio."""

    def __init__(self, base=None, parent=None, onboarding=False):
        super().__init__(parent)
        import onboarding_qt as ob
        self._ob = ob
        self.base = base or ob.BASE
        self.ruta_env = os.path.join(self.base, ".env")
        self.resultado = False
        self.campos = {}
        self._hilo = None
        self.onboarding = bool(onboarding)
        self._guardar_fn = ob.guardar_configuracion
        self.setWindowTitle("Kaya · Configuración inicial" if onboarding
                            else "Kaya · Configuración")
        self.setModal(True)
        self.setFixedWidth(560)
        self.setStyleSheet(ESTILO)
        raiz = QVBoxLayout(self)
        titulo = QLabel("◈  KAYA  /  BIENVENIDA" if onboarding
                        else "◈  KAYA  /  AJUSTES")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)
        raiz.addWidget(QLabel("Configura Kaya en esta laptop. Tus claves no salen de aquí."))

        actuales = ob.leer_env(self.ruta_env)
        formulario = QFormLayout()
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej. Alex")
        try:
            import persistencia_segura as ps
            memoria = ps.cargar_json_seguro(
                os.path.join(self.base, "memoria.json"), {})
            if isinstance(memoria, dict):
                self.campo_nombre.setText(str(memoria.get("usuario", "") or ""))
        except Exception:
            pass
        formulario.addRow("Nombre del usuario", self.campo_nombre)
        for clave in ob.CLAVES:
            campo = QLineEdit()
            campo.setEchoMode(QLineEdit.Password)
            campo.setPlaceholderText("Pega tu clave aquí")
            campo.setText(str(actuales.get(clave, "") or ""))
            self.campos[clave] = campo
            ver = QPushButton("👁")
            ver.setCheckable(True)
            ver.setToolTip("Mostrar u ocultar")
            ver.toggled.connect(lambda _c, c=campo, b=ver: self._alternar(c, b))
            enlace = QLabel(f'<a href="{ob.ENLACES[clave]}">Conseguir clave ↗</a>')
            enlace.setOpenExternalLinks(False)
            enlace.linkActivated.connect(self._abrir)
            fila = QWidget()
            caja = QHBoxLayout(fila)
            caja.setContentsMargins(0, 0, 0, 0)
            caja.addWidget(campo, 1)
            caja.addWidget(ver)
            caja.addWidget(enlace)
            formulario.addRow(ob.ETIQUETAS[clave], fila)

        self.combo_tecla = QComboBox()
        self.combo_tecla.addItems(list(ob.TECLAS))
        tecla = str(actuales.get("KAYA_TECLA", "") or "").strip()
        self.combo_tecla.setCurrentText(tecla if tecla in ob.TECLAS else ob.TECLAS[0])
        formulario.addRow("Tecla de encendido", self.combo_tecla)

        self.combo_audio = QComboBox()
        self.combo_audio.addItems([nombre for nombre, _valor in ob.MODOS_AUDIO])
        audifonos = str(actuales.get("KAYA_MODO_AUDIFONOS", "0")).strip() == "1"
        self.combo_audio.setCurrentIndex(0 if audifonos else 1)
        formulario.addRow("Audio", self.combo_audio)
        raiz.addLayout(formulario)

        if not onboarding:
            raiz.addWidget(QLabel("Opcional: graba 3 frases para que Kaya reconozca tu voz."))
            fila_voz = QHBoxLayout()
            self.btn_grabar = QPushButton("🎙️ Grabar 3 frases")
            self.btn_grabar.clicked.connect(self._calibrar)
            self.btn_omitir = QPushButton("Omitir por ahora")
            self.btn_omitir.clicked.connect(self._omitir)
            fila_voz.addWidget(self.btn_grabar)
            fila_voz.addWidget(self.btn_omitir)
            raiz.addLayout(fila_voz)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("estado")
        self.lbl_estado.setWordWrap(True)
        raiz.addWidget(self.lbl_estado)

        pie = QHBoxLayout()
        guardar = QPushButton("Probar y Guardar" if onboarding else "Guardar")
        guardar.setObjectName("guardar")
        guardar.clicked.connect(self._guardar)
        salir = QPushButton("Salir")
        salir.clicked.connect(self.reject)
        pie.addWidget(guardar)
        pie.addWidget(salir)
        raiz.addLayout(pie)

    def _abrir(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    def _alternar(self, campo, boton):
        campo.setEchoMode(QLineEdit.Normal if boton.isChecked() else QLineEdit.Password)

    def _guardar(self):
        claves = {clave: self.campos[clave].text() for clave in self._ob.CLAVES}
        ok, mensaje = self._guardar_fn(
            self.campo_nombre.text(), claves, base=self.base, ruta_env=self.ruta_env,
            tecla=self.combo_tecla.currentText(),
            audifonos=self.combo_audio.currentIndex() == 0)
        self.lbl_estado.setText(mensaje)
        if ok:
            self.resultado = True
            self.accept()

    def _calibrar(self):
        if self._hilo and self._hilo.isRunning():
            return
        self.btn_grabar.setEnabled(False)
        self.lbl_estado.setText("Preparando micrófono…")
        self._hilo = _Calibrador(FRASES_VOZ)
        self._hilo.progreso.connect(self.lbl_estado.setText)
        self._hilo.terminado.connect(self._fin_calibracion)
        self._hilo.start()

    def _fin_calibracion(self, ok, mensaje):
        self.btn_grabar.setEnabled(True)
        self.lbl_estado.setText(("✅ " if ok else "⚠️ ") + mensaje)

    def _omitir(self):
        if self._hilo and self._hilo.isRunning():
            self._hilo.cancelar()
        self.btn_grabar.setEnabled(True)
        self.lbl_estado.setText("Calibración omitida. Puedes hacerla después desde el menú.")


def abrir_configuracion(app=None, base=None):
    """Abre la ventana única de Kaya; recarga la hotkey si se guardó."""
    dialogo = ConfigKayaDialog(base=base)
    dialogo.exec()
    if dialogo.resultado and app is not None:
        try:
            import tecla_kaya
            tecla_kaya.recargar(app)
        except Exception:
            pass
    return bool(dialogo.resultado)
