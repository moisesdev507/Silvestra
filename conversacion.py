"""Lógica de conversación, escucha por micrófono y chat para Silvestra.

Maneja el reconocimiento con Whisper, filtrado de eco, entrada por texto
y la generación en streaming de respuestas mediante Groq.
"""
import difflib
import threading
import unicodedata

import respuesta_flujo


def normalizar(texto):
    """Quita tildes y convierte a minúsculas para comparaciones flexibles."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def es_eco(app, texto):
    """True si lo que 'oyó' es ella misma (su propia voz por los parlantes)."""
    a = normalizar(texto).strip()
    b = normalizar(app.ultimo_dicho).strip()
    if not a or not b:
        return False
    if len(a) >= 12 and a in b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.6


def dejar_de_escuchar(app):
    """Apaga el estado de escucha y el indicador visual en la cara."""
    app.escuchando = False
    app.cara.poner_escuchando(False)


def escuchar(app):
    """Comienza a escuchar por el micrófono si la conversación está activa y la voz libre."""
    if app.escuchando or not app.conversacion:
        return
    if app.voz.ocupada():
        app.cara.root.after(400, lambda: escuchar(app))
        return
    app.escuchando = True
    app.cara.poner_escuchando(True)
    threading.Thread(target=grabar, args=(app,), daemon=True).start()


def grabar(app):
    """Captura el audio con Whisper y encola el resultado (se ejecuta en hilo aparte)."""
    try:
        texto = app.oido.escuchar()
    except Exception as e:
        app.cola.put(("fallo", str(e)))
        return
    app.cola.put(("silencio", None) if texto is None else ("oido", texto))


def alternar_conversacion(app):
    """Enciende o apaga la conversación continua por voz."""
    if not app.memoria.nombre:
        return
    app.conversacion = not app.conversacion
    app.silencios = 0
    if app.conversacion:
        app.decir("Te escucho. Háblame.", 2500)
    else:
        app.decir("Listo, dejo de escuchar.", 2500)
        app._iniciar_reflexion()


def abrir_chat(app):
    """Abre la ventana flotante para escribirle por texto."""
    if not app.memoria.nombre:
        return

    def _enviar_chat(texto):
        app.origen_entrada_actual = "chat"
        app.enviar(texto)

    app.cara.abrir_entrada(f"Hablar con {app.memoria.nombre}", _enviar_chat)


def enviar(app, texto):
    """Procesa un texto enviado por el usuario (por voz o por teclado)."""
    if hasattr(app, "iniciativa"):
        app.iniciativa.interaccion()
    if hasattr(app, "cuidado") and app.cuidado:
        try:
            app.cuidado.notificar_senal_usuario("laptop", texto)
        except Exception:
            pass
    app.cara.decir(f"«{texto}»", 60000)

    t_norm = normalizar(texto)
    if "cancelar" in t_norm:
        try:
            import voz_dueno_registro
            if voz_dueno_registro.esta_activo():
                voz_dueno_registro.cancelar()
                return
        except Exception:
            pass

    if "dejame trabajar" in t_norm:
        if getattr(app.oido, "debe_avisar_respaldo", False):
            app.oido.debe_avisar_respaldo = False
            app.decir("Te escucho con mi oído de respaldo. Entendido, te dejo trabajar tranquilo. Desactivé mi iniciativa.", 3500)
            return
        if hasattr(app, "iniciativa"):
            app.iniciativa.desactivar()
        app.decir("Entendido, te dejo trabajar tranquilo. Desactivé mi iniciativa.", 3500)
        return

    if hasattr(app, "estudio") and app.estudio.en_examen():
        app.estudio.responder_examen(texto)
        return

    threading.Thread(target=pensar, args=(app, texto), daemon=True).start()


def pensar(app, texto):
    """Llama al cerebro en streaming y envía los fragmentos a la cola (en hilo aparte)."""
    if getattr(app.oido, "debe_avisar_respaldo", False):
        app.oido.debe_avisar_respaldo = False
        app.cola.put(("frase", "Te escucho con mi oído de respaldo."))
    try:
        resultado = respuesta_flujo.responder_flujo(
            app.cerebro, texto, lambda f: app.cola.put(("frase", f))
        )
        app.cola.put(("respuesta", resultado))
    except Exception as e:
        app.cola.put(("error", str(e)[:200]))
