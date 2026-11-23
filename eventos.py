"""Cola de eventos: Qt ejecuta los cambios de UI."""
import time


def respuesta_requiere_hablar(app, n_frases):
    """True si el flujo activo no emitió frases y la respuesta debe hablarse."""
    return getattr(app, "flujo", None) is not None and not n_frases


def es_confirmacion_rutinaria(texto):
    if not texto:
        return True
    t = str(texto).strip().lower()

    alertas = (
        "error", "fallo", "falló", "no pude", "no puedo", "no se pudo", "no está", "no esta",
        "no existe", "no encontré", "no encontre", "no tengo", "bloquead", "prohibid",
        "cuidado", "advertencia", "contraseña", "seguridad", "invalido", "inválido", "rechazad"
    )
    if any(a in t for a in alertas):
        return False

    datos = (
        "recordatorio vencido", "te leo", "resumen:", "última entrada", "ultima entrada",
        "son las ", "la hora es", "el clima", "temperatura", "grados", "noticia", "diario:"
    )
    if any(d in t for d in datos):
        return False

    rutinas = (
        "panel jarvis listo", "subiendo volumen", "bajando volumen", "cambiando silencio",
        "pausando o reanudando", "siguiente canción", "cancion anterior", "canción anterior",
        "abriendo ", "pantalla remota desactivada", "modo privado de la tablet",
        "modo normal de la tablet", "detección de presencia", "deteccion de presencia",
        "subiendo brillo", "bajando brillo", "listo", "hecho", "anotado", "abierto",
        "cerrado", "activado", "desactivado"
    )
    if any(r in t for r in rutinas):
        return True

    return len(t) <= 30


