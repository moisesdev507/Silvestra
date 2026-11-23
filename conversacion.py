"""Lógica de conversación, escucha por micrófono y chat para Silvestra.

Maneja el reconocimiento con Whisper, filtrado de eco, entrada por texto
y la generación en streaming de respuestas mediante Groq.
"""
import difflib
import threading
import time
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
        print(f"[oido] Descartado como eco (repetición): '{texto[:40]}'", flush=True)
        return True
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio > 0.85:
        print(f"[oido] Descartado como eco (ratio={ratio:.2f}): '{texto[:40]}'", flush=True)
        return True
    return False


def dejar_de_escuchar(app):
    """Apaga el estado de escucha y el indicador visual en la cara."""
    app._generacion_escucha = getattr(app, "_generacion_escucha", 0) + 1
    app.escuchando = False
    app.cara.poner_escuchando(False)
    if getattr(app, "musica_activa", False):
        try:
            import control_laptop
            if not getattr(getattr(app, "voz", None), "ocupada", lambda: False)():
                control_laptop.restaurar_ducking()
        except Exception:
            pass


def escuchar(app):
    """Comienza a escuchar por el micrófono si la conversación está activa (soporta barge-in)."""
    if app.escuchando or not app.conversacion:
        return
    app._generacion_escucha = getattr(app, "_generacion_escucha", 0) + 1
    generacion = app._generacion_escucha
    app.escuchando = True
    app.cara.poner_escuchando(True)
    if getattr(app, "musica_activa", False):
        try:
            import control_laptop
            control_laptop.aplicar_ducking()
        except Exception:
            pass
    threading.Thread(target=grabar, args=(app, generacion), daemon=True).start()


def grabar(app, generacion=None):
    """Captura el audio con Whisper y encola el resultado (se ejecuta en hilo aparte)."""
    try:
        texto = app.oido.escuchar(app=app, generacion=generacion)
    except Exception as e:
        if generacion is not None and generacion != getattr(app, "_generacion_escucha", generacion):
            return
        app.cola.put(("fallo", str(e)))
        return
    if (generacion is not None and generacion != getattr(app, "_generacion_escucha", generacion)):
        print("[oido] Descartado: sesión de escucha reiniciada", flush=True)
        return
    if not getattr(app, "conversacion", False) and not getattr(app, "escuchando", False):
        print("[oido] Descartado: conversación detenida", flush=True)
        return
    app.cola.put(("silencio", None) if texto is None else ("oido", texto))


def alternar_conversacion(app, motivo="desconocido"):
    """Enciende o apaga la conversación continua por voz."""
    if not app.memoria.nombre:
        return
    app.conversacion = not app.conversacion
    app.silencios = 0
    print(f"[conversacion] alternar_conversacion motivo='{motivo}' nuevo_estado={'escuchando' if app.conversacion else 'silencio'}", flush=True)
    if app.conversacion:
        app.decir("Te escucho. Háblame.", 2500)
        escuchar(app)
    else:
        dejar_de_escuchar(app)
        app.decir("Listo, dejo de escuchar.", 2500)
        app._iniciar_reflexion()


