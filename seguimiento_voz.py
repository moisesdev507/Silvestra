"""Ventana de seguimiento sin wake-word tras «¿Sí?» o respuesta clásica.

Mantiene abierta la captura unos segundos para hablar de corrido, igual que
Gemini Live, sin exigir repetir la palabra clave en cada turno.
"""
import time

VENTANA_SEG = 8.0


def abrir(gestor=None, app=None):
    """Refresca la ventana y el seguimiento del gestor de invocación."""
    import charla_continua
    charla_continua.abrir_ventana_charla(VENTANA_SEG)
    if gestor is not None:
        with gestor.bloqueo:
            gestor.seguimiento_activo = True
            gestor.limite_seguimiento = time.monotonic() + VENTANA_SEG
