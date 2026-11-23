"""Rearme diferido del micrófono tras acciones de sistema.

El fin_voz de la respuesta del LLM puede llegar mientras la frase de la acción
sigue hablando. Rearmar a ciegas deja la conversación colgada: el micrófono se
abre durante el TTS y ningún evento posterior vuelve a abrirlo. Este módulo
espera a que la voz esté realmente libre antes de llamar a escuchar().
"""
import time


def rearmar(app):
    """Rearma la escucha solo cuando la voz terminó, con tope de espera."""
    if not getattr(app, "conversacion", False) or getattr(app, "escuchando", False):
        return
    app._rearme_activo = True
    app._rearme_intentos = 0
    limite = time.monotonic() + 15.0

    def _hacer():
        voz = getattr(app, "voz", None)
        if (voz is not None and hasattr(voz, "ocupada") and voz.ocupada()
                and time.monotonic() < limite):
            raiz = getattr(getattr(app, "cara", None), "root", None)
            if raiz is not None and hasattr(raiz, "after"):
                raiz.after(300, _hacer)
            return
        app._rearme_activo = False
        if getattr(app, "conversacion", False) and not getattr(app, "escuchando", False):
            soltar = getattr(app, "_dejar_de_escuchar", None)
            if soltar is not None:
                soltar()
            app.escuchar()
        # Sincronizar el aro con el estado real: quedar en azul tras la accion
        # significa que la cara se quedo desincronizada de app.escuchando.
        cara = getattr(app, "cara", None)
        if cara is not None and hasattr(cara, "poner_escuchando"):
            cara.poner_escuchando(bool(getattr(app, "escuchando", False)))

    raiz = getattr(getattr(app, "cara", None), "root", None)
    if raiz is not None and hasattr(raiz, "after"):
        raiz.after(700, _hacer)
    else:
        _hacer()
