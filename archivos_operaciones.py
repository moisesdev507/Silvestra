"""Handlers puros de exploracion y organizacion dentro del sandbox."""
from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from archivos_seguridad import (
    RESPALDOS_DIR,
    ConfiguracionSandboxArchivos,
    ErrorRutaArchivos,
)


def _cancelado(token: Any) -> bool:
    return bool(token and hasattr(token, "esta_cancelado") and token.esta_cancelado())


def _fecha(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).astimezone().isoformat()


def listar_directorio(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_existente(parametros["ruta"])
    if not os.path.isdir(ruta):
        raise ErrorRutaArchivos("La ruta no es un directorio.")
    entradas = []
    with os.scandir(ruta) as listado:
        for entrada in listado:
            if _cancelado(token_cancelacion):
                return {"cancelado": True, "entradas": entradas}
            if entrada.name == RESPALDOS_DIR:
                continue
            try:
                sandbox._bloquear_reparse(entrada.path)
                tipo = "directorio" if entrada.is_dir(follow_symlinks=False) else "archivo"
                st = entrada.stat(follow_symlinks=False)
                entradas.append({
                    "nombre": entrada.name, "tipo": tipo,
                    "tamano": st.st_size if tipo == "archivo" else 0,
                    "modificado": _fecha(st.st_mtime),
                })
            except ErrorRutaArchivos:
                continue
    return {"entradas": sorted(entradas, key=lambda e: e["nombre"].lower())}


def metadatos_archivo(parametros: dict, token_cancelacion=None) -> dict:
    if _cancelado(token_cancelacion):
        return {"cancelado": True}
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_existente(parametros["ruta"])
    if not os.path.isfile(ruta):
        raise ErrorRutaArchivos("Se esperaba un archivo.")
    st = os.stat(ruta)
    resultado = {
        "tipo": "archivo", "tamano": st.st_size,
        "creado": _fecha(st.st_ctime), "modificado": _fecha(st.st_mtime),
        "extension": os.path.splitext(ruta)[1].lower(),
    }
    if st.st_size <= sandbox.tamanio_maximo_lectura:
        resultado.update(sandbox.huella_estado(ruta))
    return resultado


def buscar_archivos(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    raiz = sandbox.validar_existente(parametros["ruta"])
    if not os.path.isdir(raiz):
        raise ErrorRutaArchivos("La ruta no es un directorio.")
    patron = str(parametros.get("patron", "*")).lower()
    extension = str(parametros.get("extension", "")).lower()
    profundidad = max(0, int(parametros.get("profundidad", 3)))
    encontrados = []
    raiz_abs = os.path.abspath(raiz)

    for base, dirs, archivos in os.walk(raiz_abs, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if d != RESPALDOS_DIR]
        rel = os.path.relpath(base, raiz_abs)
        nivel = 0 if rel == "." else len(Path(rel).parts)
        if nivel > profundidad:
            dirs[:] = []
            continue
        for nombre in archivos:
            if _cancelado(token_cancelacion):
                return {"cancelado": True, "archivos": encontrados}
            ruta = os.path.join(base, nombre)
            try:
                sandbox.validar_ruta(ruta)
            except ErrorRutaArchivos:
                continue
            coincide = Path(nombre).match(patron)
            coincide = coincide and (not extension or nombre.lower().endswith(extension))
            if coincide:
                st = os.stat(ruta)
                encontrados.append({
                    "ruta": ruta, "nombre": nombre,
                    "tamano": st.st_size, "modificado": _fecha(st.st_mtime),
                })
    return {"archivos": encontrados[:500]}


def _decodificar(datos: bytes) -> tuple[str, str]:
    for codec in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return datos.decode(codec), codec
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace"), "latin-1"


def leer_archivo(parametros: dict, token_cancelacion=None) -> dict:
    if _cancelado(token_cancelacion):
        return {"cancelado": True}
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_existente(parametros["ruta"])
    st = os.stat(ruta)
    if not os.path.isfile(ruta):
        raise ErrorRutaArchivos("Se esperaba un archivo.")
    if st.st_size > sandbox.tamanio_maximo_lectura:
        raise ErrorRutaArchivos("Archivo excede el limite de lectura.")
    with open(ruta, "rb") as f:
        datos = f.read(sandbox.tamanio_maximo_lectura + 1)
    texto, codec = _decodificar(datos)
    huella = sandbox.huella_estado(ruta)
    return {"texto": texto, "codificacion": codec,
            "sha256": huella["sha256"], "mtime_ns": huella["st_mtime_ns"],
            "tamano": huella["st_size"]}


def crear_archivo(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_ruta(parametros["ruta"])
    if os.path.lexists(ruta):
        raise ErrorRutaArchivos("El archivo ya existe.")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    contenido = str(parametros.get("contenido", "")).encode("utf-8")
    sandbox.escribir_atomico(ruta, contenido)
    return {"creado": ruta, "tamano": len(contenido)}


def crear_directorio(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_ruta(parametros["ruta"])
    if os.path.lexists(ruta):
        raise ErrorRutaArchivos("La carpeta ya existe.")
    parents = bool(parametros.get("parents", False))
    if parents:
        os.makedirs(ruta)
    else:
        padre = os.path.dirname(ruta)
        if not os.path.isdir(padre):
            raise ErrorRutaArchivos("La carpeta padre no existe.")
        os.mkdir(ruta)
    return {"creado": ruta, "directorio": True}


def _respaldo(sandbox, ruta: str) -> str:
    respaldo_dir = sandbox.respaldos_dir(ruta)
    nombre = os.path.basename(ruta)
    sello = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = os.path.join(respaldo_dir, sello + "_" + nombre)
    shutil.copy2(ruta, destino)
    return destino


def modificar_archivo(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    ruta = sandbox.validar_existente(parametros["ruta"])
    actual = sandbox.huella_estado(ruta)
    esperado_sha = parametros.get("sha256_esperado")
    esperado_mtime = parametros.get("mtime_ns_esperado")
    if esperado_sha is not None and str(esperado_sha) != actual["sha256"]:
        raise ErrorRutaArchivos("Cambio concurrente: sha256 no coincide.")
    if esperado_mtime is not None and int(esperado_mtime) != actual["st_mtime_ns"]:
        raise ErrorRutaArchivos("Cambio concurrente: mtime_ns no coincide.")
    if esperado_sha is None and esperado_mtime is None:
        raise ErrorRutaArchivos("Se requiere sha256_esperado o mtime_ns_esperado.")
    contenido = str(parametros.get("contenido", "")).encode("utf-8")
    reemplazo = parametros.get("reemplazar")
    if reemplazo is not None:
        texto = leer_archivo({"_sandbox": sandbox, "ruta": ruta})["texto"]
        fragmento = str(reemplazo)
        nuevo = str(parametros.get("nuevo", ""))
        if fragmento not in texto:
            raise ErrorRutaArchivos("Fragmento no encontrado.")
        contenido = texto.replace(fragmento, nuevo, 1).encode("utf-8")
    respaldo = _respaldo(sandbox, ruta)
    actual_nuevo = sandbox.huella_estado(ruta)
    if actual_nuevo != actual:
        raise ErrorRutaArchivos("Cambio concurrente justo antes de escribir.")
    sandbox.escribir_atomico(ruta, contenido)
    return {"modificado": ruta, "respaldo": respaldo,
            "huella": sandbox.huella_estado(ruta)}


def copiar_elemento(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    origen = sandbox.validar_existente(parametros["origen"])
    destino = sandbox.validar_ruta(parametros["destino"])
    sobrescribir = bool(parametros.get("sobrescribir", False))
    if os.path.exists(destino) and not sobrescribir:
        raise ErrorRutaArchivos("El destino ya existe.")
    if origen == destino:
        raise ErrorRutaArchivos("Origen y destino son iguales.")
    if os.path.isdir(origen):
        if not os.path.exists(destino):
            os.makedirs(destino)
        for base, dirs, archivos in os.walk(origen, topdown=True, followlinks=False):
            dirs[:] = [d for d in dirs if d != RESPALDOS_DIR]
            for nombre in list(dirs):
                src_dir = os.path.join(base, nombre)
                sandbox.validar_ruta(src_dir)
            rel = os.path.relpath(base, origen)
            dest_base = destino if rel == "." else os.path.join(destino, rel)
            os.makedirs(dest_base, exist_ok=True)
            for nombre in archivos:
                if _cancelado(token_cancelacion):
                    shutil.rmtree(destino, ignore_errors=True)
                    return {"cancelado": True}
                src = os.path.join(base, nombre)
                sandbox.validar_ruta(src)
                dst = os.path.join(dest_base, nombre)
                if os.path.exists(dst) and not sobrescribir:
                    shutil.rmtree(destino, ignore_errors=True)
                    raise ErrorRutaArchivos("Conflicto dentro del directorio destino.")
                shutil.copy2(src, dst)
    else:
        shutil.copy2(origen, destino)
    return {"copiado": origen, "destino": destino}


def mover_elemento(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    origen = sandbox.validar_existente(parametros["origen"])
    destino = sandbox.validar_ruta(parametros["destino"])
    if os.path.exists(destino):
        raise ErrorRutaArchivos("El destino ya existe.")
    padre = os.path.dirname(destino)
    if not os.path.isdir(padre):
        raise ErrorRutaArchivos("La carpeta destino no existe.")
    try:
        shutil.move(origen, destino)
    except Exception:
        raise ErrorRutaArchivos("Fallo al mover el elemento.")
    return {"movido": origen, "destino": destino}


def renombrar_elemento(parametros: dict, token_cancelacion=None) -> dict:
    sandbox = parametros["_sandbox"]
    origen = sandbox.validar_existente(parametros["origen"])
    nuevo_nombre = sandbox.validar_nombre(parametros["nuevo_nombre"])
    destino = os.path.join(os.path.dirname(origen), nuevo_nombre)
    destino = sandbox.validar_ruta(destino)
    if os.path.lexists(destino):
        raise ErrorRutaArchivos("El nuevo nombre ya existe.")
    os.replace(origen, destino)
    return {"renombrado": origen, "destino": destino}
