"""Helpers de presentación visual: encendido del orbe, estados y despliegue HUD.

Todo se resuelve con matemática ligera sobre el reloj de dibujo ya existente
(33 ms): no crea timers nuevos, no bloquea Qt y mantiene la CPU en reposo.
La onda reutiliza el motor de ``cara_nucleo``/``cara_orbe_hibrido``.
"""
import math
import time
import unicodedata

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QPen
from PySide6.QtWidgets import QApplication, QMenu

from cara_dibujo import TAM

AMABLES = (
    "gracias", "linda", "bonita", "hermosa", "preciosa", "guapa", "te quiero",
    "te amo", "genial", "eres la mejor", "tierna", "bien hecho", "felicidades", "increible",
)
ESTADOS = ("reposo", "escuchando", "pensando", "hablando", "herramienta")
NIVELES = {"reposo": 0.22, "escuchando": 0.62, "pensando": 0.78, "hablando": 1.0, "herramienta": 0.72}
DURACION_ONDA = 1.1
_COLOR_ESCUCHA = QColor(52, 211, 153)
_COLOR_HERRAMIENTA = QColor(251, 191, 36)


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def proteger_evento(fn):
    """Blinda un override de evento de Qt: nunca propaga excepciones al bucle.

    Llama una sola vez a la función original, sin reenviar el evento, para
    evitar recursiones entre widgets (por ejemplo, doble clic -> menú -> orbe).
    """
    def envuelto(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:
            print(f"[ui] Evento {fn.__name__} ignorado de forma segura: {exc}", flush=True)
            return None
    envuelto.__name__ = fn.__name__
    envuelto.__doc__ = fn.__doc__
    return envuelto


def crear_menu(cara, al_escribir, al_conversar, al_renacer, al_descansar):
    """Construye el menú contextual fuera de cara_qt para ahorrar bytes."""
    menu = QMenu()
    menu.addAction("Opciones HUD...").triggered.connect(lambda *_: __import__("menu_hud").abrir(cara))
    menu.addAction("Escribirle").triggered.connect(lambda *_: al_escribir())
    menu.addAction("Silenciar / reanudar voz").triggered.connect(lambda *_: al_conversar())
    accion_paseo = QAction("Pasearse por la pantalla", menu)
    accion_paseo.setCheckable(True)
    accion_paseo.setChecked(True)
    accion_paseo.triggered.connect(lambda *_: cara._tocar())
    menu.addAction(accion_paseo)
    import qt_estabilidad_ui
    menu.addAction(qt_estabilidad_ui.crear_accion_segura(
        menu, "Descansar (desaparece hasta que la llames)", "¿Confirmar descanso? (3s)", al_descansar
    ))
    menu.addAction(qt_estabilidad_ui.crear_accion_segura(
        menu, "Renacer (borrar su memoria)", "¿Confirmar renacer? (3s)", al_renacer
    ))
    menu.addSeparator()
    menu.addAction("Salir").triggered.connect(lambda *_: QApplication.quit())
    cara.menu = menu
    cara.accion_paseo = accion_paseo


def preparar(cara):
    """Inicializa los escalares de animación sin tocar la API pública."""
    if getattr(cara, "_presentacion_inicio", None) is None:
        cara._presentacion_inicio = 0.0
        cara._presentacion_estado = "reposo"
        cara._presentacion_nivel = NIVELES["reposo"]
        cara._presentacion_progreso = 1.0
        cara._onda_saludo_hecha = False


def iniciar(cara, ahora=None):
    """Dispara la onda de encendido sincronizada con el saludo."""
    preparar(cara)
    cara._presentacion_inicio = ahora if ahora is not None else time.time()
    cara._presentacion_progreso = 0.0


def fijar_estado(cara, estado, ahora=None):
    """Cambia el objetivo visual con transición suave."""
    preparar(cara)
    estado = str(estado or "reposo")
    if estado not in ESTADOS:
        estado = "reposo"
    cara._presentacion_estado = estado
    ahora = ahora if ahora is not None else time.time()
    if estado in ("pensando", "herramienta"):
        cara.pensando = True
        cara.pensando_hasta = ahora + (1.1 if estado == "herramienta" else 25.0)
    elif estado in ("escuchando", "hablando", "reposo"):
        cara.pensando = False


def estado_desde(cara):
    """Estado deducido de los flags clásicos de la cara."""
    if getattr(cara, "hablando", False):
        return "hablando"
    if getattr(cara, "escuchando", False):
        return "escuchando"
    if getattr(cara, "_presentacion_estado", "reposo") == "herramienta":
        return "herramienta"
    if getattr(cara, "pensando", False):
        return "pensando"
    return "reposo"


def avanzar(cara, ahora=None):
    """Interpola nivel y onda; coste constante por frame."""
    preparar(cara)
    ahora = ahora if ahora is not None else time.time()
    estado = getattr(cara, "_presentacion_estado", "reposo")
    objetivo = NIVELES.get(estado, NIVELES["reposo"])
    actual = float(getattr(cara, "_presentacion_nivel", objetivo))
    cara._presentacion_nivel = actual + (objetivo - actual) * 0.12

    inicio = float(cara._presentacion_inicio or 0.0)
    if inicio:
        p = max(0.0, min(1.0, (ahora - inicio) / DURACION_ONDA))
        cara._presentacion_progreso = 1.0 - (1.0 - p) ** 3
        if p >= 1.0:
            cara._presentacion_inicio = 0.0
            cara._presentacion_progreso = 1.0
    return cara._presentacion_nivel


def opacidad_despliegue(progreso):
    """Curva de entrada suave para el panel HUD (0..1)."""
    p = max(0.0, min(1.0, float(progreso or 0.0)))
    return 1.0 - (1.0 - p) ** 2


def dibujar(p, cara, ahora=None):
    """Dibuja la onda de encendido y el acento de herramienta sobre el orbe."""
    ahora = ahora if ahora is not None else time.time()
    preparar(cara)
    centro = (float(getattr(cara, "width", lambda: TAM)()) or TAM) / 2.0
    progreso = float(getattr(cara, "_presentacion_progreso", 1.0))

    if progreso < 1.0:
        p.save()
        p.setBrush(Qt.NoBrush)
        for k in range(2):
            fase = min(1.0, progreso + k * 0.22)
            radio = centro * (0.30 + 0.48 * fase)
            alfa = int((1.0 - fase) ** 1.5 * 170)
            color = QColor(_COLOR_ESCUCHA)
            color.setAlpha(max(0, alfa))
            p.setPen(QPen(color, 1.6))
            p.drawEllipse(QRectF(centro - radio, centro - radio, radio * 2, radio * 2))
        p.restore()

    if getattr(cara, "_presentacion_estado", "reposo") == "herramienta":
        pulso = 0.5 + 0.5 * math.sin(ahora * 5.0)
        radio = centro * 0.40
        color = QColor(_COLOR_HERRAMIENTA)
        color.setAlpha(int(90 + 70 * pulso))
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, 1.4))
        p.drawEllipse(QRectF(centro - radio, centro - radio, radio * 2, radio * 2))
        p.restore()


__all__ = [
    "AMABLES", "ESTADOS", "normalizar", "crear_menu", "preparar", "iniciar",
    "fijar_estado", "estado_desde", "avanzar", "opacidad_despliegue", "dibujar",
]
