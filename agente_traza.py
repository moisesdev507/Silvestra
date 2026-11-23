"""Traza por paso y cancelación inmediata del bucle agéntico."""
from __future__ import annotations

import re
import threading
import time

import verificacion_modelo as vm


def _texto(valor, max_len=300):
    texto = str(valor or "")
    texto = re.sub(r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTADO]", texto)
    texto = re.sub(r"\b(?:sk|coh|gsk|nvapi|grs)[_-][A-Za-z0-9_\-]{6,}", "[CLAVE REDACTADA]", texto)
    return texto[:max_len]


def _sanitizado(datos):
    limpio = vm.sanitizar_datos(datos)
    if isinstance(limpio, dict):
        return {str(clave): (_texto(valor) if isinstance(valor, str) else valor)
                for clave, valor in limpio.items()}
    return limpio


class Traza:
    """Registro thread-safe con bandera de cancelación compartida."""

    def __init__(self, limite=200):
        self._bloqueo = threading.RLock()
        self._eventos = []
        self._cancelacion = threading.Event()
        self._limite = max(1, int(limite))

    def registrar(self, paso, intencion="", herramienta="", argumentos=None,
                  resultado=None, verificado=None, duracion_ms=0, error=""):
        with self._bloqueo:
            if len(self._eventos) >= self._limite:
                self._eventos.pop(0)
            self._eventos.append({
                "paso": int(paso),
                "intencion": _texto(intencion, 160),
                "herramienta": _texto(herramienta, 80),
                "argumentos": _sanitizado(argumentos or {}),
                "resultado": _texto(resultado),
                "verificado": verificado,
                "duracion_ms": int(duracion_ms or 0),
                "error": _texto(error),
                "timestamp": time.time(),
            })

    def cancelar(self):
        """Cancela el bucle en el próximo punto de control."""
        self._cancelacion.set()

    @property
    def cancelada(self):
        return self._cancelacion.is_set()

    @property
    def evento(self):
        return self._cancelacion

    def a_lista(self):
        with self._bloqueo:
            return [dict(evento) for evento in self._eventos]

    def ultimo(self):
        with self._bloqueo:
            return dict(self._eventos[-1]) if self._eventos else None
