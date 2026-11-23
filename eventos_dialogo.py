"""Manejadores de diálogo y acciones de la cola de eventos.

Extraído de eventos.py para cumplir el límite de 15 KB por archivo.
eventos.py conserva la fachada y la cadena de estabilidad Qt.
"""
import time


def _hablar_en_conversacion(app):
    """True si el evento ocurre durante una conversación por micrófono."""
    return bool(
        getattr(app, "conversacion", False)
        and getattr(app, "origen_entrada_actual", "") in ("microfono", "voz")
    )


def atender_resto(app, tipo, texto, es_confirmacion_rutinaria):
    """Atiende los eventos que no pasan por la verificación Qt de eventos.py."""
    if tipo == "ejecutar_accion":
        app._t_accion_llm = 0
        app.ejecutar(texto)

    elif tipo == "hablar":
        msg = texto[0] if isinstance(texto, (list, tuple)) else str(texto)
        emo = texto[1] if isinstance(texto, (list, tuple)) and len(texto) > 1 else None

        t_llm = getattr(app, "_t_accion_llm", 0)
        if t_llm and (time.time() - t_llm < 4.0):
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
            if t_llm and (time.time() - t_llm < 4.0):
                if es_confirmacion_rutinaria(voz_txt):
                    print(f"[eventos] Omitiendo voz duplicada en hablar_registro: '{voz_txt}'", flush=True)
                    return
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
        app.ultimo_clima = texto

    elif tipo == "fin_voz":
        app.flujo = None
        if getattr(app, "musica_activa", False) and not app.escuchando:
            try:
                import control_laptop
                control_laptop.restaurar_ducking()
            except Exception:
                pass
        if hasattr(app, "cara") and app.cara:
            app.cara.programar_retorno_neutral(2500)
        if app.pendiente_descanso:
            app.descansar()
        elif app.conversacion and not app.escuchando:
            app.cara.root.after(700, app.escuchar)

    elif tipo == "oido":
        app._t_accion_llm = 0
        if hasattr(app, "iniciativa"):
            app.iniciativa.interaccion()
        app._dejar_de_escuchar()
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
                try:
                    import agente_confirmacion as ac
                    if ac.hay_pendiente(app):
                        if ac.resolver(app, texto):
                            return
                        ac.cancelar(app)
                        import agente_conector
                        agente_conector.cancelar(app)
                        app.decir("Cancelé la acción pendiente. No la ejecuté.", 3000)
                        return
                except Exception:
                    pass
                app.enviar(texto)

    elif tipo == "silencio":
        app._dejar_de_escuchar()
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

    elif tipo in ("ecosistema_observacion", "ecosistema_mostrar_qr"):
        import ecosistema_eventos
        ecosistema_eventos.procesar(app, tipo, texto)

    elif tipo == "subtitulo":
        app.decir(str(texto), 5000, con_voz=False)

    elif tipo == "fallo":
        remoto = getattr(app, "_ecosistema_origen", None)
        if remoto and getattr(app, "pantalla_remota", None):
            app.pantalla_remota.puente.reservar_turno(remoto, cerrar=True)
            app._ecosistema_origen = None
        app._dejar_de_escuchar()
        hablar = _hablar_en_conversacion(app)
        app.conversacion = False
        app.decir(texto, 5000, con_voz=hablar)

    else:
        if app.flujo is not None:
            app.flujo.cerrar()
            app.flujo = None
        hablar = _hablar_en_conversacion(app)
        app.decir(f"Tuve un problema para pensar: {texto}", 5000, con_voz=hablar)
        if app.conversacion and not app.escuchando:
            app.cara.root.after(5000, app.escuchar)
