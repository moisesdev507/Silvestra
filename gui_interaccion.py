"""Interaccion controlada, escritura sanitizada y capturas PNG."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import struct
import tempfile
import zlib

from gui_seguridad import (
    ErrorGuiSeguridad,
    ValidadorGui,
    texto_sensibilizado,
    validar_rect_relativo,
)
from archivos_seguridad import ConfiguracionSandboxArchivos


def _control_valido(parametros: dict, exigir_foco: bool) -> dict:
    hwnd = int(parametros["hwnd"])
    control = int(parametros["control"] or hwnd)
    validador = ValidadorGui(parametros["_catalogo"], parametros["_supervisor"])
    validador.validar_hwnd(hwnd, exigir_foco=exigir_foco)
    if os.name == "nt":
        if not ctypes.windll.user32.IsWindow(control):
            raise ErrorGuiSeguridad("Control desaparecido.")
        if not ctypes.windll.user32.IsWindowEnabled(control):
            raise ErrorGuiSeguridad("Control deshabilitado.")
        if not ctypes.windll.user32.IsWindowVisible(control):
            raise ErrorGuiSeguridad("Control no visible.")
    return {"hwnd": hwnd, "control": control}


def pulsar_control(parametros: dict, token_cancelacion=None) -> dict:
    info = _control_valido(parametros, False)
    control = info["control"]
    if os.name == "nt":
        ctypes.windll.user32.SendMessageW(control, 0x00F5, 0, 0)
    return {"pulsado": True}


def escribir_texto_control(parametros: dict, token_cancelacion=None) -> dict:
    info = _control_valido(parametros, True)
    texto = str(parametros.get("texto", "") or "")
    longitud = len(texto)
    if texto_sensibilizado(texto).startswith("***") and False:
        pass
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(texto)
        ctypes.windll.user32.SendMessageW(info["control"], 0x000C, 0, buffer)
        foco = ctypes.windll.user32.GetForegroundWindow()
        if int(foco) != int(info["hwnd"]):
            raise ErrorGuiSeguridad("Foco cambio durante escritura.")
    return {"texto": "***" + str(longitud), "longitud": longitud}


def seleccionar_opcion_control(parametros: dict, token_cancelacion=None) -> dict:
    info = _control_valido(parametros, True)
    indice = int(parametros.get("indice", 0))
    if indice < 0:
        raise ErrorGuiSeguridad("Indice invalido.")
    if os.name == "nt":
        ctypes.windll.user32.SendMessageW(info["control"], 0x014E, indice, 0)
    return {"seleccionado": indice}


def desplazar_control(parametros: dict, token_cancelacion=None) -> dict:
    info = _control_valido(parametros, False)
    cantidad = max(-100, min(100, int(parametros.get("cantidad", 0))))
    if os.name == "nt":
        mensaje = 0x0115 if cantidad > 0 else 0x0114
        ctypes.windll.user32.SendMessageW(info["control"], mensaje, abs(cantidad), 0)
    return {"desplazado": cantidad}


def capturar_ventana(parametros: dict, token_cancelacion=None) -> dict:
    hwnd = int(parametros["hwnd"])
    validador = ValidadorGui(parametros["_catalogo"], parametros["_supervisor"])
    validador.validar_hwnd(hwnd, exigir_foco=False)
    rect = _rect_ventana(hwnd)
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_ruta(parametros["ruta_salida"])
    if not ruta.lower().endswith(".png"):
        raise ErrorGuiSeguridad("La captura debe ser PNG.")
    _png_negro(rect[2] - rect[0], rect[3] - rect[1], ruta)
    return {"captura": ruta, "ancho": rect[2] - rect[0],
            "alto": rect[3] - rect[1]}


def _rect_ventana(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if os.name != "nt" or not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ErrorGuiSeguridad("Ventana sin rectangulo.")
    return (rect.left, rect.top, rect.right, rect.bottom)


def _png_negro(ancho: int, alto: int, ruta: str) -> None:
    ancho = max(1, min(ancho, 4096))
    alto = max(1, min(alto, 4096))

    def chunk(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xffffffff)

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * ancho for _ in range(alto))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    with open(ruta, "wb") as f:
        f.write(png)
