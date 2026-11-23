"""Voz de eventos: streaming del LLM y frases sueltas de acciones.

Las frases del LLM se acumulan en ``app.flujo`` y se cierran con ``respuesta``.
Las frases de acción llegan después de ese cierre: se hablan en un flujo propio
que se cierra de inmediato y emite ``fin_voz`` al terminar, sin dejar
``voz.ocupada()`` colgado ni el aro en azul.
"""
import time


def _suelta(app, frase, emo, al_terminar):
    """Habla una frase puntual en un flujo autocerrado."""
    flujo = app.voz.flujo(al_terminar, emocion=emo or "neutral")
    flujo.agregar(frase, emocion=emo)
    flujo.cerrar()
    if getattr(app, "cara", None):
        app.cara.decir(frase, None, emocion=emo)


def suelta(app, texto, emo=None):
    """Frase de acción o registro: cierre garantizado y ``fin_voz``."""
    _suelta(app, texto, emo, lambda: app.cola.put(("fin_voz", None)))


def frase(app, frase_txt, frase_emo=None):
    """Encadena el streaming del LLM o habla una frase suelta de acción."""
    if app.flujo is None and not getattr(app, "_flujo_cerrado", False):
        app.texto_flujo = ""
        t_fin = getattr(app, "t_fin_habla", None)
        if t_fin and (time.time() - t_fin > 30.0 or getattr(app, "_ecosistema_origen", None)):
            t_fin, app.t_fin_habla, app.metricas_turno = None, None, None
        app.flujo = app.voz.flujo(
            lambda: app.cola.put(("fin_voz", None)),
            emocion=frase_emo or "neutral",
            t_fin_habla=t_fin,
            metricas=getattr(app, "metricas_turno", None),
            t_inicio_texto=getattr(app, "t_inicio_texto", None),
        )
        app.t_inicio_texto = None
    if getattr(app, "_flujo_cerrado", False) or app.flujo is None:
        suelta(app, frase_txt, frase_emo)
        return
    app.texto_flujo = (app.texto_flujo + " " + frase_txt).strip()
    app.flujo.agregar(frase_txt, emocion=frase_emo)
    app.cara.decir(app.texto_flujo, None, emocion=frase_emo)
