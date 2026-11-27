"""Arranque oculto del navegador WebRTC: sin bienvenida ni ventana visible en Windows."""
import json
import os
import time
from typing import List, Optional

SW_HIDE = 0
_STARTF_USESHOWWINDOW = 0x0001
_EX_TOOLWINDOW = 0x00000080
_EX_APPWINDOW = 0x00040000


def preparar_perfil(perfil: str) -> bool:
    """Crea First Run y preferencias que suprimen la pantalla de bienvenida."""
    try:
        os.makedirs(perfil, exist_ok=True)
        with open(os.path.join(perfil, "First Run"), "a", encoding="utf-8") as _:
            pass
        ruta = os.path.join(perfil, "Default", "Preferences")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        datos = {}
        if os.path.isfile(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                cargados = json.load(f)
            if isinstance(cargados, dict):
                datos = cargados
        navegador = datos.setdefault("browser", {})
        navegador.update({
            "has_seen_welcome_page": True,
            "has_seen_welcome_page_37": True,
            "show_welcome_page": False,
        })
        datos.setdefault("edge", {}).update({
            "show_welcome_page": False,
            "show_firstrun_pages": False,
        })
        datos.setdefault("profile", {}).update({
            "exit_type": "Normal",
            "exited_cleanly": True,
        })
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def comando_edge(navegador: str, perfil: str, url: str) -> List[str]:
    """Comando completo: conserva el audio y añade las banderas anti-bienvenida."""
    return [
        navegador,
        f"--user-data-dir={perfil}",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        f"--app={url}",
        "--window-size=1,1",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion",
        "--window-position=-2400,-2400",
    ]


def startupinfo_oculto():
    """STARTUPINFO con SW_HIDE para el process creation; None fuera de Windows."""
    if os.name != "nt":
        return None
    import subprocess
    info = subprocess.STARTUPINFO()
    info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", _STARTF_USESHOWWINDOW)
    info.wShowWindow = SW_HIDE
    return info


def ocultar_ventana_pid(pid: int, titulo: Optional[str] = None,
                        intentos: int = 40, espera: float = 0.05) -> bool:
    """Oculta por HWND todas las ventanas top-level del PID del navegador."""
    if os.name != "nt" or not pid:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    tipo_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    encontradas = []

    def _visitar(hwnd, _dato):
        proceso = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proceso))
        if proceso.value != int(pid):
            return True
        if titulo:
            longitud = user32.GetWindowTextLengthW(hwnd)
            texto = ctypes.create_unicode_buffer(longitud + 1)
            user32.GetWindowTextW(hwnd, texto, longitud + 1)
            if titulo.lower() not in texto.value.lower():
                return True
        encontradas.append(hwnd)
        return True

    callback = tipo_callback(_visitar)
    for _ in range(intentos):
        encontradas.clear()
        user32.EnumWindows(callback, 0)
        for hwnd in encontradas:
            ex = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, (ex | _EX_TOOLWINDOW) & ~_EX_APPWINDOW)
            user32.ShowWindow(hwnd, SW_HIDE)
        if encontradas:
            return True
        time.sleep(espera)
    return False


__all__ = [
    "preparar_perfil", "comando_edge", "startupinfo_oculto",
    "ocultar_ventana_pid", "SW_HIDE",
]
