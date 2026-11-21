"""Catalogo deny-by-default e identidad segura de procesos Windows."""
from __future__ import annotations

import ctypes
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


LISTA_PROCESOS_CRITICOS = {
    "system", "idle", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe",
    "winlogon.exe", "dwm.exe", "explorer.exe", "taskmgr.exe",
    "msmpeng.exe", "securityhealthservice.exe", "audiodg.exe",
    "spoolsv.exe", "conhost.exe",
}
LANZADORES_PROHIBIDOS = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe",
    "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe",
}
META_SHELL = set("&|;><`$\n\r")


class ErrorProcesoSeguridad(ValueError):
    pass


@dataclass(frozen=True)
class AplicacionAutorizada:
    id_app: str
    nombre: str
    ruta_ejecutable: str
    argumentos_permitidos: tuple[str, ...] = ()
    permite_inicio: bool = True
    permite_cierre: bool = False
    directorio_trabajo: str = ""


@dataclass(frozen=True)
class IdentidadProceso:
    pid: int
    creado_en_ns: int
    ruta_ejecutable: str

    def a_dict(self) -> dict:
        return {
            "pid": self.pid,
            "creado_en_ns": self.creado_en_ns,
            "ruta_ejecutable": self.ruta_ejecutable,
        }


class CatalogoAppsAutorizadas:
    def __init__(self) -> None:
        self._apps: dict[str, AplicacionAutorizada] = {}
        self._bloqueo = threading.RLock()

    def registrar(self, app: AplicacionAutorizada, sobrescribir: bool = False) -> bool:
        app_id = str(app.id_app or "").strip().lower()
        if not app_id:
            raise ErrorProcesoSeguridad("id_app obligatorio.")
        ruta = normalizar_exe(app.ruta_ejecutable)
        nueva = AplicacionAutorizada(
            app_id, str(app.nombre).strip(), ruta,
            tuple(str(a) for a in app.argumentos_permitidos),
            bool(app.permite_inicio), bool(app.permite_cierre),
            str(app.directorio_trabajo or ""),
        )
        with self._bloqueo:
            if app_id in self._apps and not sobrescribir:
                raise ErrorProcesoSeguridad("Aplicacion ya registrada.")
            self._apps[app_id] = nueva
        return True

    def obtener(self, id_app: str) -> Optional[AplicacionAutorizada]:
        with self._bloqueo:
            return self._apps.get(str(id_app or "").strip().lower())

    def listar(self) -> list[AplicacionAutorizada]:
        with self._bloqueo:
            return list(self._apps.values())


def normalizar_exe(ruta: str) -> str:
    if not isinstance(ruta, str) or not ruta.strip():
        raise ErrorProcesoSeguridad("Ruta inexistente.")
    ruta = ruta.strip()
    if "\x00" in ruta:
        raise ErrorProcesoSeguridad("Ruta contiene bytes nulos.")
    if ruta.startswith(("\\\\", "//")):
        raise ErrorProcesoSeguridad("Rutas UNC no permitidas.")
    normal = ruta.replace("/", "\\")
    if ".." in re.split(r"[\\/]+", normal):
        raise ErrorProcesoSeguridad("Segmento '..' no permitido.")
    if normal.lower().startswith("\\\\?\\") or normal.lower().startswith("\\\\.\\"):
        raise ErrorProcesoSeguridad("Ruta de dispositivo no permitida.")
    canon = os.path.realpath(os.path.abspath(ruta))
    if not os.path.isfile(canon):
        raise ErrorProcesoSeguridad("Ejecutable inexistente.")
    if not canon.lower().endswith(".exe"):
        raise ErrorProcesoSeguridad("Solo se permiten ejecutables .exe.")
    if os.path.islink(canon):
        raise ErrorProcesoSeguridad("Enlace simbolico no permitido.")
    nombre = os.path.basename(canon).lower()
    if nombre in LANZADORES_PROHIBIDOS:
        raise ErrorProcesoSeguridad("Lanzador generico prohibido.")
    if os.name == "nt":
        try:
            attrs = os.lstat(canon).st_file_attributes
            if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ErrorProcesoSeguridad("Reparse point no permitido.")
        except AttributeError:
            pass
    return canon


def validar_argumentos(argumentos: list[str], permitidos: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(argumentos, list):
        raise ErrorProcesoSeguridad("Argumentos deben ser una lista.")
    limite = 32
    if len(argumentos) > limite:
        raise ErrorProcesoSeguridad("Demasiados argumentos.")
    resultado = []
    set_permitidos = set(str(a) for a in permitidos)
    for arg in argumentos:
        texto = str(arg)
        if "\x00" in texto or any(c in texto for c in META_SHELL):
            raise ErrorProcesoSeguridad("Argumento contiene metacaracteres prohibidos.")
        if permitidos and texto not in set_permitidos:
            raise ErrorProcesoSeguridad("Argumento no contemplado por el catalogo.")
        resultado.append(texto)
    return tuple(resultado)


def proceso_escritico(nombre: str, pid: int = 0) -> bool:
    nombre_norm = str(nombre or "").strip().lower()
    if nombre_norm in LISTA_PROCESOS_CRITICOS:
        return True
    if pid and pid in (os.getpid(), os.getppid()):
        return True
    return False


def obtener_identidad(pid: int) -> Optional[IdentidadProceso]:
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creada = ctypes.c_ulonglong(0)
            salida = ctypes.c_ulonglong(0)
            kernel = ctypes.c_ulonglong(0)
            usuario = ctypes.c_ulonglong(0)
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creada),
                ctypes.byref(salida),
                ctypes.byref(kernel),
                ctypes.byref(usuario),
            )
            if not ok:
                return None
            buffer = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return None
            ruta = normalizar_exe(buffer.value)
            return IdentidadProceso(pid, creada.value, ruta)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def verificar_identidad_proceso(identidad: IdentidadProceso) -> tuple[bool, str]:
    actual = obtener_identidad(identidad.pid)
    if actual is None:
        return False, "PROCESO_DESAPARECIDO"
    if actual.creado_en_ns != identidad.creado_en_ns:
        return False, "PID_REUTILIZADO"
    if os.path.realpath(actual.ruta_ejecutable).lower() != (
        os.path.realpath(identidad.ruta_ejecutable).lower()
    ):
        return False, "PID_REUTILIZADO"
    return True, "ACTIVO"
