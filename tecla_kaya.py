"""Encendido de Kaya por tecla global (Windows) y local en el orbe.

Usa QAbstractNativeEventFilter + RegisterHotKey de user32, sin dependencias
externas. El filtro solo encola; las acciones Qt se ejecutan en el bucle.
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtWidgets import QApplication

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x0004
WM_HOTKEY = 0x0312
ID_KAYA = 0x4B4A
POR_DEFECTO = "Ctrl + Alt + K"

_MAPA = {
    "Ctrl + Alt + K": (MOD_CONTROL | MOD_ALT, 0x4B),
    "Alt + Espacio": (MOD_ALT, 0x20),
    "F9": (0, 0x78),
    "F10": (0, 0x79),
}

_FILTRO = None
_APP = None


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


def tecla_desde_env():
    """Devuelve una tecla configurada válida, con seguridad ante valores raros."""
    actual = str(os.environ.get("KAYA_TECLA", "") or "").strip()
    if actual in _MAPA:
        return actual
    try:
        import onboarding_qt
        if actual in onboarding_qt.TECLAS:
            return actual
        return onboarding_qt.TECLAS[0]
    except Exception:
        return POR_DEFECTO


def modificadores_vk(tecla):
    """Par (modificadores, código virtual) para RegisterHotKey."""
    return _MAPA.get(str(tecla or "").strip())


def accionar(app=None):
    """Encola la pulsación; nunca toca widgets desde un hilo nativo."""
    objetivo = app or _APP
    if objetivo is None:
        return False
    cola = getattr(objetivo, "cola", None)
    if cola is None:
        return False
    try:
        cola.put(("kaya_tecla", ""))
        return True
    except Exception:
        return False


def pulsacion_local(cara, evento):
    """Espacio/Enter con el orbe enfocado enciende a Kaya."""
    if evento is None or getattr(evento, "key", lambda: None)() not in (
            Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
        return False
    app = (getattr(cara, "silvestra_app", None)
           or getattr(cara, "_ref_app", None) or _APP)
    accionar(app)
    try:
        evento.accept()
    except Exception:
        pass
    return True


def _despertar_live(app):
    """Reposo Azul: mismo patrón seguro que cerebro_sistema2, sin tocar Live."""
    coordinador = getattr(app, "coordinador_live", None)
    sesion = getattr(coordinador, "sesion_live", None) if coordinador else None
    puente = getattr(sesion, "_puente_webrtc", None)
    if puente is not None and getattr(puente, "dormida", False):
        try:
            puente.dormida = False
            puente.despertar()
        except Exception:
            pass
    return coordinador, sesion


def atender(app=None):
    """Se ejecuta en el hilo de Qt: muestra el orbe y enciende/despierta Live."""
    objetivo = app or _APP
    if objetivo is None:
        return False
    cara = getattr(objetivo, "cara", None)
    if cara is not None:
        try:
            if callable(getattr(cara, "mostrar", None)):
                cara.mostrar()
            else:
                cara.show()
            cara.raise_()
            cara.activateWindow()
            cara.setFocus()
        except Exception:
            pass
    if getattr(objetivo, "descansando", False):
        try:
            objetivo.despertar()
        except Exception:
            pass
    coordinador, sesion = _despertar_live(objetivo)
    if coordinador is not None:
        try:
            if coordinador.esta_live_activo():
                import live_estado
                live_estado.reanudar_escucha(sesion)
            elif getattr(coordinador, "modo_live_habilitado", False):
                coordinador.intentar_activar_live("Kaya, estoy aquí.")
                return True
        except Exception:
            pass
    try:
        objetivo.alternar_conversacion("tecla")
    except Exception:
        pass
    return True


class _FiltroTecla(QAbstractNativeEventFilter):
    """Filtro nativo mínimo: solo detecta WM_HOTKEY y encola la acción."""

    def __init__(self, app, hwnd):
        super().__init__()
        self._app = app
        self._hwnd = hwnd
        self._registrada = False

    def registrar(self):
        self.desregistrar()
        if sys.platform != "win32" or not self._hwnd:
            return False
        datos = modificadores_vk(tecla_desde_env())
        if datos is None:
            return False
        mods, vk = datos
        try:
            user32 = ctypes.windll.user32
            user32.RegisterHotKey.argtypes = [wintypes.HWND, wintypes.INT,
                                              wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            self._registrada = bool(user32.RegisterHotKey(
                self._hwnd, ID_KAYA, mods | MOD_NOREPEAT, vk))
        except Exception:
            self._registrada = False
        return self._registrada

    def desregistrar(self):
        if self._registrada:
            try:
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, ID_KAYA)
            except Exception:
                pass
        self._registrada = False

    def nativeEventFilter(self, eventType, message):
        if not self._registrada:
            return False
        try:
            try:
                msg = ctypes.cast(message, ctypes.POINTER(_MSG)).contents
            except TypeError:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY and int(msg.wParam) == ID_KAYA:
                accionar(self._app)
                return True, 1
        except Exception:
            pass
        return False


def instalar(app=None):
    """Instala el filtro sobre el HWND del orbe y registra la hotkey."""
    global _APP, _FILTRO
    _APP = app or _APP
    aplicacion = QApplication.instance()
    if aplicacion is None or _FILTRO is not None or sys.platform != "win32":
        return False
    cara = getattr(_APP, "cara", None)
    win_id = getattr(cara, "winId", None)
    try:
        hwnd = int(win_id()) if callable(win_id) else 0
    except Exception:
        hwnd = 0
    if not hwnd:
        return False
    _FILTRO = _FiltroTecla(_APP, hwnd)
    aplicacion.installNativeEventFilter(_FILTRO)
    return _FILTRO.registrar()


def recargar(app=None):
    """Vuelve a registrar la hotkey tras cambiar la configuración."""
    global _APP
    _APP = app or _APP
    if _FILTRO is not None:
        return _FILTRO.registrar()
    return instalar(_APP)


def desinstalar():
    """Quita el filtro y libera la combinación global."""
    global _FILTRO
    if _FILTRO is None:
        return
    aplicacion = QApplication.instance()
    if aplicacion is not None:
        try:
            aplicacion.removeNativeEventFilter(_FILTRO)
        except Exception:
            pass
    _FILTRO.desregistrar()
    _FILTRO = None
