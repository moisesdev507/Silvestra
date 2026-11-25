"""Cola de eventos: Qt ejecuta los cambios de UI."""
import time

import conversacion
import eventos_voz
import invocacion_lyris
import sonidos_ui
import voz_stream


def es_confirmacion_rutinaria(texto):
    if not texto:
        return True
    t = str(texto).strip().lower()

    alertas = (
        "error", "fallo", "falló", "no pude", "no puedo", "no se pudo", "no está", "no esta",
        "no existe", "no encontré", "no encontre", "no tengo", "bloquead", "prohibid",
        "cuidado", "advertencia", "contraseña", "seguridad", "invalido", "inválido", "rechazad",
    )
    if any(a in t for a in alertas):
        return False
    datos = (
        "recordatorio vencido", "te leo", "resumen:", "última entrada", "ultima entrada",
        "son las ", "la hora es", "el clima", "temperatura", "grados", "noticia", "diario:",
    )
    if any(d in t for d in datos):
        return False
    rutinas = (
        "panel jarvis listo", "subiendo volumen", "bajando volumen", "cambiando silencio",
        "pausando o reanudando", "siguiente canción", "cancion anterior", "canción anterior",
        "abriendo ", "pantalla remota desactivada", "modo privado de la tablet",
        "modo normal de la tablet", "detección de presencia", "deteccion de presencia",
        "subiendo brillo", "bajando brillo", "listo", "hecho", "anotado", "abierto",
        "cerrado", "activado", "desactivado",
    )
    if any(r in t for r in rutinas):
        return True

    return len(t) <= 30


