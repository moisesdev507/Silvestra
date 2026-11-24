"""Cartuchos de especialistas para escalado cognitivo modular de Lyris."""
from .matematicas import EXPERTO_MATEMATICAS
from .programacion import EXPERTO_PROGRAMACION

REGISTRO_EXPERTOS = {
    "programacion": EXPERTO_PROGRAMACION,
    "matematicas": EXPERTO_MATEMATICAS,
}


def obtener_cartucho(area: str) -> str:
    """Devuelve el prompt especializado del cartucho solicitado o cadena vacía."""
    return REGISTRO_EXPERTOS.get(str(area or "").lower().strip(), "")


__all__ = ["REGISTRO_EXPERTOS", "obtener_cartucho", "EXPERTO_PROGRAMACION", "EXPERTO_MATEMATICAS"]
