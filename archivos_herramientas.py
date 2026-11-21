"""Registro de herramientas de archivos y politicas base."""
from __future__ import annotations

from typing import Iterable, Optional

import permisos_modelo as pm
from ejecucion_modelo import ContratoHerramienta
from archivos_seguridad import ConfiguracionSandboxArchivos
import archivos_operaciones as operaciones


ESQUEMAS = {
    "listar_directorio": {"requeridos": ["ruta"], "opcionales": [],
                         "tipos": {"ruta": "str"}},
    "metadatos_archivo": {"requeridos": ["ruta"], "opcionales": [],
                          "tipos": {"ruta": "str"}},
    "buscar_archivos": {"requeridos": ["ruta"], "opcionales": ["patron", "extension", "profundidad"],
                        "tipos": {"ruta": "str", "patron": "str", "extension": "str", "profundidad": "int"}},
    "leer_archivo": {"requeridos": ["ruta"], "opcionales": [],
                     "tipos": {"ruta": "str"}},
    "crear_archivo": {"requeridos": ["ruta"], "opcionales": ["contenido"],
                      "tipos": {"ruta": "str", "contenido": "str"}},
    "crear_directorio": {"requeridos": ["ruta"], "opcionales": ["parents"],
                         "tipos": {"ruta": "str", "parents": "bool"}},
    "modificar_archivo": {"requeridos": ["ruta"], "opcionales":
                          ["contenido", "reemplazar", "nuevo", "sha256_esperado", "mtime_ns_esperado"],
                          "tipos": {"ruta": "str", "contenido": "str", "reemplazar": "str",
                                    "nuevo": "str", "sha256_esperado": "str", "mtime_ns_esperado": "int"}},
    "copiar_elemento": {"requeridos": ["origen", "destino"], "opcionales": ["sobrescribir"],
                        "tipos": {"origen": "str", "destino": "str", "sobrescribir": "bool"}},
    "mover_elemento": {"requeridos": ["origen", "destino"], "opcionales": [],
                       "tipos": {"origen": "str", "destino": "str"}},
    "renombrar_elemento": {"requeridos": ["origen", "nuevo_nombre"], "opcionales": [],
                           "tipos": {"origen": "str", "nuevo_nombre": "str"}},
}


def configurar(
    registro,
    motor_permisos,
    sandbox: ConfiguracionSandboxArchivos,
    sobrescribir: bool = False,
) -> list[str]:
    """Registra contratos con handlers puros y no modifica acciones heredadas."""
    handlers = {
        "listar_directorio": operaciones.listar_directorio,
        "metadatos_archivo": operaciones.metadatos_archivo,
        "buscar_archivos": operaciones.buscar_archivos,
        "leer_archivo": operaciones.leer_archivo,
        "crear_archivo": operaciones.crear_archivo,
        "crear_directorio": operaciones.crear_directorio,
        "modificar_archivo": operaciones.modificar_archivo,
        "copiar_elemento": operaciones.copiar_elemento,
        "mover_elemento": operaciones.mover_elemento,
        "renombrar_elemento": operaciones.renombrar_elemento,
    }
    niveles = {
        "listar_directorio": ("consulta", "bajo", False),
        "metadatos_archivo": ("consulta", "bajo", False),
        "buscar_archivos": ("consulta", "bajo", False),
        "leer_archivo": ("consulta", "bajo", False),
        "crear_archivo": ("archivo", "medio", False),
        "crear_directorio": ("archivo", "medio", False),
        "copiar_elemento": ("archivo", "medio", False),
        "renombrar_elemento": ("archivo", "medio", False),
        "modificar_archivo": ("archivo", "alto", True),
        "mover_elemento": ("archivo", "alto", True),
    }
    registrados = []
    for nombre, handler in handlers.items():
        categoria, riesgo, reforzada = niveles[nombre]
        def handler_sandbox(parametros, token=None, _handler=handler):
            parametros = dict(parametros)
            parametros["_sandbox"] = sandbox
            if token is not None:
                return _handler(parametros, token)
            return _handler(parametros)
        contrato = ContratoHerramienta(
            nombre=nombre,
            categoria=categoria,
            descripcion="Operacion segura de archivos dentro del sandbox.",
            parametros_esquema=ESQUEMAS[nombre],
            handler=handler_sandbox,
            nivel_riesgo=riesgo,
            requiere_confirmacion=(riesgo != "bajo"),
            permisos_requeridos=("usuario.confirmar",),
            cancelable=True,
            asincrona=True,
            timeout_seg=15.0,
            habilitada=True,
        )
        if registro.existe(nombre) and not sobrescribir:
            pass
        else:
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