def atender_evento(app, tipo, texto):
    if invocacion_lyris.interceptar(app, tipo, texto):
        return
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
        eventos_voz.frase(app, frase_txt, frase_emo)

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
        app.ultimo_dicho = ""
        if hasattr(app, "cara") and app.cara:
            app.cara.poner_escuchando(True)

    elif tipo == "respuesta":
        app._flujo_cerrado = True
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

        texto_hablable = voz_stream.texto_hablable(respuesta)
        hablado_fallback = voz_stream.garantizar_voz(app, texto_hablable, emocion)
        if not hablado_fallback and app.flujo is not None:
            app.flujo.cerrar()
            if texto_hablable:
                app.ultimo_dicho = texto_hablable
                if hasattr(app, "cara") and app.cara:
                    app.cara.fijar_emocion(emocion)
                app.cara.decir(texto_hablable, None, emocion=emocion)
        elif not hablado_fallback and texto_hablable:
            app.decir(texto_hablable, emocion=emocion)
        elif not hablado_fallback:
            app.cola.put(("fin_voz", None))
        if accion:
            if respuesta and str(respuesta).strip():
                app._t_accion_llm = time.time()
            sonidos_ui.reproducir("accion")
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

    elif tipo == "ejecutar_accion":
        app._t_accion_llm = 0
        sonidos_ui.reproducir("accion")
        app.ejecutar(texto)

    elif tipo == "hablar":
        msg = texto[0] if isinstance(texto, (list, tuple)) else str(texto)
        emo = texto[1] if isinstance(texto, (list, tuple)) and len(texto) > 1 else None

        t_llm = getattr(app, "_t_accion_llm", 0)
        if (t_llm and (time.time() - t_llm < 4.0)
                and getattr(app, "_fragmentos_voz", False)):
            if es_confirmacion_rutinaria(msg):
                print(f"[eventos] Omitiendo confirmacion hablada duplicada de accion: '{msg}'", flush=True)
                return

        if isinstance(texto, (list, tuple)):
            app.decir(msg, emocion=emo)
        else:
            app.decir(texto)

    elif tipo == "hablar_registro":
        voz_txt, burbuja_txt = texto
        if burbuja_txt:
            app.cara.decir(burbuja_txt, None)
        if voz_txt:
            t_llm = getattr(app, "_t_accion_llm", 0)
            if (t_llm and (time.time() - t_llm < 4.0)
                    and getattr(app, "_fragmentos_voz", False)):
                if es_confirmacion_rutinaria(voz_txt):
                    print(f"[eventos] Omitiendo voz duplicada en hablar_registro: '{voz_txt}'", flush=True)
                    return
            app.ultimo_dicho = voz_txt
            eventos_voz.suelta(app, voz_txt)

    elif tipo == "copiar_portapapeles":
        copiado = False
        try:
            from PySide6.QtGui import QGuiApplication
            clip = QGuiApplication.clipboard()
            if clip:
                clip.setText(texto)
                copiado = True
        except Exception:
            pass
        if not copiado:
            try:
                import subprocess
                p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
                p.communicate(input=str(texto).encode("utf-16le"))
            except Exception:
                pass

    elif tipo == "hud_clima":
        if hasattr(app, "hud") and app.hud:
            app.hud.actualizar_clima(texto)
        app.ultimo_clima = texto

    elif tipo == "fin_voz":
        conversacion.fin_voz(app)

    elif tipo == "oido":
        app._t_accion_llm = 0
        app._fragmentos_voz = False
        app._flujo_cerrado = False
        if hasattr(app, "iniciativa"):
            app.iniciativa.interaccion()
        app._dejar_de_escuchar()
        conversacion.registrar_orden_wakeword(app)
        if hasattr(app, "cara") and hasattr(app.cara, "asentir"):
            app.cara.asentir(0.55)
        if app.conversacion:
            app.silencios = 0
            if app._es_eco(texto):
                app.escuchar()
            else:
                app.origen_entrada_actual = "microfono"
                if hasattr(app, "voz_dueno") and app.voz_dueno:
                    app.voz_dueno.evaluar_entrada_voz(texto)
                vd = getattr(app, "voz_dueno", None)
                if vd and getattr(vd, "activa", False):
                    uv = getattr(vd, "ultima_verificacion", {})
                    if not uv.get("es_dueno", True) and getattr(vd, "modo_solo_dueno", False):
                        print("[voz_dueno] Audio de invitado ignorado (modo solo dueño)", flush=True)
                        app.escuchar()
                        return
                if getattr(app, "musica_activa", False) and getattr(config, "VERIFICAR_DUENO_CON_MUSICA", True):
                    uv = getattr(getattr(app, "voz_dueno", None), "ultima_verificacion", {})
                    if hasattr(app, "voz_dueno") and getattr(app.voz_dueno, "activa", False) and not uv.get("es_dueno", False):
                        print(f"[oido] Audio ignorado durante música (no verificado como dueño CAM++): '{texto[:40]}'", flush=True)
                        app.escuchar()
                        return
                sonidos_ui.reproducir("captado")
                app.enviar(texto)

    elif tipo == "silencio":
        app._dejar_de_escuchar()
        if getattr(app, "turno_wakeword", False):
            conversacion.cerrar_turno(app, "silencio")
            return
        hablando = bool(hasattr(app, "voz") and app.voz.ocupada())
        if not hablando:
            app.silencios += 1
        if app.conversacion:
            en_demo = bool(
                (hasattr(app, "escenario") and app.escenario and app.escenario.isVisible())
                or getattr(app, "presentacion_activa", False)
            )
            limite = 5 if en_demo else 3
            if app.silencios >= limite:
                app.conversacion = False
                app.decir("Me quedo callada. Avísame cuando quieras hablar.", 3500)
                app._iniciar_reflexion()
            else:
                app.escuchar()

    elif tipo == "texto_tablet":
        if isinstance(texto, dict):
            app._ecosistema_origen = texto.get("identity")
            app.dispositivo_entrada_actual = (texto.get("device_id"), texto.get("tipo_dispositivo"))
            texto = texto.get("texto", "")
        app._t_accion_llm = 0
        app._fragmentos_voz = False
        app._flujo_cerrado = False
        app.origen_entrada_actual = "chat"
        app.t_fin_habla, app.t_inicio_texto = None, time.time()
        if hasattr(app, "iniciativa"):
            app.iniciativa.interaccion()
        app.enviar(texto)

    elif tipo in ("ecosistema_observacion", "ecosistema_mostrar_qr"):
        import ecosistema_eventos
        ecosistema_eventos.procesar(app, tipo, texto)
    elif tipo == "subtitulo":
        app.decir(str(texto), 5000, con_voz=False)

    elif tipo in ("error", "fallo"):
        remoto = getattr(app, "_ecosistema_origen", None)
        if remoto and getattr(app, "pantalla_remota", None):
            app.pantalla_remota.puente.reservar_turno(remoto, cerrar=True)
            app._ecosistema_origen = None
        app._dejar_de_escuchar()
        app.conversacion = False
        if texto and texto is not False and str(texto).strip():
            app.decir(str(texto), 5000, con_voz=False)

    else:
        if app.flujo is not None:
            app.flujo.cerrar()
            app.flujo = None
        if texto and texto is not False and str(texto).strip():
            app.decir(f"Tuve un problema para pensar: {texto}", 5000, con_voz=False)
        if app.conversacion and not app.escuchando:
            app.cara.root.after(5000, app.escuchar)