def atender_evento(app, tipo, texto):
    if tipo == "frase":
        if isinstance(texto, (tuple, list)):
            frase_txt = str(texto[0])
            frase_emo = texto[1] if len(texto) > 1 else None
        else:
            frase_txt = str(texto)
            frase_emo = None
        if frase_emo and hasattr(app, "cara") and app.cara:
            app.cara.fijar_emocion(frase_emo)
        if getattr(app, "musica_activa", False):
            try:
                import control_laptop
                control_laptop.aplicar_ducking()
            except Exception:
                pass
        if hasattr(app, "escenario") and app.escenario and app.escenario.isVisible():
            app.escenario.actualizar_subtitulo(frase_txt)
        if app.flujo is None:
            app.texto_flujo = ""
            app._frases_flujo_emitidas = 0
            t_fin = getattr(app, "t_fin_habla", None)
            if t_fin and (time.time() - t_fin > 30.0 or getattr(app, "_ecosistema_origen", None)):
                t_fin, app.t_fin_habla, app.metricas_turno = None, None, None
            metricas = getattr(app, "metricas_turno", None)
            t_in_txt = getattr(app, "t_inicio_texto", None)
            app.flujo = app.voz.flujo(
                lambda: app.cola.put(("fin_voz", None)),
                emocion=frase_emo or "neutral",
                t_fin_habla=t_fin,
                metricas=metricas,
                t_inicio_texto=t_in_txt,
            )
            app.t_inicio_texto = None
        app.texto_flujo = (app.texto_flujo + " " + frase_txt).strip()
        app.flujo.agregar(frase_txt, emocion=frase_emo)
        app._frases_flujo_emitidas = getattr(app, "_frases_flujo_emitidas", 0) + 1
        if "?" in frase_txt or "¿" in frase_txt:
            try:
                import voz_gracia
                voz_gracia.registrar_pregunta(app)
            except Exception:
                pass
        app.cara.decir(app.texto_flujo, None, emocion=frase_emo)

    elif tipo == "escenario_subtitulo":
        if hasattr(app, "escenario") and app.escenario:
            app.escenario.actualizar_subtitulo(texto)

    elif tipo == "escenario_paso":
        if hasattr(app, "escenario") and app.escenario:
            app.escenario.avanzar_paso(texto)

    elif tipo == "escenario_captura":
        if hasattr(app, "escenario") and app.escenario:
            app.escenario.fijar_captura(texto)

    elif tipo == "escenario_gesto":
        if hasattr(app, "escenario") and app.escenario:
            app.escenario.registrar_gesto(texto)

    elif tipo == "saludo_invitado":
        if hasattr(app, "escenario") and app.escenario and app.escenario.isVisible():
            app.escenario.actualizar_subtitulo(texto)
        app.decir(texto, 4500)

    elif tipo == "saludo_inicial":
        txt_s, emo_s = texto if isinstance(texto, tuple) else (str(texto), "calida")
        app.decir(txt_s, emocion=emo_s)

    elif tipo == "interrupcion":
        if app.flujo is not None:
            try:
                app.flujo.cerrar()
            except Exception:
                pass
            app.flujo = None
            app._frases_flujo_emitidas = 0
        app.ultimo_dicho = ""
        if hasattr(app, "cara") and app.cara:
            app.cara.poner_escuchando(True)

    elif tipo == "respuesta":
        remoto = getattr(app, "_ecosistema_origen", None)
        if remoto and getattr(app, "pantalla_remota", None):
            app.pantalla_remota.puente.reservar_turno(remoto, cerrar=True)
        if isinstance(texto, (list, tuple)):
            if len(texto) >= 3:
                respuesta, accion, emocion = texto[0], texto[1], texto[2]
            elif len(texto) == 2:
                respuesta, accion = texto[0], texto[1]
                emocion = "neutral"
            else:
                respuesta = texto[0]
                accion = None
                emocion = "neutral"
        else:
            respuesta, accion, emocion = str(texto), None, "neutral"

        if respuesta is None or not str(respuesta).strip():
            return

        if accion and remoto:
            import ecosistema_eventos
            if not ecosistema_eventos.accion_autorizada_remota(app, remoto, accion):
                app._ecosistema_origen = None
                ecosistema_eventos.bloquear_accion_remota(app, remoto, accion)
                return

        if accion and hasattr(app, "voz_dueno") and app.voz_dueno:
            permitido, frase_negativa = app.voz_dueno.autorizar_accion(accion)
            if not permitido:
                if app.flujo is not None:
                    app.flujo.cerrar()
                    app.flujo = None
                app.ultimo_dicho = frase_negativa
                app.cara.decir(frase_negativa, None)
                app.decir(frase_negativa, emocion="calida")
                return

        n_frases = getattr(app, "_frases_flujo_emitidas", 0)
        if respuesta_requiere_hablar(app, n_frases):
            # El streaming creó un flujo pero no sintetizó ninguna frase: hablar aquí
            # evita que la respuesta quede solo en pantalla.
            app.flujo.cerrar()
            app.flujo = None
            app._frases_flujo_emitidas = 0
            app.decir(respuesta, emocion=emocion)
        elif app.flujo is not None:
            app.flujo.cerrar()
            app.ultimo_dicho = respuesta
            if hasattr(app, "cara") and app.cara:
                app.cara.fijar_emocion(emocion)
            app.cara.decir(respuesta, None, emocion=emocion)
        else:
            app.decir(respuesta, emocion=emocion)
        if accion:
            if respuesta and str(respuesta).strip():
                app._t_accion_llm = time.time()
            app.ejecutar(accion)
        if remoto:
            app._ecosistema_origen = None

    elif tipo == "emocion":
        if hasattr(app, "cara") and app.cara:
            app.cara.fijar_emocion(texto)

    elif tipo == "despertar":
        app.despertar()

    elif tipo == "restaurar_ventanas":
        import casa
        casa.restaurar_ventanas(app)

    elif tipo == "alternar_conversacion":
        motivo = texto or "evento"
        app.silencios = 0
        if not app.conversacion:
            app.alternar_conversacion(motivo=motivo)

    elif tipo == "mirando_pantalla":
        app.cara.decir("Mirando la pantalla...", 4000)

    elif tipo == "telegram_codigo":
        app.decir(f"Código de Telegram: {texto}")

    elif tipo == "telegram_vinculado":
        app.decir("Telegram vinculado con éxito.", 4000)

    elif tipo == "telegram_burbuja":
        app.cara.decir(texto, 4000)

    elif tipo == "multimodal_situacion":
        import qt_estabilidad_ui
        if qt_estabilidad_ui.puede_actualizar_ui() and getattr(app, "cara", None):
            app.cara.decir(str(texto)[:550], 4000)

    elif tipo == "presencia_modo_discreto":
        discreto = bool(texto)
        if hasattr(app, "cara") and app.cara:
            if discreto:
                if hasattr(app.cara, "burbuja") and app.cara.burbuja:
                    try:
                        app.cara.burbuja.hide()
                    except Exception:
                        pass
                app.cara.hide()
            else:
                try:
                    import qt_estabilidad_ui
                    if not qt_estabilidad_ui.puede_actualizar_ui():
                        return
                    app.cara.setWindowOpacity(0.0)
                    app.cara.show()
                    app.cara.raise_()

                    def _animar_aparicion(op):
                        if hasattr(app, "cara") and app.cara:
                            op = min(1.0, op + 0.15)
                            app.cara.setWindowOpacity(op)
                            if op < 1.0:
                                app.cara.root.after(30, lambda: _animar_aparicion(op))

                    _animar_aparicion(0.0)
                except Exception:
                    try:
                        app.cara.show()
                        app.cara.raise_()
                    except Exception:
                        pass

    elif tipo == "texto_tablet":
        if isinstance(texto, dict):
            app._ecosistema_origen = texto.get("identity")
            app.dispositivo_entrada_actual = (texto.get("device_id"), texto.get("tipo_dispositivo"))
            texto = texto.get("texto", "")
        app._t_accion_llm = 0
        app.origen_entrada_actual = "chat"
        app.t_fin_habla, app.t_inicio_texto = None, time.time()
        if hasattr(app, "iniciativa"):
            app.iniciativa.interaccion()
        app.enviar(texto)

    else:
        import eventos_dialogo
        eventos_dialogo.atender_resto(app, tipo, texto, es_confirmacion_rutinaria)
