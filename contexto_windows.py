"""Sensor nativo de contexto de Windows para Silvestra (Etapa 1).

Captura de forma pasiva y ligera la ventana en primer plano, proceso activo
e inactividad física del usuario mediante ctypes y Win32 APIs (user32 y kernel32),
sin dependencias externas ni ganchos (hooks) invasivos.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from typing import Any

# Constante de acceso a procesos en Windows (Windows Vista+)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DESKTOP_ENUMERATE = 0x0100
DWMWA_CLOAKED = 14
CLASES_SISTEMA_DESCARTAR = {"Progman", "WorkerW", "Shell_TrayWnd"}


class LASTINPUTINFO(ctypes.Structure):
    """Estructura Win32 para recibir la telemetría de GetLastInputInfo."""

    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class SensorContextoWindows:
    """Sensor pasivo que lee el estado de ventanas y actividad en Windows 11."""

    def __init__(
        self,
        user32_lib: Any = None,
        kernel32_lib: Any = None,
        dwmapi_lib: Any = None,
    ) -> None:
        """Inicializa el sensor configurando firmas explícitas de Win32."""
        self._user32 = user32_lib or ctypes.windll.user32
        self._kernel32 = kernel32_lib or ctypes.windll.kernel32
        if dwmapi_lib is not None:
            self._dwmapi = dwmapi_lib
        else:
            try:
                self._dwmapi = ctypes.windll.dwmapi
            except Exception:
                self._dwmapi = None
        self._configurar_firmas()

    def _configurar_firmas(self) -> None:
        """Configura argtypes y restype para llamadas seguras en 64 bits."""
        try:
            self._user32.GetForegroundWindow.argtypes = []
            self._user32.GetForegroundWindow.restype = wintypes.HWND

            self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            self._user32.GetWindowTextLengthW.restype = ctypes.c_int

            self._user32.GetWindowTextW.argtypes = [
                wintypes.HWND,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            self._user32.GetWindowTextW.restype = ctypes.c_int

            self._user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD

            self._user32.GetLastInputInfo.argtypes = [
                ctypes.POINTER(LASTINPUTINFO)
            ]
            self._user32.GetLastInputInfo.restype = wintypes.BOOL

            self._kernel32.GetTickCount.argtypes = []
            self._kernel32.GetTickCount.restype = wintypes.DWORD

            self._kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            self._kernel32.OpenProcess.restype = wintypes.HANDLE

            self._kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

            self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            self._kernel32.CloseHandle.restype = wintypes.BOOL

            self._user32.OpenInputDesktop.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            self._user32.OpenInputDesktop.restype = wintypes.HANDLE

            self._user32.CloseDesktop.argtypes = [wintypes.HANDLE]
            self._user32.CloseDesktop.restype = wintypes.BOOL

            self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
            self._user32.IsWindowVisible.restype = wintypes.BOOL

            self._user32.IsIconic.argtypes = [wintypes.HWND]
            self._user32.IsIconic.restype = wintypes.BOOL

            self._user32.GetClassNameW.argtypes = [
                wintypes.HWND,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            self._user32.GetClassNameW.restype = ctypes.c_int

            if self._dwmapi:
                self._dwmapi.DwmGetWindowAttribute.argtypes = [
                    wintypes.HWND,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                ]
                self._dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        except Exception:
            # En caso de mocks parciales o entornos de prueba, continuar
            pass

    def _obtener_inactividad_segundos(self) -> float:
        """Calcula el tiempo sin interacción física en segundos de forma segura."""
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not self._user32.GetLastInputInfo(ctypes.byref(lii)):
                return 0.0

            tick_actual = self._kernel32.GetTickCount()
            # Aritmética segura de 32 bits para contemplar wrap-around tras ~49.7 días
            delta_ms = (tick_actual - lii.dwTime) & 0xFFFFFFFF
            return max(0.0, float(delta_ms) / 1000.0)
        except Exception:
            return 0.0

    def _obtener_titulo_ventana(self, hwnd: int) -> str:
        """Lee el título Unicode completo de una ventana activa."""
        try:
            longitud = self._user32.GetWindowTextLengthW(hwnd)
            if longitud <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(longitud + 1)
            self._user32.GetWindowTextW(hwnd, buffer, longitud + 1)
            return buffer.value or ""
        except Exception:
            return ""

    def _obtener_nombre_ejecutable(self, pid: int) -> str:
        """Obtiene el nombre base del ejecutable dado su PID."""
        if not pid or pid <= 0:
            return ""

        handle = None
        try:
            handle = self._kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return ""

            buffer = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                ruta = buffer.value
                return os.path.basename(ruta) if ruta else ""
            return ""
        except Exception:
            return ""
        finally:
            if handle:
                try:
                    self._kernel32.CloseHandle(handle)
                except Exception:
                    pass

    def _obtener_clase_ventana(self, hwnd: int) -> str:
        """Obtiene la clase de ventana Win32 de forma segura."""
        try:
            buf = ctypes.create_unicode_buffer(256)
            res = self._user32.GetClassNameW(hwnd, buf, 256)
            return buf.value if res > 0 else ""
        except Exception:
            return ""

    def _es_ventana_cloaked(self, hwnd: int) -> bool:
        """Detecta ventanas cloaked (invisibles/suspendidas de Store) en Windows 11."""
        if not self._dwmapi:
            return False
        try:
            cloaked = wintypes.DWORD(0)
            res = self._dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_CLOAKED,
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked),
            )
            return res == 0 and bool(cloaked.value)
        except Exception:
            return False

    def _obtener_ventana_input_desktop(self) -> tuple[int, int, str, str] | None:
        """Fallback para sesiones en segundo plano: obtiene la ventana superior activa en InputDesktop."""
        handle_desk = None
        try:
            handle_desk = self._user32.OpenInputDesktop(0, False, DESKTOP_ENUMERATE)
            if not handle_desk:
                return None

            resultado: list[tuple[int, int, str, str]] = []

            def _enum_cb(hwnd: int, lparam: int) -> bool:
                try:
                    if self._user32.IsWindowVisible(hwnd) and not self._user32.IsIconic(hwnd):
                        if self._es_ventana_cloaked(hwnd):
                            return True
                        clase = self._obtener_clase_ventana(hwnd)
                        if clase in CLASES_SISTEMA_DESCARTAR:
                            return True
                        tit = self._obtener_titulo_ventana(hwnd)
                        if tit:
                            pid = wintypes.DWORD(0)
                            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            exe = self._obtener_nombre_ejecutable(pid.value) if pid.value else ""
                            if exe:
                                resultado.append((int(hwnd), int(pid.value), exe, tit))
                                return False
                except Exception:
                    pass
                return True

            cb_tipo = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            self._user32.EnumDesktopWindows(handle_desk, cb_tipo(_enum_cb), 0)
            return resultado[0] if resultado else None
        except Exception:
            return None
        finally:
            if handle_desk:
                try:
                    self._user32.CloseDesktop(handle_desk)
                except Exception:
                    pass

    def leer(self) -> dict[str, Any]:
        """Captura y retorna el estado de la ventana en primer plano y actividad."""
        t_ahora = time.time()
        inactividad = self._obtener_inactividad_segundos()

        hwnd_val: int | None = None
        titulo = ""
        pid_val: int | None = None
        ejecutable = ""

        try:
            hwnd = self._user32.GetForegroundWindow()
            if hwnd:
                hwnd_val = int(hwnd)
                titulo = self._obtener_titulo_ventana(hwnd)

                pid = wintypes.DWORD(0)
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pid_val = int(pid.value)
                    ejecutable = self._obtener_nombre_ejecutable(pid.value)

            # Fallback transparente si no se obtuvo ejecutable (ej. en hilos/subprocesos secundarios)
            if not ejecutable:
                w_top = self._obtener_ventana_input_desktop()
                if w_top:
                    h_top, p_top, exe_top, tit_top = w_top
                    if not hwnd_val:
                        hwnd_val = h_top
                    if not pid_val:
                        pid_val = p_top
                    if not ejecutable:
                        ejecutable = exe_top
                    if not titulo:
                        titulo = tit_top
        except Exception:
            pass

        return {
            "hwnd": hwnd_val,
            "titulo": titulo,
            "pid": pid_val,
            "ejecutable": ejecutable,
            "inactividad_seg": round(inactividad, 2),
            "nivel": "detectado",
            "timestamp": t_ahora,
            "disponible": True,
        }


# Instancia única reutilizable del sensor
_sensor_instancia: SensorContextoWindows | None = None


def obtener_contexto_windows() -> dict[str, Any]:
    """Función de conveniencia para consultar el sensor activo de Windows."""
    global _sensor_instancia
    if _sensor_instancia is None:
        _sensor_instancia = SensorContextoWindows()
    return _sensor_instancia.leer()
