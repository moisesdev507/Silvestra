"""Blindaje de GUI, escritorio protegido y controles sensibles."""
from __future__ import annotations

import ctypes
import os
import re
import threading
from ctypes import wintypes
from typing import Any, Optional

from procesos_seguridad import (
    IdentidadProceso,
    LISTA_PROCESOS_CRITICOS,
    proceso_escritico,
    verificar_identidad_proceso,
)


PATRONES_SENSIBLES = (
    "password", "contraseña", "contrasena", "pin", "token",
    "secret", "clave", "credencial", "otp", "2fa",
)
CLASES_PROHIBIDAS = {"Progman", "WorkerW", "Shell_TrayWnd"}


class ErrorGuiSeguridad(ValueError):
    pass


def texto_sensibilizado(texto: str) -> str:
    limpio = str(texto or "")
    return "***" + str(len(limpio))


def titulo_es_sensible(titulo: str) -> bool:
    txt = str(titulo or "").lower()
    return any(p in txt for p in PATRONES_SENSIBLES)


def escritorio_de_entrada_activo() -> bool:
    if os.name != "nt":
        return True
    handle = None
    try:
        user32 = ctypes.windll.user32
        handle = user32.OpenInputDesktop(0, False, 0x00000100)
        if not handle:
            return False
        return True
    except Exception:
        return False
    finally:
        if handle:
            try:
                ctypes.windll.user32.CloseDesktop(handle)
            except Exception:
                pass


def rect_visible(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    if os.name != "nt":
        return None
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def validar_rect_relativo(
    hwnd: int,
    rect_relativo: dict,
) -> tuple[int, int]:
    rect = rect_visible(hwnd)
    if rect is None:
        raise ErrorGuiSeguridad("Ventana sin rectangulo visible.")
    try:
        x = int(rect_relativo["x"])
        y = int(rect_relativo["y"])
    except (KeyError, TypeError, ValueError):
        raise ErrorGuiSeguridad("Coordenadas relativas invalidas.")
    left, top, right, bottom = rect
    ancho = right - left
    alto = bottom - top
    if x < 0 or y < 0 or x >= ancho or y >= alto:
        raise ErrorGuiSeguridad("Coordenada relativa fuera de ventana.")
    return left + x, top + y


class ValidadorGui:
    def __init__(self, catalogo=None, supervisor=None) -> None:
        self.catalogo = catalogo
        self.supervisor = supervisor

    def identidad_hwnd(self, hwnd: int) -> tuple[Optional[IdentidadProceso], str]:
        if os.name != "nt":
            return None, "PLATAFORMA_NO_SOPORTADA"
        try:
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return None, "VENTANA_DESAPARECIDA"
            if pid.value == os.getpid() or pid.value == os.getppid():
                return None, "VENTANA_PROTEGIDA"
            if not self.supervisor:
                return None, "SUPERVISOR_NO_DISPONIBLE"
            registro = self.supervisor.obtener(pid.value)
            if registro is None:
                return None, "VENTANA_NO_AUTORIZADA"
            identidad = IdentidadProceso(
                pid.value,
                registro.identidad.creado_en_ns,
                registro.identidad.ruta_ejecutable,
            )
            ok, motivo = verificar_identidad_proceso(identidad)
            if not ok:
                return None, motivo
            nombre = os.path.basename(identidad.ruta_ejecutable).lower()
            if proceso_escritico(nombre, pid.value):
                return None, "VENTANA_PROTEGIDA"
            return identidad, "ACTIVA"
        except Exception:
            return None, "ERROR_VALIDACION_GUI"

    def validar_hwnd(self, hwnd: int, exigir_foco: bool = False) -> dict:
        if not escritorio_de_entrada_activo():
            raise ErrorGuiSeguridad("Escritorio protegido/UAC.")
        identidad, motivo = self.identidad_hwnd(hwnd)
        if identidad is None:
            raise ErrorGuiSeguridad(motivo)
        if os.name == "nt":
            if not ctypes.windll.user32.IsWindow(hwnd):
                raise ErrorGuiSeguridad("Ventana desaparecida.")
            if exigir_foco:
                foco = ctypes.windll.user32.GetForegroundWindow()
                if int(foco) != int(hwnd):
                    raise ErrorGuiSeguridad("Foco inesperado.")
        return {
            "hwnd": int(hwnd),
            "identidad": identidad.a_dict(),
            "motivo": motivo,
        }
