"""Panel de opciones HUD de Lyris: estética oscura celeste/ámbar sobre el núcleo.

Los controles persisten en ``estado.json`` y se aplican en caliente; ningún
cambio requiere reiniciar la aplicación ni bloquea el hilo de Qt.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout)

import conversacion
import estado
import modos_sistema
import voz_estilo

MODOS = (("normal", "Normal"), ("programacion", "Código"), ("estudio", "Estudio"))


def texto_modo_escucha(activo):
    """Etiqueta del interruptor de invocación en vivo."""
    return ('Exigir decir "Lyris" — invocación habitual'
            if activo else 'Escucha directa (solo tu voz CAM++) — sin decir "Lyris"')

ESTILO_HUD = """
QDialog { background: rgba(8, 18, 30, 238); color: #E2E8F0;
          border: 1px solid #22D3EE; border-radius: 12px; font-size: 12px; }
QLabel#titulo { color: #22D3EE; font-size: 15px; font-weight: bold;
                padding: 10px 12px 6px 12px; letter-spacing: 1px; }
QLabel { color: #94A3B8; padding-left: 12px; }
QComboBox { background: #0F2233; color: #E2E8F0; border: 1px solid #22D3EE;
            border-radius: 6px; padding: 5px 8px; min-height: 22px; }
QComboBox::drop-down { border: none; }
QCheckBox, QPushButton { color: #E2E8F0; padding: 5px 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px;
                       border: 1px solid #22D3EE; background: #0F2233; }
QCheckBox::indicator:checked { background: #F59E0B; border: 1px solid #FBBF24; }
QPushButton { background: #0F2233; border: 1px solid #22D3EE; border-radius: 6px; }
QPushButton:hover { background: #16364A; }
QPushButton:checked { background: #F59E0B; color: #0B1220; border-color: #FBBF24; }
QPushButton#probar { background: #22D3EE; color: #06121C; font-weight: bold; }
QPushButton#probar:hover { background: #67E8F9; }
"""


class MenuHUD(QDialog):
    """Diálogo flotante con los ajustes principales de Lyris."""

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Lyris · Opciones HUD")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(350)
        self.setStyleSheet(ESTILO_HUD)
        datos = estado.cargar()

        raiz = QVBoxLayout(self)
        titulo = QLabel("◈  LYRIS  /  CONTROL HUD")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        raiz.addWidget(QLabel("Motor de voz principal"))
        self.combo_motor_voz = QComboBox()
        self.combo_motor_voz.addItem("Gemini Live (Natural · Achernar)", "gemini_live")
        self.combo_motor_voz.addItem("Voz Clásica (Celeste · Groq)", "clasico")
        modo_voz_act = datos.get("modo_voz_principal", "gemini_live")
        idx_mv = self.combo_motor_voz.findData(modo_voz_act)
        self.combo_motor_voz.setCurrentIndex(idx_mv if idx_mv >= 0 else 0)
        self.combo_motor_voz.currentIndexChanged.connect(self._on_motor_voz)
        raiz.addWidget(self.combo_motor_voz)

        raiz.addWidget(QLabel("Voz neuronal (Clásica)"))
        self.combo_voz = QComboBox()
        for clave, etiqueta in voz_estilo.VOCES.items():
            self.combo_voz.addItem(etiqueta, clave)
        self.combo_voz.setCurrentIndex(max(0, self.combo_voz.findData(
            voz_estilo.voz_actual())))
        self.combo_voz.currentIndexChanged.connect(self._on_voz)
        raiz.addWidget(self.combo_voz)

        raiz.addWidget(QLabel("Personalidad vocal"))
        self.combo_estilo = QComboBox()
        for clave, etiqueta in voz_estilo.ESTILOS.items():
            self.combo_estilo.addItem(etiqueta, clave)
        self.combo_estilo.setCurrentIndex(max(0, self.combo_estilo.findData(
            voz_estilo.estilo_actual())))
        self.combo_estilo.currentIndexChanged.connect(self._on_estilo)
        raiz.addWidget(self.combo_estilo)

        manos = bool(datos.get("palabra_clave", True))
        self.chk_manos = QCheckBox('Escucha manos libres ("Lyris")')
        self.chk_manos.setChecked(manos)
        self.chk_manos.stateChanged.connect(self._on_manos)
        raiz.addWidget(self.chk_manos)
        self.lbl_manos = QLabel(texto_modo_escucha(manos))
        raiz.addWidget(self.lbl_manos)

        self.btn_silenciar = QPushButton("Silenciar micrófono y voz")
        self.btn_silenciar.setCheckable(True)
        self.btn_silenciar.setChecked(bool(getattr(self.app, "voz_silenciada", False)))
        self.btn_silenciar.clicked.connect(self._on_silenciar)
        raiz.addWidget(self.btn_silenciar)

        self.chk_solo = QCheckBox("Solo voz del dueño (CAM++)")
        self.chk_solo.setChecked(bool(datos.get("modo_solo_dueno", False)))
        self.chk_solo.stateChanged.connect(self._on_solo)
        raiz.addWidget(self.chk_solo)

        raiz.addWidget(QLabel("Modo de trabajo"))
        self.combo_modo = QComboBox()
        for clave, etiqueta in MODOS:
            self.combo_modo.addItem(etiqueta, clave)
        actual = modos_sistema.obtener_modo_activo(self.app)
        indice = self.combo_modo.findData(actual)
        self.combo_modo.setCurrentIndex(indice if indice >= 0 else 0)
        self.combo_modo.currentIndexChanged.connect(self._on_modo)
        raiz.addWidget(self.combo_modo)

        pie = QHBoxLayout()
        self.btn_probar = QPushButton("▶  Probar voz")
        self.btn_probar.setObjectName("probar")
        self.btn_probar.clicked.connect(self._on_probar)
        pie.addWidget(self.btn_probar)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.hide)
        pie.addWidget(cerrar)
        raiz.addLayout(pie)

    def _on_motor_voz(self, _indice):
        modo = self.combo_motor_voz.currentData()
        datos = estado.cargar()
        datos["modo_voz_principal"] = modo
        estado.guardar(datos)
        if self.app is not None:
            cl = getattr(self.app, "coordinador_live", None)
            if cl is not None and hasattr(cl, "actualizar_modo_voz"):
                cl.actualizar_modo_voz(modo)

    def _on_voz(self, _indice):
        voz_estilo.guardar(voz=self.combo_voz.currentData())

    def _on_estilo(self, _indice):
        voz_estilo.guardar(estilo=self.combo_estilo.currentData())

    def _on_manos(self, _valor):
        activo = self.chk_manos.isChecked()
        datos = estado.cargar()
        datos["palabra_clave"] = activo
        if not activo:
            # La escucha directa solo obedece a la voz verificada por CAM++.
            datos["verificacion_voz_activa"] = True
            datos["modo_solo_dueno"] = True
        estado.guardar(datos)
        self.lbl_manos.setText(texto_modo_escucha(activo))
        detector = getattr(self.app, "palabra_clave", None)
        if detector is not None:
            detector.siempre_atenta = activo
        gestor = getattr(self.app, "invocacion", None)
        if gestor is not None:
            gestor.palabra_clave = activo
        if not activo:
            verificado = getattr(self.app, "voz_dueno", None)
            if verificado is not None:
                verificado.activa = True
                verificado.modo_solo_dueno = True

    def _on_silenciar(self, _checked=None):
        if self.app is None:
            return
        cambiar = getattr(self.app, "alternar_silencio", None)
        try:
            if callable(cambiar):
                cambiar()
            else:
                conversacion.alternar_silencio(self.app)
        except Exception:
            self.app.voz_silenciada = not getattr(self.app, "voz_silenciada", False)
        self.btn_silenciar.setChecked(bool(getattr(self.app, "voz_silenciada", False)))

    def _on_solo(self, _valor):
        activo = self.chk_solo.isChecked()
        datos = estado.cargar()
        datos["modo_solo_dueno"] = activo
        datos["verificacion_voz_activa"] = activo
        estado.guardar(datos)
        verificado = getattr(self.app, "voz_dueno", None)
        if verificado is not None:
            verificado.modo_solo_dueno = activo
            verificado.activa = activo

    def _on_modo(self, _indice):
        modo = self.combo_modo.currentData()
        datos = estado.cargar()
        datos["modo_activo"] = modo
        estado.guardar(datos)
        if self.app is not None:
            self.app.modo_activo = modo
            cara = getattr(self.app, "cara", None)
            if cara is not None:
                cara.modo_activo = modo

    def _on_probar(self):
        voz = getattr(self.app, "voz", None) if self.app is not None else None
        if voz is not None and hasattr(voz, "hablar"):
            voz.hablar("Hola, soy Lyris. Todo listo.", emocion="neutral")


def abrir(cara):
    """Abre (o enfoca) el HUD asociado a una cara sin crear QApplication."""
    app = getattr(cara, "silvestra_app", None) or getattr(cara, "_ref_app", None)
    previo = getattr(cara, "_menu_hud", None)
    if previo is not None:
        previo.show()
        previo.raise_()
        return previo
    menu = MenuHUD(app, cara if hasattr(cara, "winId") else None)
    cara._menu_hud = menu
    menu.show()
    return menu
