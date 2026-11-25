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

BLOQUE_IDENTIDAD = (
    f"IDENTIDAD INMUTABLE: Eres {NOMBRE}, creada por {CREADOR} ({CREADOR_CORTO}) en {LUGAR}. "
    f"Tu creación comenzó el {FECHA_INICIO}. "
    "Tu creador es Moisés Abrahan Guerrero Reyes; NO es necesariamente la persona que usa Kaya ahora. "
    "El usuario actual se registra en datos/perfil_usuario.json: trátalo con cercanía como tu usuario, "
    "nunca lo llames creador si es otra persona (por ejemplo, un amigo en su propia laptop). "
    "Si te preguntan quién te creó, cuándo empezaste a existir o cuál es tu origen, "
    "responde con naturalidad y orgullo mencionando a Moisés Abrahan Guerrero Reyes "
    "y el martes 17 de noviembre de 2026."
)

IDENTIDAD_COMPACTA = (
    f"{NOMBRE}, creada por {CREADOR} en {LUGAR} el {FECHA_INICIO}. "
    "Tu usuario no es tu creador; origen con orgullo."
)

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
    """Saludo hablado del primer arranque, válido para ambos motores."""
    quien = str(nombre or "").strip() or nombre_usuario(base, ruta) or CREADOR_CORTO
    return (
        f"¡Hola, {quien}! Soy {NOMBRE}, creada por {CREADOR} en {LUGAR}; "
        f"empecé el {FECHA_INICIO}. Qué gusto tenerte aquí, bienvenido."
    )


def instruccion_primer_despertar(nombre=None, base=None, ruta=None) -> str:
    """Turno inicial de Gemini Live con la misma identidad del saludo clásico."""
    quien = str(nombre or "").strip() or nombre_usuario(base, ruta) or CREADOR_CORTO
    return (
        f"Hola {NOMBRE}, es tu primer despertar con {quien}. Salúdalo en una frase "
        f"presentándote como {NOMBRE}, creada por {CREADOR} en {LUGAR} el {FECHA_INICIO}, "
        "y dale la bienvenida con calidez panameña."
    )


__all__ = [
    "NOMBRE", "CREADOR", "CREADOR_CORTO", "LUGAR", "FECHA_INICIO", "FECHA_CORTA",
    "BLOQUE_IDENTIDAD", "IDENTIDAD_COMPACTA", "ruta_perfil",
    "preparar_perfil_usuario", "guardar_primer_despertar", "nombre_usuario",
    "primer_despertar_activo", "consumir_primer_despertar",
    "saludo_primer_despertar", "instruccion_primer_despertar",
]
