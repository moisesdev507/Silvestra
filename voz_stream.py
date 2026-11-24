"""Síntesis anticipada por oraciones para el flujo de voz.

Una frase que llega completa al pipeline no debe esperar a que se sintetice
todo un párrafo: se divide por oraciones y la primera entra de inmediato a la
cola de ``Voz``, de modo que suene mientras se genera/sintetiza la siguiente.
"""
from voz import dividir_frases, normalizar_emocion


def oraciones(texto):
    """Devuelve la lista de oraciones, reutilizando el separador de ``voz.py``."""
    if not texto:
        return []
    texto = str(texto).strip()
    try:
        return [p for p in dividir_frases(texto) if p]
    except Exception:
        return [texto]


def primera_oracion(texto):
    """Primera oración completa de un texto (o ``""`` si no hay ninguna)."""
    bloques = oraciones(texto)
    return bloques[0] if bloques else ""


def agregar_bloques(flujo, texto, emocion=None):
    """Encola cada oración por separado y devuelve los bloques agregados."""
    bloques = oraciones(texto)
    for bloque in bloques:
        flujo.agregar(bloque, emocion=emocion)
    return bloques


def hablar_en_bloques(voz, texto, al_terminar=None, emocion=None,
                      cerrar=True, **opciones):
    """Crea un flujo y encola la primera oración antes de devolver.

    El productor/consumidor de ``Voz`` sintetiza la oración siguiente mientras
    se reproduce la actual. Esta función solo prepara la cola; no bloquea.
    """
    emo = normalizar_emocion(emocion) if emocion else "neutral"
    flujo = voz.flujo(al_terminar, emocion=emo, **opciones)
    agregar_bloques(flujo, texto, emocion=emo)
    if cerrar:
        flujo.cerrar()
    return flujo


def iniciar_stream(voz, primera_frase, al_terminar=None, emocion=None, **opciones):
    """Arranca el flujo de streaming con su primera frase ya encolada."""
    emo = normalizar_emocion(emocion) if emocion else "neutral"
    flujo = voz.flujo(al_terminar, emocion=emo, **opciones)
    if primera_frase:
        agregar_bloques(flujo, primera_frase, emocion=emo)
    return flujo


__all__ = [
    "oraciones", "primera_oracion", "agregar_bloques",
    "hablar_en_bloques", "iniciar_stream",
]
