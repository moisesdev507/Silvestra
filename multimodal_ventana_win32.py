"""Enumeración Win32 de ventanas externas en orden Z."""
import ctypes
import os
from ctypes import wintypes


def enumerar_ventana_externa():
    """Devuelve la primera ventana externa, visible y utilizable del orden Z."""
    if os.name != "nt":
        return None
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        try:
            dwmapi = ctypes.windll.dwmapi
        except Exception:
            dwmapi = None
        clases = {"WorkerW", "Progman", "Shell_TrayWnd"}
        hallada = []
        tipo_cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.EnumWindows.argtypes = [tipo_cb, wintypes.LPARAM]
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        def visitar(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            clase = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, clase, len(clase))
            if clase.value in clases or get_long(hwnd, -20) & 0x80:
                return True
            if not dwmapi:
                return True
            else:
                cloaked = wintypes.DWORD(0)
                try:
                    estado = dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked),
                                                          ctypes.sizeof(cloaked))
                    if estado != 0 or cloaked.value:
                        return True
                except Exception:
                    return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == os.getpid():
                return True
            largo = user32.GetWindowTextLengthW(hwnd)
            if largo <= 0:
                return True
            titulo = ctypes.create_unicode_buffer(min(largo + 1, 1024))
            user32.GetWindowTextW(hwnd, titulo, len(titulo))
            if not titulo.value:
                return True
            exe = ""
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    ruta = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(len(ruta))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, ruta, ctypes.byref(size)):
                        exe = os.path.basename(ruta.value)
                finally:
                    kernel32.CloseHandle(handle)
            hallada.append({"hwnd": int(hwnd), "pid": int(pid.value), "titulo": titulo.value,
                            "ejecutable": exe, "clase": clase.value})
            return False

        user32.EnumWindows(tipo_cb(visitar), 0)
        return hallada[0] if hallada else None
    except Exception:
        return None
