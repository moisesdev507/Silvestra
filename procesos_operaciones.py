"""Supervision y operaciones Win32 controladas de procesos."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import threading
import time
from typing import Any, Optional

from procesos_seguridad import (
    CatalogoAppsAutorizadas,
    ErrorProcesoSeguridad,
    IdentidadProceso,
    normalizar_exe,
    obtener_identidad,
    proceso_escritico,
    validar_argumentos,
    verificar_identidad_proceso,
)


class RegistroProceso:
    def __init__(self, identidad: IdentidadProceso, id_app: str) -> None:
        self.identidad = identidad
        self.id_app = id_app
        self.estado = "ejecutando"
        self.hora_inicio = time.time()
        self.codigo_salida: Optional[int] = None

    def a_dict(self) -> dict:
        return {
            "identidad": self.identidad.a_dict(),
            "id_app": self.id_app,
            "estado": self.estado,
            "hora_inicio": self.hora_inicio,
            "codigo_salida": self.codigo_salida,
        }


class SupervisorProcesosSilvestra:
    def __init__(self) -> None:
        self._bloqueo = threading.RLock()
        self._procesos: dict[int, RegistroProceso] = {}
        self._popen: dict[int, subprocess.Popen] = {}

    def registrar(self, identidad: IdentidadProceso, id_app: str) -> None:
        with self._bloqueo:
            self._procesos[identidad.pid] = RegistroProceso(identidad, id_app)

    def obtener(self, pid: int) -> Optional[RegistroProceso]:
        with self._bloqueo:
            return self._procesos.get(pid)

    def actualizar(self, pid: int, estado: str, codigo: Optional[int] = None) -> None:
        with self._bloqueo:
            registro = self._procesos.get(pid)
            if registro:
                registro.estado = estado
                if codigo is not None:
                    registro.codigo_salida = codigo

    def registrar_popen(self, pid: int, proceso: subprocess.Popen) -> None:
        with self._bloqueo:
            self._popen[pid] = proceso

    def esperar_todos(self, timeout: float = 3.0) -> None:
        with self._bloqueo:
            procesos = list(self._popen.items())
        limite = max(0.1, float(timeout))
        for pid, proceso in procesos:
            try:
                proceso.wait(timeout=limite)
            except Exception:
                pass
            finally:
                try:
                    proceso.stdout and proceso.stdout.close()
                    proceso.stderr and proceso.stderr.close()
                except Exception:
                    pass
                with self._bloqueo:
                    self._popen.pop(pid, None)

    def listar(self, solo_silvestra: bool = False) -> list[dict]:
        with self._bloqueo:
            return [r.a_dict() for r in self._procesos.values()]

    def limpiar(self) -> None:
        with self._bloqueo:
            self._procesos.clear()


def _proceso_info(pid: int) -> dict:
    identidad = obtener_identidad(pid)
    if identidad is None:
        return {"pid": pid, "nombre": "", "ejecutable": "",
                "estado": "desaparecido"}
    nombre = os.path.basename(identidad.ruta_ejecutable)
    return {
        "pid": pid,
        "nombre": nombre,
        "ejecutable": identidad.ruta_ejecutable,
        "estado": "ejecutando",
        "creado_en_ns": identidad.creado_en_ns,
    }


def consultar_procesos(parametros: dict, token_cancelacion=None) -> dict:
    supervisor = parametros["_supervisor"]
    limite = max(1, min(500, int(parametros.get("limite", 100))))
    filtro = str(parametros.get("nombre", "")).strip().lower()
    solo = bool(parametros.get("solo_silvestra", False))
    resultados = []
    if solo:
        lista = supervisor.listar(True)
        for item in lista[:limite]:
            info = item["identidad"]
            pid = int(info["pid"])
            if filtro and filtro not in os.path.basename(info["ruta_ejecutable"]).lower():
                continue
            resultados.append({
                "pid": pid,
                "nombre": os.path.basename(info["ruta_ejecutable"]),
                "ejecutable": info["ruta_ejecutable"],
                "estado": item["estado"],
                "creado_en_ns": info["creado_en_ns"],
            })
        return {"procesos": resultados}

    if os.name != "nt":
        return {"procesos": []}
    snapshot = None
    try:
        kernel32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x00000002
        InvalidHandle = -1

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == InvalidHandle:
            return {"procesos": []}
        entrada = PROCESSENTRY32()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entrada)):
            return {"procesos": []}
        while True:
            if token_cancelacion and hasattr(token_cancelacion, "esta_cancelado"):
                if token_cancelacion.esta_cancelado():
                    break
            pid = int(entrada.th32ProcessID)
            nombre = entrada.szExeFile
            if not filtro or filtro in nombre.lower():
                info = _proceso_info(pid)
                if info["nombre"] or not proceso_escritico(nombre, pid):
                    resultados.append(info)
            if len(resultados) >= limite:
                break
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entrada)):
                break
    except Exception:
        return {"procesos": [], "error": "ERROR_ENUMERACION_PROCESOS"}
    finally:
        if snapshot:
            try:
                ctypes.windll.kernel32.CloseHandle(snapshot)
            except Exception:
                pass
    return {"procesos": resultados}


def buscar_proceso(parametros: dict, token_cancelacion=None) -> dict:
    nombre = str(parametros.get("nombre", "")).strip()
    id_app = str(parametros.get("id_app", "")).strip()
    if not nombre and not id_app:
        raise ErrorProcesoSeguridad("Se requiere nombre o id_app.")
    return consultar_procesos({
        "_supervisor": parametros["_supervisor"],
        "limite": parametros.get("limite", 100),
        "nombre": nombre,
        "solo_silvestra": bool(id_app),
    }, token_cancelacion)


def estado_aplicacion(parametros: dict, token_cancelacion=None) -> dict:
    supervisor = parametros["_supervisor"]
    pid = parametros.get("pid")
    if pid is not None:
        identidad = IdentidadProceso(
            int(pid),
            int(parametros["creado_en_ns"]),
            normalizar_exe(parametros["ruta_ejecutable"]),
        )
        ok, motivo = verificar_identidad_proceso(identidad)
        if not ok:
            return {"activa": False, "motivo": motivo}
        return {"activa": True, "identidad": identidad.a_dict()}
    id_app = str(parametros.get("id_app", "")).strip().lower()
    if not id_app:
        raise ErrorProcesoSeguridad("Se requiere id_app o identidad.")
    coincidencias = [
        r for r in supervisor.listar(True)
        if r["id_app"] == id_app
    ]
    activas = []
    for item in coincidencias:
        info = item["identidad"]
        identidad = IdentidadProceso(
            int(info["pid"]),
            int(info["creado_en_ns"]),
            normalizar_exe(info["ruta_ejecutable"]),
        )
        ok, motivo = verificar_identidad_proceso(identidad)
        if ok:
            activas.append(identidad.a_dict())
    return {"activa": bool(activas), "instancias": activas}


def iniciar_aplicacion(parametros: dict, token_cancelacion=None) -> dict:
    catalogo = parametros["_catalogo"]
    supervisor = parametros["_supervisor"]
    id_app = str(parametros["id_app"]).strip().lower()
    app = catalogo.obtener(id_app)
    if app is None:
        raise ErrorProcesoSeguridad("Aplicacion no autorizada.")
    if not app.permite_inicio:
        raise ErrorProcesoSeguridad("Inicio no permitido.")
    ruta = normalizar_exe(app.ruta_ejecutable)
    argumentos = validar_argumentos(
        list(parametros.get("argumentos", [])),
        app.argumentos_permitidos,
    )
    directorio = app.directorio_trabajo
    if directorio:
        directorio = normalizar_exe(os.path.join(directorio, os.path.basename(ruta))) if False else os.path.abspath(directorio)
    try:
        proceso = subprocess.Popen(
            [ruta, *argumentos],
            shell=False,
            close_fds=True,
            cwd=directorio or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tiempo = time.time()
        time.sleep(0.03)
        identidad = obtener_identidad(proceso.pid)
        if identidad is None:
            return {"error": "FALLO_INICIO_APLICACION", "pid": proceso.pid}
        supervisor.registrar(identidad, id_app)
        supervisor.registrar_popen(proceso.pid, proceso)
        return {
            "pid": proceso.pid,
            "id_app": id_app,
            "identidad": identidad.a_dict(),
            "inicio": tiempo,
        }
    except Exception as exc:
        raise ErrorProcesoSeguridad("FALLO_INICIO_APLICACION")


def cerrar_aplicacion(parametros: dict, token_cancelacion=None) -> dict:
    supervisor = parametros["_supervisor"]
    catalogo = parametros["_catalogo"]
    id_app = str(parametros.get("id_app", "")).strip().lower()
    pid = int(parametros["pid"])
    creado = int(parametros["creado_en_ns"])
    ruta = normalizar_exe(parametros["ruta_ejecutable"])
    app = catalogo.obtener(id_app)
    if app is None or not app.permite_cierre:
        raise ErrorProcesoSeguridad("Cierre no autorizado.")
    identidad = IdentidadProceso(pid, creado, ruta)
    ok, motivo = verificar_identidad_proceso(identidad)
    if not ok:
        return {"cerrado": False, "motivo": motivo}
    nombre = os.path.basename(ruta).lower()
    if proceso_escritico(nombre, pid):
        return {"cerrado": False, "motivo": "PROCESO_CRITICO"}
    registro = supervisor.obtener(pid)
    if registro is None or registro.identidad != identidad:
        return {"cerrado": False, "motivo": "PROCESO_NO_GESTIONADO"}

    if os.name != "nt":
        return {"cerrado": False, "motivo": "PLATAFORMA_NO_SOPORTADA"}
    try:
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        enviados = []

        def enum_cb(hwnd, lparam):
            pid_ref = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_ref))
            if pid_ref.value == pid:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                enviados.append(int(hwnd))
            return True

        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(cb(enum_cb), 0)
        if not enviados:
            return {"cerrado": False, "motivo": "APLICACION_NO_RESPONDE"}
        inicio = time.time()
        espera = min(5.0, float(parametros.get("espera_seg", 3.0)))
        while time.time() - inicio < espera:
            if token_cancelacion and token_cancelacion.esta_cancelado():
                return {"cerrado": False, "motivo": "CANCELADA"}
            activo, motivo = verificar_identidad_proceso(identidad)
            if not activo:
                supervisor.actualizar(pid, "finalizado")
                return {"cerrado": True, "motivo": "CERRADO_NORMAL"}
            time.sleep(0.05)
        return {"cerrado": False, "motivo": "APLICACION_NO_RESPONDE"}
    except Exception:
        return {"cerrado": False, "motivo": "ERROR_CIERRE_NORMAL"}
