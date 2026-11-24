"""Síntesis anticipada por oraciones para el flujo de voz.

Una frase que llega completa al pipeline no debe esperar a que se sintetice
todo un párrafo: se divide por oraciones y la primera entra de inmediato a la
cola de ``Voz``, de modo que suene mientras se genera/sintetiza la siguiente.
"""
from cerebro_parser import limpiar_etiquetas
from voz import dividir_frases, normalizar_emocion


def oraciones(texto):
    """Devuelve la lista de oraciones, reutilizando el separador de ``voz.py``."""
    if not texto:
        return []
    texto = limpiar_etiquetas(texto)
    if not texto:
        return []
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


def texto_hablable(texto):
    """Texto listo para TTS: sin etiquetas internas ni bloques ``<think>``."""
    return limpiar_etiquetas(texto)


def garantizar_voz(app, texto, emocion=None):
    """Habla el texto final cuando el turno no emitió ningún fragmento.

    Cierra un flujo vacío, limpia etiquetas y encola ``fin_voz`` al terminar,
    de modo que la app nunca se quede con la voz ocupada ni en silencio.
    """
    limpio = limpiar_etiquetas(texto)
    if not limpio or getattr(app, "_fragmentos_voz", False):
        return False
    flujo = getattr(app, "flujo", None)
    if flujo is not None:
        try:
            flujo.cerrar()
        except Exception:
            pass
        app.flujo = None
    emo = emocion or "neutral"
    app._fragmentos_voz = True
    app.ultimo_dicho = limpio
    cara = getattr(app, "cara", None)
    if cara is not None:
        try:
            if hasattr(cara, "fijar_emocion"):
                cara.fijar_emocion(emo)
            cara.decir(limpio, None, emocion=emo)
        except Exception:
            pass
    try:
        fin = lambda: app.cola.put(("fin_voz", None))
        app.voz.hablar(limpio, fin, emocion=emo)
    except Exception:
        try:
            app.decir(limpio, emocion=emo)
        except Exception:
            pass
    return True


def iniciar_stream(voz, primera_frase, al_terminar=None, emocion=None, **opciones):
    """Arranca el flujo de streaming con su primera frase ya encolada."""
    emo = normalizar_emocion(emocion) if emocion else "neutral"
    flujo = voz.flujo(al_terminar, emocion=emo, **opciones)
    if primera_frase:
        agregar_bloques(flujo, primera_frase, emocion=emo)
    return flujo


__all__ = [
    "oraciones", "primera_oracion", "agregar_bloques",
    "hablar_en_bloques", "iniciar_stream", "texto_hablable",
    "garantizar_voz",
]
