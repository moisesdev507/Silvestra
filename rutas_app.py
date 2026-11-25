"""Resolución de rutas para Kaya en desarrollo y en el ejecutable congelado.

En modo frozen los recursos de solo lectura viven en ``sys._MEIPASS``
(``_internal``), mientras que la configuración y los datos del usuario deben
quedar junto a ``Kaya.exe`` (directorio de ``sys.executable``).
"""
import os
import sys


def _congelado():
    return bool(getattr(sys, "frozen", False))


def dir_recursos():
    """Directorio de modelos `.onnx` y recursos empaquetados."""
    if _congelado():
        return os.path.abspath(
            str(getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def dir_usuario():
    """Directorio donde se crean `.env`, `datos/` y `silvestra.log`."""
    if _congelado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def ruta_recurso(*partes):
    """Une componentes sobre ``dir_recursos()``."""
    return os.path.join(dir_recursos(), *[str(p) for p in partes])


def ruta_usuario(*partes):
    """Une componentes sobre ``dir_usuario()``."""
    return os.path.join(dir_usuario(), *[str(p) for p in partes])


def preparar_dir_usuario():
    """Crea `datos/` y un `.env` vacío junto al ejecutable; devuelve la ruta."""
    base = dir_usuario()
    try:
        os.makedirs(os.path.join(base, "datos"), exist_ok=True)
        ruta_env = os.path.join(base, ".env")
        if not os.path.exists(ruta_env):
            with open(ruta_env, "w", encoding="utf-8"):
                pass
    except Exception as e:
        print(f"[rutas_app] No pude preparar la carpeta del usuario: {e}", flush=True)
    return base
