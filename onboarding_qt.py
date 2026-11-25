"""Asistente de configuración inicial de Kaya: nombre y API keys propias."""
from __future__ import annotations

import os
import re
import tempfile
import threading

import estado
import identidad_origen
import persistencia_segura as ps
import rutas_app
from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

BASE = rutas_app.dir_usuario()
CLAVES = ("GEMINI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY")
ENLACES = {
    "GEMINI_API_KEY": "https://aistudio.google.com/app/apikey",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "DEEPGRAM_API_KEY": "https://console.deepgram.com/",
}
ETIQUETAS = {
    "GEMINI_API_KEY": "Gemini Live y visión (obligatoria)",
    "GROQ_API_KEY": "Motor clásico rápido (obligatoria)",
    "DEEPGRAM_API_KEY": "Voz en tiempo real (obligatoria)",
}
FRASES_VOZ = (
    "Kaya, esta es mi voz y quiero que me reconozcas.",
    "Hoy estoy configurando mi asistente en mi propia laptop.",
    "Recuerda mi nombre y responde solo cuando me escuches.",
)
_FORMATO = re.compile(r"^[A-Za-z0-9_.\-]{12,}$")
_NOMBRE = re.compile(r"^[\w .'\-]{1,40}$", re.UNICODE)
_MARCADORES = ("tu_clave", "tuclave", "your_key", "changeme", "cambiar",
               "xxxx", "xxx", "clave-aqui", "pega_tu_clave")


def leer_env(ruta=None):
    """Lee un .env simple sin ejecutar código ni interpretar comandos."""
    ruta = ruta or os.path.join(BASE, ".env")
    datos = {}
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                if linea.lower().startswith("export "):
                    linea = linea[7:].strip()
                if "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave = clave.strip()
                if clave:
                    datos[clave] = valor.strip().strip("'\"")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[onboarding] No se pudo leer .env: {e}", flush=True)
    return datos


def cargar_env(ruta=None):
    """Vuelca el .env local en el entorno del proceso actual."""
    for clave, valor in leer_env(ruta).items():
        if valor:
            os.environ[clave] = valor
    return leer_env(ruta)


def claves_actuales(ruta=None):
    """Combina entorno y .env; el archivo local tiene prioridad."""
    actuales = {k: str(os.environ.get(k, "") or "").strip() for k in CLAVES}
    actuales.update({k: v for k, v in leer_env(ruta).items() if k in CLAVES})
    return actuales


def validar_clave(nombre, valor):
    """Valida formato básico sin revelar ni registrar la clave."""
    valor = str(valor or "").strip()
    if not valor:
        return False, f"{nombre}: está vacía."
    if any(m in valor.lower() for m in _MARCADORES) or set(valor) <= set("xX*"):
        return False, f"{nombre}: parece un marcador de posición."
    if not _FORMATO.fullmatch(valor):
        return False, f"{nombre}: usa solo letras, números, _, . o -."
    return True, ""


def necesita_onboarding(ruta=None):
    """True si falta el .env o alguna clave obligatoria no es válida."""
    ruta = ruta or os.path.join(BASE, ".env")
    if not os.path.isfile(ruta):
        return True
    actuales = claves_actuales(ruta)
    return any(not validar_clave(k, actuales.get(k))[0] for k in CLAVES)


