"""Identidad raíz inmutable de Kaya y primer despertar por perfil de usuario."""
from __future__ import annotations

import os
import threading

import persistencia_segura as ps
import rutas_app

NOMBRE = "Kaya"
CREADOR = "Moisés Abrahan Guerrero Reyes"
CREADOR_CORTO = "Moisés"
LUGAR = "Panamá"
FECHA_INICIO = "martes 17 de noviembre de 2026"
FECHA_CORTA = "17 de noviembre de 2026"
ARCHIVO_PERFIL = "perfil_usuario.json"
CLAVE_DESPERTAR = "primer_despertar"
VOZ_KAYA_LIVE = "Aoede"
VOZ_KAYA_CLASICA = "aura-2-gloria-es"
USUARIO_SIN_NOMBRE = "tu usuario"

DATO_ORIGEN = (
    " [Origen, SOLO si te preguntan]: creada por "
    f"{CREADOR} el {FECHA_INICIO} en {LUGAR}. Nunca lo saques en saludos ni charla normal."
)

REGLA_ORIGEN = (
    " Si preguntan quién te creó o tu origen, di ese dato con naturalidad; "
    "si no, jamás lo menciones."
)


def prompt_identidad(nombre_usuario: str = "") -> str:
    """Identidad de Kaya; el origen queda disponible solo si se pregunta por él."""
    quien = str(nombre_usuario or "").strip() or USUARIO_SIN_NOMBRE
    return (
        f"Tu nombre es {NOMBRE}. Eres una asistente de inteligencia artificial. "
        f"El usuario con el que estás hablando actualmente se llama {quien}. "
        f"NUNCA digas que eres {quien} ni que eres tu creadora; "
        f"tú eres {NOMBRE} y te diriges a {quien}." + DATO_ORIGEN
    )


def bloque_identidad(nombre_usuario: str = "") -> str:
    """Identidad raíz más la distinción entre creador y usuario actual."""
    return (
        prompt_identidad(nombre_usuario)
        + " El usuario actual se registra en datos/perfil_usuario.json: trátalo con cercanía "
        "como tu usuario, nunca lo llames creador si es otra persona (por ejemplo, un amigo "
        "en su propia laptop)." + REGLA_ORIGEN
    )


BLOQUE_IDENTIDAD = bloque_identidad()
IDENTIDAD_COMPACTA = prompt_identidad()

_LOCK = threading.RLock()


def ruta_perfil(base=None, ruta=None) -> str:
    """Resuelve la ruta del perfil del usuario en desarrollo o en el ejecutable."""
    if ruta:
        return os.path.abspath(str(ruta))
    base = base or rutas_app.dir_usuario()
    return os.path.join(os.path.abspath(str(base)), "datos", ARCHIVO_PERFIL)


def _cargar(ruta: str) -> dict:
    datos = ps.cargar_json_seguro(ruta, {})
    return datos if isinstance(datos, dict) else {}


def preparar_perfil_usuario(nombre, base=None, ruta=None) -> bool:
    """Crea o actualiza el perfil; marca el despertar solo cuando el perfil es nuevo."""
    destino = ruta_perfil(base, ruta)
    with _LOCK:
        es_nuevo = not os.path.isfile(destino)
        datos = {} if es_nuevo else _cargar(destino)
        nombre_limpio = str(nombre or "").strip()
        if nombre_limpio:
            datos["nombre"] = nombre_limpio
        elif "nombre" not in datos:
            datos["nombre"] = ""
        if es_nuevo:
            datos[CLAVE_DESPERTAR] = True
        elif CLAVE_DESPERTAR not in datos:
            datos[CLAVE_DESPERTAR] = False
        return ps.guardar_json_atomico(destino, datos)


def guardar_primer_despertar(activo: bool = True, base=None, ruta=None) -> bool:
    """Fija el flag de primer despertar de forma atómica."""
    destino = ruta_perfil(base, ruta)
    with _LOCK:
        datos = _cargar(destino)
        datos[CLAVE_DESPERTAR] = bool(activo)
        return ps.guardar_json_atomico(destino, datos)


def nombre_usuario(base=None, ruta=None) -> str:
    """Devuelve el nombre del usuario actual, nunca el del creador por defecto."""
    with _LOCK:
        return str(_cargar(ruta_perfil(base, ruta)).get("nombre") or "").strip()


def perfil_con_usuario(base=None, ruta=None) -> bool:
    """True si ya hay un perfil con nombre; nunca lo tratamos como instalación nueva."""
    with _LOCK:
        return bool(_cargar(ruta_perfil(base, ruta)).get("nombre"))


def desactivar_primer_despertar_si_existe(base=None, ruta=None) -> bool:
    """Neutraliza el flag en un perfil existente sin tocar su nombre ni otros datos."""
    destino = ruta_perfil(base, ruta)
    with _LOCK:
        datos = _cargar(destino)
        if not datos.get("nombre") or not datos.get(CLAVE_DESPERTAR, False):
            return False
        datos[CLAVE_DESPERTAR] = False
        return ps.guardar_json_atomico(destino, datos)


def primer_despertar_activo(base=None, ruta=None) -> bool:
    """Consulta sin consumir si el perfil aún debe despertar por primera vez."""
    with _LOCK:
        return bool(_cargar(ruta_perfil(base, ruta)).get(CLAVE_DESPERTAR, False))


def consumir_primer_despertar(base=None, ruta=None) -> bool:
    """Consume el flag una sola vez y devuelve True solo en esa ocasión."""
    destino = ruta_perfil(base, ruta)
    with _LOCK:
        datos = _cargar(destino)
        if not datos.get(CLAVE_DESPERTAR, False):
            return False
        datos[CLAVE_DESPERTAR] = False
        ps.guardar_json_atomico(destino, datos)
        return True


def saludo_primer_despertar(nombre=None, base=None, ruta=None) -> str:
    """Saludo hablado del primer arranque, sin creador ni origen espontáneos."""
    quien = str(nombre or "").strip() or nombre_usuario(base, ruta) or USUARIO_SIN_NOMBRE
    return f"¡Hola, {quien}! Soy {NOMBRE}. Qué gusto tenerte aquí, bienvenido."


def instruccion_primer_despertar(nombre=None, base=None, ruta=None) -> str:
    """Turno inicial de Gemini Live con la misma identidad del saludo clásico."""
    quien = str(nombre or "").strip() or nombre_usuario(base, ruta) or USUARIO_SIN_NOMBRE
    return (
        f"Hola {NOMBRE}, es tu primer despertar con {quien}. Salúdalo en una frase "
        f"presentándote solo como {NOMBRE}, sin decir nunca que eres {quien} ni tu creadora, "
        "y dale la bienvenida con calidez panameña. No menciones quién te creó, tu fecha "
        "de inicio ni tu origen salvo que te lo pregunte explícitamente."
    )


__all__ = [
    "NOMBRE", "CREADOR", "CREADOR_CORTO", "LUGAR", "FECHA_INICIO", "FECHA_CORTA",
    "VOZ_KAYA_LIVE", "VOZ_KAYA_CLASICA", "USUARIO_SIN_NOMBRE",
    "prompt_identidad", "bloque_identidad",
    "BLOQUE_IDENTIDAD", "IDENTIDAD_COMPACTA", "ruta_perfil",
    "preparar_perfil_usuario", "guardar_primer_despertar", "nombre_usuario",
    "perfil_con_usuario", "desactivar_primer_despertar_si_existe",
    "primer_despertar_activo", "consumir_primer_despertar",
    "saludo_primer_despertar", "instruccion_primer_despertar",
]