def despertar(app):
    """Sale del reposo y difiere la restauración visual a la cola Qt."""
    app.descansando = False
    app.pendiente_descanso = False
    app.conversacion = True
    app.silencios = 0
    app.cola.put(("restaurar_ventanas", None))
    app.decir(f"Aquí estoy, {app.memoria.creador}. Dime.", 3000)


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
    t_habla = getattr(getattr(app, "oido", None), "t_fin_habla", getattr(getattr(app, "oido", None), "t_fin_escucha", time.time()))
    t_txt = getattr(getattr(app, "oido", None), "t_texto", time.time())
    app.t_fin_habla = t_habla
    app.metricas_turno = {"t_fin_habla": t_habla, "t_texto": t_txt, "t_primer_token": None}

    try:
        import naturalidad
        naturalidad.registrar_turno_usuario(texto)
    except Exception:
        pass

    # Detección de turno de invitado no verificado
    es_invitado = bool(
        getattr(app, "origen_entrada_actual", "chat") == "microfono"
        and hasattr(app, "voz_dueno")
        and getattr(app.voz_dueno, "activa", False)
        and not getattr(app.voz_dueno, "ultima_verificacion", {}).get("es_dueno", True)
    )
    if hasattr(app, "cerebro"):
        app.cerebro.turno_invitado = es_invitado
    if hasattr(app, "memoria"):
        app.memoria.bloqueo_invitado = es_invitado

    if hasattr(app, "iniciativa"):
        app.iniciativa.interaccion()
    if hasattr(app, "cuidado") and app.cuidado:
        try:
            app.cuidado.notificar_senal_usuario("laptop", texto)
        except Exception:
            pass
    app.cara.decir(f"«{texto}»", 60000)

    t_norm = normalizar(texto).strip()

    if hasattr(app, "control_seguridad") and app.control_seguridad.tiene_pendiente():
        if "cancelar" in t_norm:
            app.control_seguridad.limpiar_pendiente()
            app.decir("Acción cancelada.", 2500)
            return
        if app.control_seguridad.verificar_codigo(texto):
            return

    try:
        import control_seguridad
        if control_seguridad.es_accion_prohibida(texto):
            control_seguridad.registrar_log("PROHIBIDO", "texto_prohibido", getattr(app, "origen_entrada_actual", "desconocido"), "RECHAZADO")
            app.decir("Esa acción está prohibida por seguridad.", 3000)
            return
    except Exception:
        pass

    if t_norm in ("para", "silencio", "callate", "alto", "stop", "ya"):
        if getattr(app, "musica_activa", False):
            if len(t_norm.split()) > 2:
                return
            import config
            if getattr(config, "VERIFICAR_DUENO_CON_MUSICA", True):
                uv = getattr(getattr(app, "voz_dueno", None), "ultima_verificacion", {})
                if hasattr(app, "voz_dueno") and getattr(app.voz_dueno, "activa", False) and not uv.get("es_dueno", False):
                    return
            app.musica_activa = False
            try:
                import control_laptop
                control_laptop.restaurar_ducking()
            except Exception:
                pass
        if hasattr(app, "voz") and hasattr(app.voz, "detener"):
            app.voz.detener()
        app.decir("Listo, me callo.", 2000)
        return

    if t_norm in ("espera", "un momento", "aguanta"):
        if hasattr(app, "voz") and hasattr(app.voz, "detener"):
            app.voz.detener("comando_espera")
        app.decir("Te escucho, dime.", 2500)
        return

    if t_norm in ("deja de escuchar", "dejar de escuchar", "apaga el microfono", "deja de oir"):
        if getattr(app, "musica_activa", False):
            if len(t_norm.split()) > 4:
                return
            import config
            if getattr(config, "VERIFICAR_DUENO_CON_MUSICA", True):
                uv = getattr(getattr(app, "voz_dueno", None), "ultima_verificacion", {})
                if hasattr(app, "voz_dueno") and getattr(app.voz_dueno, "activa", False) and not uv.get("es_dueno", False):
                    return
        if app.conversacion:
            app.alternar_conversacion(motivo="comando_voz_deja_de_escuchar")
        return

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
    try:
        import correcciones
        if correcciones.es_correccion(texto):
            correcciones.registrar_correccion(getattr(app, "ultimo_dicho", ""), texto)
    except Exception as e:
        print(f"[correcciones] Error detectando corrección: {e}", flush=True)

    if getattr(app.oido, "debe_avisar_respaldo", False):
        app.oido.debe_avisar_respaldo = False
        app.cola.put(("frase", "Te escucho con mi oído de respaldo."))
    import config
    muletillas_activas = getattr(config, "MULETILLAS_ACTIVAS", False)
    timer_espera = None
    if muletillas_activas:
        umbral_espera = getattr(config, "UMBRAL_MULETILLA_SEGUNDOS", 0.30)
        timer_espera = threading.Timer(
            umbral_espera,
            lambda: getattr(app, "voz", None) and hasattr(app.voz, "soltar_espera") and app.voz.soltar_espera()
        )
        timer_espera.daemon = True
        timer_espera.start()

    try:
        def _on_token():
            if timer_espera:
                timer_espera.cancel()
            if hasattr(app, "metricas_turno") and isinstance(app.metricas_turno, dict):
                if app.metricas_turno.get("t_primer_token") is None:
                    app.metricas_turno["t_primer_token"] = time.time()

        resultado = respuesta_flujo.responder_flujo(
            app.cerebro, texto, lambda f: app.cola.put(("frase", f)), on_primer_token=_on_token
        )
        if timer_espera:
            timer_espera.cancel()
        try:
            import naturalidad
            naturalidad.registrar_turno_asistente(resultado)
        except Exception:
            pass
        app.cola.put(("respuesta", resultado))
    except Exception as e:
        if timer_espera:
            timer_espera.cancel()
        app.cola.put(("error", str(e)[:200]))


def instalar(app):
    """Registra acciones de conversación y control de voz."""
    import acciones

    def _accion_silencio(arg=None):
        if hasattr(app, "voz") and hasattr(app.voz, "detener"):
            app.voz.detener()
        return True, "Silencio activado."

    desc = "Detiene la voz de Silvestra de inmediato."
    for nom in ("silencio", "para", "callate", "callar"):
        acciones.registrar(nom, _accion_silencio, desc)

