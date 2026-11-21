"""Registro de herramientas GUI y politicas centralizadas."""
from __future__ import annotations

import permisos_modelo as pm
from ejecucion_modelo import ContratoHerramienta
from gui_ventanas import listar_ventanas, ventana_activa, enfocar_ventana
from gui_inspeccion import inspeccionar_interfaz, consultar_control
from gui_interaccion import (
    pulsar_control,
    escribir_texto_control,
    seleccionar_opcion_control,
    desplazar_control,
    capturar_ventana,
)
from gui_secuencias import ejecutar_secuencia_gui


ESQUEMAS = {
    "listar_ventanas": {"requeridos": [], "opcionales": ["limite"],
                        "tipos": {"limite": "int"}},
    "ventana_activa": {"requeridos": [], "opcionales": [], "tipos": {}},
    "enfocar_ventana": {"requeridos": ["hwnd"], "opcionales": [],
                        "tipos": {"hwnd": "int"}},
    "inspeccionar_interfaz": {"requeridos": ["hwnd"], "opcionales": [],
                              "tipos": {"hwnd": "int"}},
    "consultar_control": {"requeridos": ["hwnd", "ruta_control"], "opcionales": [],
                          "tipos": {"hwnd": "int", "ruta_control": "str"}},
    "pulsar_control": {"requeridos": ["hwnd", "control"], "opcionales": [],
                       "tipos": {"hwnd": "int", "control": "int"}},
    "escribir_texto_control": {"requeridos": ["hwnd", "control", "texto"],
                               "opcionales": [],
                               "tipos": {"hwnd": "int", "control": "int", "texto": "str"}},
    "seleccionar_opcion_control": {"requeridos": ["hwnd", "control", "indice"],
                                   "opcionales": [],
                                   "tipos": {"hwnd": "int", "control": "int", "indice": "int"}},
    "desplazar_control": {"requeridos": ["hwnd", "control", "cantidad"],
                          "opcionales": [],
                          "tipos": {"hwnd": "int", "control": "int", "cantidad": "int"}},
    "capturar_ventana": {"requeridos": ["hwnd", "ruta_salida"], "opcionales": [],
                         "tipos": {"hwnd": "int", "ruta_salida": "str"}},
    "ejecutar_secuencia_gui": {"requeridos": ["hwnd", "pasos"], "opcionales": [],
                               "tipos": {"hwnd": "int", "pasos": "list"}},
}


def configurar_gui(
    registro,
    motor_permisos,
    catalogo,
    supervisor,
    sandbox,
    sobrescribir: bool = False,
) -> list[str]:
    solo = {
        "listar_ventanas": listar_ventanas,
        "ventana_activa": ventana_activa,
        "inspeccionar_interfaz": inspeccionar_interfaz,
        "consultar_control": consultar_control,
    }
    confirmacion = {
        "enfocar_ventana": enfocar_ventana,
        "capturar_ventana": capturar_ventana,
        "pulsar_control": pulsar_control,
        "seleccionar_opcion_control": seleccionar_opcion_control,
        "desplazar_control": desplazar_control,
    }
    reforzada = {
        "escribir_texto_control": escribir_texto_control,
        "ejecutar_secuencia_gui": ejecutar_secuencia_gui,
    }
    registrados = []
    for nombre, handler in {**solo, **confirmacion, **reforzada}.items():
        def gui_handler(parametros, token=None, _handler=handler):
            parametros = dict(parametros)
            parametros["_catalogo"] = catalogo
            parametros["_supervisor"] = supervisor
            parametros["_sandbox"] = sandbox
            return _handler(parametros, token) if token is not None else _handler(parametros)

        riesgo = "bajo" if nombre in solo else (
            "alto" if nombre in reforzada else "medio"
        )
        contrato = ContratoHerramienta(
            nombre=nombre,
            categoria="gui",
            descripcion="Interaccion GUI segura y validada.",
            parametros_esquema=ESQUEMAS[nombre],
            handler=gui_handler,
            nivel_riesgo=riesgo,
            requiere_confirmacion=nombre not in solo,
            permisos_requeridos=("usuario.confirmar",) if nombre not in solo else (),
            cancelable=True,
            asincrona=True,
            timeout_seg=15.0,
            habilitada=True,
        )
        registro.registrar(contrato, sobrescribir=sobrescribir)
        nivel = (
            pm.NIVEL_SOLO_LECTURA if nombre in solo else
            pm.NIVEL_SENSIBLE_REFORZADA if nombre in reforzada else
            pm.NIVEL_REQUIERE_CONFIRMACION
        )
        politica = pm.PoliticaOperacion(
            herramienta=nombre,
            nivel_autorizacion=nivel,
            riesgo_maximo_permitido=riesgo,
            permisos_requeridos=("usuario.confirmar",) if nivel != pm.NIVEL_SOLO_LECTURA else (),
            ttl_seg_por_defecto=60.0,
            requiere_doble_confirmacion=(nombre in reforzada),
            habilitada=True,
        )
        motor_permisos.registrar_politica(politica, actor="sistema_inicio")
        registrados.append(nombre)
    for prohibida in ("clic_coordenadas_arbitrarias", "interaccion_ventana_protegida"):
        politica = pm.PoliticaOperacion(
            herramienta=prohibida,
            nivel_autorizacion=pm.NIVEL_PROHIBIDA,
            riesgo_maximo_permitido="critico",
            permisos_requeridos=(),
            ttl_seg_por_defecto=1.0,
            requiere_doble_confirmacion=False,
            habilitada=True,
        )
        motor_permisos.registrar_politica(politica, actor="sistema_inicio")
    return registrados