def guardar_configuracion(nombre, claves, base=None, ruta_env=None):
    """Guarda .env, perfil en datos/ y nombre en memoria.json de forma atómica."""
    base = base or BASE
    ruta_env = ruta_env or os.path.join(base, ".env")
    nombre = str(nombre or "").strip()
    if not _NOMBRE.fullmatch(nombre):
        return False, "Escribe un nombre válido (máximo 40 caracteres)."
    errores = []
    for clave in CLAVES:
        ok, mensaje = validar_clave(clave, (claves or {}).get(clave))
        if not ok:
            errores.append(mensaje)
    if errores:
        return False, " · ".join(errores)

    try:
        ruta_datos = os.path.join(base, "datos")
        os.makedirs(ruta_datos, exist_ok=True)
        if not identidad_origen.preparar_perfil_usuario(nombre, base=base):
            return False, "No se pudo guardar el perfil en datos/."
        ruta_memoria = os.path.join(base, "memoria.json")
        memoria = ps.cargar_json_seguro(ruta_memoria, {})
        if not isinstance(memoria, dict):
            memoria = {}
        memoria["nombre"] = nombre
        if not ps.guardar_json_atomico(ruta_memoria, memoria):
            return False, "No se pudo guardar el nombre en memoria.json."

        lineas = []
        if os.path.exists(ruta_env):
            with open(ruta_env, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.read().splitlines()
        finales, vistos = [], set()
        for linea in lineas:
            clave = linea.split("=", 1)[0].strip().lstrip("#")
            if clave.lower().startswith("export "):
                clave = clave[7:].strip()
            if clave in CLAVES:
                if clave not in vistos:
                    finales.append(f"{clave}={str(claves[clave]).strip()}")
                    vistos.add(clave)
                continue
            finales.append(linea)
        for clave in CLAVES:
            if clave not in vistos:
                finales.append(f"{clave}={str(claves[clave]).strip()}")
        texto = ("# Claves privadas de Kaya. Nunca compartas este archivo.\n"
                 + "\n".join(finales).strip() + "\n")
        directorio = os.path.dirname(os.path.abspath(ruta_env))
        fd, temporal = tempfile.mkstemp(prefix=".env-", dir=directorio)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(temporal, 0o600)
        except Exception:
            pass
        os.replace(temporal, ruta_env)
    except Exception as e:
        return False, f"Error guardando la configuración: {type(e).__name__}"

    cargar_env(ruta_env)
    return True, "Configuración guardada en esta laptop."


ESTILO = """
QDialog { background: #08121E; color: #E2E8F0; border: 1px solid #22D3EE;
          border-radius: 12px; font-size: 12px; }
QLabel#titulo { color: #22D3EE; font-size: 17px; font-weight: bold;
                padding: 12px 14px 4px 14px; letter-spacing: 1px; }
QLabel { color: #94A3B8; }
QLabel#estado { color: #FBBF24; }
QLineEdit { background: #0F2233; color: #E2E8F0; border: 1px solid #164E63;
            border-radius: 6px; padding: 5px 8px; min-height: 24px; }
QPushButton { background: #0F2233; color: #E2E8F0; border: 1px solid #22D3EE;
              border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #16364A; }
QPushButton:disabled { color: #64748B; border-color: #334155; }
QPushButton#guardar { background: #22D3EE; color: #06121C; font-weight: bold; }
QLabel a { color: #67E8F9; }
"""


class _Calibrador(QThread):
    """Graba 3 frases en hilo secundario; nunca toca widgets directamente."""

    progreso = Signal(str)
    terminado = Signal(bool, str)

    def __init__(self, frases):
        super().__init__()
        self.frases = tuple(frases)
        self._cancelar = threading.Event()

    def cancelar(self):
        self._cancelar.set()

    def _grabar(self, sd, segundos=3.0):
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
                self.terminado.emit(False, "Calibración incompleta; puedes repetirla después.")
                return
            guardar_banco(voz_dueno.ARCHIVO_VOZ, np.asarray(embeddings, dtype=np.float32))
            datos = estado.cargar()
            datos["verificacion_voz_activa"] = True
            estado.guardar(datos)
            self.terminado.emit(True, "Huella de voz guardada en esta laptop.")
        except Exception as e:
            self.terminado.emit(False, f"No se pudo calibrar ({type(e).__name__}). Puedes omitirlo.")


class OnboardingDialog(QDialog):
    """Modal oscuro de bienvenida: nombre, claves y calibración opcional."""

    def __init__(self, base=None, parent=None):
        super().__init__(parent)
        self.base = base or BASE
        self.ruta_env = os.path.join(self.base, ".env")
        self.resultado = False
        self.campos = {}
        self._hilo = None
        self.setWindowTitle("Kaya · Configuración inicial")
        self.setModal(True)
        self.setFixedWidth(560)
        self.setStyleSheet(ESTILO)
        raiz = QVBoxLayout(self)

        titulo = QLabel("◈  KAYA  /  BIENVENIDA")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)
        raiz.addWidget(QLabel("Configura Kaya en esta laptop. Tus claves no salen de aquí."))

        formulario = QFormLayout()
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej. Alex")
        formulario.addRow("Nombre del usuario", self.campo_nombre)
        for clave in CLAVES:
            campo = QLineEdit()
            campo.setEchoMode(QLineEdit.Password)
            campo.setPlaceholderText("Pega tu clave aquí")
            self.campos[clave] = campo
            ver = QPushButton("👁")
            ver.setCheckable(True)
            ver.setToolTip("Mostrar u ocultar")
            ver.toggled.connect(lambda _checked, c=campo, b=ver: self._alternar(c, b))
            enlace = QLabel(f'<a href="{ENLACES[clave]}">Conseguir clave ↗</a>')
            enlace.setOpenExternalLinks(False)
            enlace.linkActivated.connect(self._abrir)
            fila = QWidget()
            caja = QHBoxLayout(fila)
            caja.setContentsMargins(0, 0, 0, 0)
            caja.addWidget(campo, 1)
            caja.addWidget(ver)
            caja.addWidget(enlace)
            formulario.addRow(ETIQUETAS[clave], fila)
        raiz.addLayout(formulario)

        raiz.addWidget(QLabel("Paso opcional: graba 3 frases para que Kaya reconozca tu voz."))
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
        guardar = QPushButton("Probar y Guardar")
        guardar.setObjectName("guardar")
        guardar.clicked.connect(self._guardar)
        salir = QPushButton("Salir")
        salir.clicked.connect(self.reject)
        pie.addWidget(guardar)
        pie.addWidget(salir)
        raiz.addLayout(pie)

    def _abrir(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def _alternar(self, campo, boton):
        campo.setEchoMode(QLineEdit.Normal if boton.isChecked() else QLineEdit.Password)

    def _guardar(self):
        claves = {clave: self.campos[clave].text() for clave in CLAVES}
        ok, mensaje = guardar_configuracion(
            self.campo_nombre.text(), claves, base=self.base, ruta_env=self.ruta_env)
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


def asegurar_configuracion(base=None):
    """Muestra el onboarding solo cuando falta .env o alguna clave válida."""
    base = base or BASE
    ruta = os.path.join(base, ".env")
    if not necesita_onboarding(ruta):
        cargar_env(ruta)
        return True
    app = QApplication.instance() or QApplication([])
    del app
    dialogo = OnboardingDialog(base=base)
    dialogo.exec()
    return bool(dialogo.resultado)
