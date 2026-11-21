"""Inspeccion estructurada Win32/UIA de controles de interfaz."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from typing import Any, Optional

from gui_seguridad import ValidadorGui, titulo_es_sensible


def _rect_relativo(hwnd_padre: int, hwnd_control: int) -> dict:
    padre = wintypes.RECT()
    control = wintypes.RECT()
    try:
        ctypes.windll.user32.GetWindowRect(hwnd_padre, ctypes.byref(padre))
        ctypes.windll.user32.GetWindowRect(hwnd_control, ctypes.byref(control))
        return {
            "x": control.left - padre.left,
            "y": control.top - padre.top,
            "ancho": max(0, control.right - control.left),
            "alto": max(0, control.bottom - control.top),
        }
    except Exception:
        return {"x": 0, "y": 0, "ancho": 0, "alto": 0}


def _nombre_control(hwnd: int) -> str:
    try:
        longitud = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(longitud + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, longitud + 1)
        return "" if titulo_es_sensible(buffer.value) else buffer.value
    except Exception:
        return ""


def _tipo_control(hwnd: int) -> str:
    try:
        buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buffer, 256)
        clase = buffer.value.lower()
        if "button" in clase:
            return "boton"
        if "edit" in clase:
            return "campo_texto"
        if "combobox" in clase:
            return "lista"
        if "list" in clase:
            return "lista"
        if "static" in clase:
            return "etiqueta"
        return "control"
    except Exception:
        return "no_accesible"


def inspeccionar_interfaz(parametros: dict, token_cancelacion=None) -> dict:
    hwnd = int(parametros["hwnd"])
    validador = ValidadorGui(parametros["_catalogo"], parametros["_supervisor"])
    identidad = validador.validar_hwnd(hwnd, exigir_foco=False)
    elementos = []
    if os.name != "nt":
        return {"elementos": elementos, "fuente_accesibilidad": "no_accesible"}

    def enum_cb(child, lparam):
        if token_cancelacion and hasattr(token_cancelacion, "esta_cancelado"):
            if token_cancelacion.esta_cancelado():
                return False
        try:
            nombre = _nombre_control(child)
            tipo = _tipo_control(child)
            estilo = ctypes.windll.user32.GetWindowLongW(child, -16)
            visible = bool(ctypes.windll.user32.IsWindowVisible(child))
            habilitado = bool(ctypes.windll.user32.IsWindowEnabled(child))
            es_sensible = titulo_es_sensible(nombre)
            elementos.append({
                "hwnd": int(child),
                "pid": identidad["identidad"]["pid"],
                "creado_en_ns": identidad["identidad"]["creado_en_ns"],
                "ruta_control": f"{hwnd}/{int(child)}",
                "tipo": tipo,
                "nombre": "***" if es_sensible else nombre,
                "habilitado": habilitado,
                "visible": visible,
                "solo_lectura": bool(estilo & 0x0800),
                "es_sensible": es_sensible,
                "rect_relativo": _rect_relativo(hwnd, child),
                "fuente_accesibilidad": "win32",
            })
        except Exception:
            pass
        return True

    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumChildWindows(hwnd, cb(enum_cb), 0)
    if not elementos:
        elementos.append({
            "hwnd": hwnd,
            "pid": identidad["identidad"]["pid"],
            "creado_en_ns": identidad["identidad"]["creado_en_ns"],
            "ruta_control": str(hwnd),
            "tipo": "no_accesible",
            "nombre": "",
            "habilitado": True,
            "visible": True,
            "solo_lectura": True,
            "es_sensible": False,
            "rect_relativo": {"x": 0, "y": 0, "ancho": 0, "alto": 0},
            "fuente_accesibilidad": "no_accesible",
        })
    return {"elementos": elementos}


def consultar_control(parametros: dict, token_cancelacion=None) -> dict:
    inspeccion = inspeccionar_interfaz(parametros, token_cancelacion)
    ruta = str(parametros.get("ruta_control", "")).strip()
    for elemento in inspeccion["elementos"]:
        if elemento["ruta_control"] == ruta or elemento["nombre"] == ruta:
            return {"control": elemento}
    raise LookupError("Control no encontrado.")
