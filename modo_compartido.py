"""Detecta la edición compartida de prueba: solo activa en el .exe compilado."""
import os
import sys

NOMBRE_FLAG = "beta_compartida.flag"


def ruta_flag():
    """Ruta del marcador, junto al ejecutable (o al intérprete en desarrollo)."""
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), NOMBRE_FLAG)


def es_version_compartida() -> bool:
    """True únicamente cuando el ejecutable congelado incluye el marcador."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        return os.path.isfile(ruta_flag())
    except Exception:
        return False


__all__ = ["es_version_compartida", "ruta_flag", "NOMBRE_FLAG"]
