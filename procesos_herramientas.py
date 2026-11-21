"""Registro de herramientas y politicas base para procesos Windows."""
from __future__ import annotations

import permisos_modelo as pm
from ejecucion_modelo import ContratoHerramienta
from procesos_seguridad import CatalogoAppsAutorizadas
from procesos_operaciones import (
    SupervisorProcesosSilvestra,
    consultar_procesos,
    buscar_proceso,
    estado_aplicacion,
    iniciar_aplicacion,
    cerrar_aplicacion,
)


ESQUEMAS = {
    "consultar_procesos": {
        "requeridos": [],
        "opcionales": ["limite", "nombre", "solo_silvestra"],
        "tipos": {"limite": "int", "nombre": "str", "solo_silvestra": "bool"},
    },
    "buscar_proceso": {
        "requeridos": [],
        "opcionales": ["nombre", "id_app", "limite"],
        "tipos": {"nombre": "str", "id_app": "str", "limite": "int"},
    },
    "estado_aplicacion": {
        "requeridos": [],
        "opcionales": ["id_app", "pid", "creado_en_ns", "ruta_ejecutable"],
        "tipos": {"id_app": "str", "pid": "int", "creado_en_ns": "int",
                  "ruta_ejecutable": "str"},
    },
    "iniciar_aplicacion": {
        "requeridos": ["id_app"],
        "opcionales": ["argumentos"],
        "tipos": {"id_app": "str", "argumentos": "list"},
    },
    "cerrar_aplicacion": {
        "requeridos": ["id_app", "pid", "creado_en_ns", "ruta_ejecutable"],
        "opcionales": ["espera_seg"],
        "tipos": {"id_app": "str", "pid": "int", "creado_en_ns": "int",
                  "ruta_ejecutable": "str", "espera_seg": "number"},
    },
}


def configurar(
    registro,
    motor_permisos,
    catalogo: CatalogoAppsAutorizadas,
    supervisor: SupervisorProcesosSilvestra,
    sobrescribir: bool = False,
) -> list[str]:
    handlers = {
        "consultar_procesos": consultar_procesos,
        "buscar_proceso": buscar_proceso,
        "estado_aplicacion": estado_aplicacion,
        "iniciar_aplicacion": iniciar_aplicacion,
        "cerrar_aplicacion": cerrar_aplicacion,
    }
    niveles = {
        "consultar_procesos": ("consulta", "bajo", False),
        "buscar_proceso": ("consulta", "bajo", False),
        "estado_aplicacion": ("consulta", "bajo", False),
        "iniciar_aplicacion": ("sistema", "medio", False),
        "cerrar_aplicacion": ("sistema", "alto", True),
    }
    registrados = []
    for nombre, handler in handlers.items():
        categoria, riesgo, reforzada = niveles[nombre]

        def handler_sandbox(parametros, token=None, _handler=handler):
            parametros = dict(parametros)
            parametros["_catalogo"] = catalogo
            parametros["_supervisor"] = supervisor
            if token is not None:
                return _handler(parametros, token)
            return _handler(parametros)

        contrato = ContratoHerramienta(
            nombre=nombre,
            categoria=categoria,
            descripcion="Operacion segura de aplicaciones y procesos Windows.",
            parametros_esquema=ESQUEMAS[nombre],
            handler=handler_sandbox,
            nivel_riesgo=riesgo,
            requiere_confirmacion=riesgo != "bajo",
            permisos_requeridos=("usuario.confirmar",),
            cancelable=True,
            asincrona=True,
            timeout_seg=15.0,
            habilitada=True,
        )
        registro.registrar(contrato, sobrescribir=sobrescribir)

        nivel = pm.NIVEL_SOLO_LECTURA if riesgo == "bajo" else (
            pm.NIVEL_SENSIBLE_REFORZADA if reforzada
            else pm.NIVEL_REQUIERE_CONFIRMACION
        )
        politica = pm.PoliticaOperacion(
            herramienta=nombre,
            nivel_autorizacion=nivel,
            riesgo_maximo_permitido=riesgo,
            permisos_requeridos=("usuario.confirmar",),
            ttl_seg_por_defecto=60.0,
            requiere_doble_confirmacion=reforzada,
            habilitada=True,
        )
        motor_permisos.registrar_politica(politica, actor="sistema_inicio")
        registrados.append(nombre)
    return registrados


def registrar_politica_forzada(motor_permisos) -> tuple[bool, str]:
    politica = pm.PoliticaOperacion(
        herramienta="terminar_proceso_forzado",
        nivel_autorizacion=pm.NIVEL_PROHIBIDA,
        riesgo_maximo_permitido="critico",
        permisos_requeridos=(),
        ttl_seg_por_defecto=1.0,
        requiere_doble_confirmacion=False,
        habilitada=True,
    )
    return motor_permisos.registrar_politica(politica, actor="sistema_inicio")
