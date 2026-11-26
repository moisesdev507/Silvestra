"""Lectura del portapapeles en Windows segura desde hilos secundarios.

Contrato de ``leer_portapapeles_windows``:
  * ``str`` con el texto (puede ser ``""`` si el portapapeles está vacío);
  * ``None`` si otra app lo tiene bloqueado o no hay API disponible.

Sin tkinter: Win32 puro y, como respaldo, PowerShell.
"""
import subprocess
import time

CF_UNICODETEXT = 13
INTENTOS = 5
ESPERA_REINTENTO_S = 0.015
TIMEOUT_PS = 2.5
CREAR_SIN_VENTANA = 0x08000000


def _api():
    """Configura y devuelve (user32, kernel32, wstring_at)."""
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    return user32, kernel32, ctypes.wstring_at


def _leer_win32_crudo():
    """Texto, '' si no hay texto, o None si no se pudo abrir tras reintentar."""
    user32, kernel32, wstring_at = _api()
    abierto = False
    for intento in range(INTENTOS):
        if user32.OpenClipboard(0):
            abierto = True
            break
        if intento + 1 < INTENTOS:
            time.sleep(ESPERA_REINTENTO_S)
    if not abierto:
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        puntero = kernel32.GlobalLock(handle)
        if not puntero:
            return ""
        try:
            return wstring_at(puntero)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _leer_powershell():
    """Respaldo sin Qt: Get-Clipboard -Raw; None si falla."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=TIMEOUT_PS, creationflags=CREAR_SIN_VENTANA,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def _limpiar(texto, max_chars):
    """Normaliza saltos, quita caracteres de control y recorta."""
    t = str(texto or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    t = "".join(ch for ch in t if ch in "\n\t" or ord(ch) >= 32).strip()
    return t[:max(1, int(max_chars))]


def leer_portapapeles_windows(max_chars=1200):
    """Devuelve el texto copiado; '' si está vacío o None si está bloqueado."""
    try:
        texto = _leer_win32_crudo()
    except Exception:
        texto = None
    if texto is None:
        texto = _leer_powershell()
    if texto is None:
        return None
    return _limpiar(texto, max_chars)


__all__ = ["leer_portapapeles_windows"]
