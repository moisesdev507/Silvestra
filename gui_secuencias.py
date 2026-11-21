"""Ejecucion supervisada y cancelable de secuencias GUI."""
from __future__ import annotations

import time
from typing import Any

from gui_seguridad import ErrorGuiSeguridad, ValidadorGui
from gui_interaccion import (
    pulsar_control,
    escribir_texto_control,
    seleccionar_opcion_control,
    desplazar_control,
)


def ejecutar_secuencia_gui(parametros: dict, token_cancelacion=None) -> dict:
    hwnd = int(parametros["hwnd"])
    pasos = parametros.get("pasos")
    if not isinstance(pasos, list) or not pasos:
        raise ErrorGuiSeguridad("Secuencia vacia.")
    validador = ValidadorGui(parametros["_catalogo"], parametros["_supervisor"])
    ejecutados = []
    for indice, paso in enumerate(pasos):
        if token_cancelacion and hasattr(token_cancelacion, "esta_cancelado"):
            if token_cancelacion.esta_cancelado():
                return {"completada": False, "cancelada": True,
                        "pasos": ejecutados}
        if not isinstance(paso, dict):
            raise ErrorGuiSeguridad("Paso GUI invalido.")
        validador.validar_hwnd(hwnd, exigir_foco=True)
        accion = str(paso.get("accion", "")).strip().lower()
        subparam = dict(paso)
        subparam["_catalogo"] = parametros["_catalogo"]
        subparam["_supervisor"] = parametros["_supervisor"]
        subparam["hwnd"] = hwnd
        subparam["control"] = paso.get("control", hwnd)
        if accion == "pulsar_control":
            pulsar_control(subparam, token_cancelacion)
        elif accion == "escribir_texto_control":
            texto = str(paso.get("texto", ""))
            resultado = escribir_texto_control(subparam, token_cancelacion)
            subparam["texto"] = resultado["texto"]
        elif accion == "seleccionar_opcion_control":
            seleccionar_opcion_control(subparam, token_cancelacion)
        elif accion == "desplazar_control":
            desplazar_control(subparam, token_cancelacion)
        else:
            raise ErrorGuiSeguridad("Accion GUI no permitida.")
        ejecutados.append({"indice": indice, "accion": accion})
        time.sleep(max(0.0, min(1.0, float(paso.get("espera_seg", 0.05)))))
    return {"completada": True, "pasos": ejecutados}
