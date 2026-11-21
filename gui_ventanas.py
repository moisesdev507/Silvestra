"""Enumeracion y enfocado seguro de ventanas Win32."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time

from gui_seguridad import (
    CLASES_PROHIBIDAS,
    ErrorGuiSeguridad,
    ValidadorGui,
    rect_visible,
    titulo_es_sensible,
)
from procesos_seguridad import verificar_identidad_proceso


def _titulo(hwnd: int) -> str:
    try:
        longitud = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(longitud + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, longitud + 1)
        return buffer.value or ""
    except Exception:
        return ""


def _clase(hwnd: int) -> str:
    try:
        buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value or ""
    except Exception:
        return ""


def listar_ventanas(parametros: dict, token_cancelacion=None) -> dict:
    catalogo = parametros["_catalogo"]
    supervisor = parametros["_supervisor"]
    validador = ValidadorGui(catalogo, supervisor)
    limite = max(1, min(200, int(parametros.get("limite", 100))))
    if os.name != "nt":
        return {"ventanas": []}
    resultado = []
    user32 = ctypes.windll.user32

    def enum_cb(hwnd, lparam):
        if len(resultado) >= limite:
            return False
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            clase = _clase(hwnd)
            if clase in CLASES_PROHIBIDAS:
                return True
            titulo = _titulo(hwnd)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            identidad = None
            app_autorizada = False
            registro = supervisor.obtener(pid.value)
            if registro:
                identidad = registro.identidad
                ok, _ = verificar_identidad_proceso(identidad)
                app_autorizada = bool(ok)
            rect = rect_visible(hwnd)
            crea = getattr(identidad, "creado_en_ns", 0) if identidad else 0
            estilo = user32.GetWindowLongW(hwnd, -16)
            if estilo & 0x02000000:
                estado = "minimizada"
            elif estilo & 0x01000000:
                estado = "maximizada"
            else:
                estado = "normal"
            activa = int(user32.GetForegroundWindow()) == int(hwnd)
            responde = bool(_responde(hwnd))
            protegido = titulo_es_sensible(titulo) or clase in CLASES_PROHIBIDAS
            resultado.append({
                "hwnd": int(hwnd),
                "titulo": "" if protegido else titulo,
                "clase": clase,
                "pid": pid.value,
                "creado_en_ns": crea,
                "app_autorizada": app_autorizada,
                "estado": estado,
                "activa": activa,
                "responde": responde,
                "rect": rect,
                "protegida": protegido,
            })
        except Exception:
            pass
        return True

    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(cb(enum_cb), 0)
    return {"ventanas": resultado}


def _responde(hwnd: int) -> bool:
    try:
        resultado = wintypes.DWORD()
        ctypes.windll.user32.SendMessageTimeoutW(
            hwnd, 0, 0, 0, 0x0002, 150, ctypes.byref(resultado)
        )
        return True
    except Exception:
        return False


def ventana_activa(parametros: dict, token_cancelacion=None) -> dict:
    catalogo = parametros["_catalogo"]
    supervisor = parametros["_supervisor"]
    if os.name != "nt":
        return {"hwnd": None, "protegida": True}
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    validador = ValidadorGui(catalogo, supervisor)
    titulo = _titulo(hwnd)
    clase = _clase(hwnd)
    try:
        info = validador.validar_hwnd(hwnd, exigir_foco=False)
        protegida = titulo_es_sensible(titulo) or clase in CLASES_PROHIBIDAS
        return {
            "hwnd": hwnd,
            "titulo": "" if protegida else titulo,
            "clase": clase,
            "identidad": info["identidad"],
            "app_autorizada": True,
            "protegida": protegida,
            "rect": rect_visible(hwnd),
        }
    except ErrorGuiSeguridad as exc:
        return {
            "hwnd": hwnd,
            "titulo": "" if titulo_es_sensible(titulo) else titulo,
            "clase": clase,
            "app_autorizada": False,
            "protegida": True,
            "motivo": str(exc),
        }


def enfocar_ventana(parametros: dict, token_cancelacion=None) -> dict:
    hwnd = int(parametros["hwnd"])
    validador = ValidadorGui(parametros["_catalogo"], parametros["_supervisor"])
    validador.validar_hwnd(hwnd, exigir_foco=False)
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    foco = int(user32.GetForegroundWindow())
    if foco != hwnd:
        raise ErrorGuiSeguridad("El foco no correspondio al hwnd esperado.")
    return {"hwnd": hwnd, "enfocada": True}
