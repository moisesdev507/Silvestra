"""Manejo centralizado de la cola de eventos de Silvestra.

Se ejecuta exclusivamente en el hilo principal de Qt mediante revisar_cola,
garantizando que ninguna operación sobre la interfaz gráfica ocurra desde hilos secundarios.
"""


def atender_evento(app, tipo, texto):
    """Procesa un evento extraído de app.cola."""
    if tipo == "frase":
        if hasattr(app, "escenario") and app.escenario and app.escenario.isVisible():
            app.escenario.actualizar_subtitulo(texto)
        if app.flujo is None:
            app.texto_flujo = ""
            app.flujo = app.voz.flujo(lambda: app.cola.put(("fin_voz", None)))
        app.texto_flujo = (app.texto_flujo + " " + texto).strip()
        app.flujo.agregar(texto)
        app.cara.decir(app.texto_flujo, None)

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

    elif tipo == "respuesta":
        respuesta, accion = texto
        if accion and hasattr(app, "voz_dueno") and app.voz_dueno:
            permitido, frase_negativa = app.voz_dueno.autorizar_accion(accion)
            if not permitido:
                if app.flujo is not None:
                    app.flujo.cerrar()
                    app.flujo = None
                app.ultimo_dicho = frase_negativa
                app.cara.decir(frase_negativa, None)
                app.decir(frase_negativa)
                return

        if app.flujo is not None:
            app.flujo.cerrar()
            app.flujo = None
            app.ultimo_dicho = respuesta
            app.cara.decir(respuesta, None)
        else:
            app.decir(respuesta)
        if accion:
            app.ejecutar(accion)

    elif tipo == "despertar":
        app.despertar()

    elif tipo == "alternar_conversacion":
        if not app.conversacion:
            app.alternar_conversacion()

    elif tipo == "mirando_pantalla":
        app.cara.decir("Mirando la pantalla...", 4000)

    elif tipo == "telegram_codigo":
        app.decir(f"Código de Telegram: {texto}")

    elif tipo == "telegram_vinculado":
        app.decir("Telegram vinculado con éxito.", 4000)

    elif tipo == "telegram_burbuja":
        app.cara.decir(texto, 4000)

    elif tipo == "ejecutar_accion":
        app.ejecutar(texto)

    elif tipo == "hablar":
        app.decir(texto)

    elif tipo == "hablar_registro":
        voz_txt, burbuja_txt = texto
        if burbuja_txt:
            app.cara.decir(burbuja_txt, None)
        if voz_txt:
            app.ultimo_dicho = voz_txt
            app.voz.hablar(voz_txt)

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

    elif tipo == "fin_voz":
        if app.pendiente_descanso:
            app.descansar()
        elif app.conversacion and not app.escuchando:
            app.cara.root.after(700, app.escuchar)

    elif tipo == "oido":
        if hasattr(app, "iniciativa"):
            app.iniciativa.interaccion()
        app._dejar_de_escuchar()
        if app.conversacion:
            app.silencios = 0
            if app._es_eco(texto):
                app.escuchar()
            else:
                app.origen_entrada_actual = "microfono"
                if hasattr(app, "voz_dueno") and app.voz_dueno:
                    app.voz_dueno.evaluar_entrada_voz(texto)
                app.enviar(texto)

    elif tipo == "silencio":
        app._dejar_de_escuchar()
        app.silencios += 1
        if app.conversacion:
            en_demo = bool(
                (hasattr(app, "escenario") and app.escenario and app.escenario.isVisible())
                or getattr(app, "presentacion_activa", False)
            )
            limite = 5 if en_demo else 2
            if app.silencios >= limite:
                app.conversacion = False
                app.decir("Me quedo callada. Avísame cuando quieras hablar.", 3500)
                app._iniciar_reflexion()
            else:
                app.escuchar()

    elif tipo == "fallo":
        app._dejar_de_escuchar()
        app.conversacion = False
        app.decir(texto, 5000, con_voz=False)

    else:
        # Errores de pensamiento u otros eventos no contemplados
        if app.flujo is not None:
            app.flujo.cerrar()
            app.flujo = None
        app.decir(f"Tuve un problema para pensar: {texto}", 5000, con_voz=False)
        if app.conversacion and not app.escuchando:
            app.cara.root.after(5000, app.escuchar)
