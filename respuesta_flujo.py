"""Manejo de respuestas en streaming para Silvestra mediante la cadena de proveedores."""
from cerebro import separar
import cerebro_enrutador
import proveedores
import proveedores_cadenas as pc
import respuesta_flujo_acciones


def responder_flujo(cerebro, texto, al_frase, on_primer_token=None):
    """Genera la respuesta con streaming y conmutación automática de proveedores si hay fallos."""
    texto_orig = str(texto)
    try:
        import agente_confirmacion as ac
        if ac.resolver(getattr(cerebro, "app", None), texto) in ("aprobado", "rechazado"):
            # El hilo del bucle ya tiene el evento: su respuesta final se hablará una sola vez.
            return "", None, "neutral"
    except Exception:
        pass
    try:
        import cerebro_trabajo
        texto = cerebro_trabajo.resolver_referencias(texto)
    except Exception:
        pass

    local = respuesta_flujo_acciones.atender(
        cerebro, texto_orig, texto, al_frase,
        app=getattr(cerebro, "app", None),
    )
    if local is not None:
        return local

    cerebro.historial.append({"role": "user", "content": texto})
    # El carril se decide antes de construir la ventana (política única).
    app = getattr(cerebro, "app", None)
    modo = "normal"
    if app and hasattr(app, "modo_activo"):
        modo = getattr(app, "modo_activo", "normal") or "normal"
    else:
        try:
            import modos_sistema
            modo = modos_sistema.obtener_modo_activo(app)
        except Exception:
            pass

    pro_disp = cerebro_enrutador.verificar_pro_disponible()
    carril, motivo = cerebro_enrutador.decidir_carril(texto, modo_activo=modo, pro_disponible=pro_disp)
    print(f"[enrutador] carril={carril} motivo={motivo}", flush=True)
    from cerebro_historial import construir_ventana
    mensajes = construir_ventana(cerebro.historial, carril=carril,
                                 instrucciones=cerebro.instrucciones(texto))

    tarea = pc.clasificar_dificultad(texto)

    def _on_emocion(emo):
        try:
            import cerebro_mentor
            if cerebro_mentor.es_modo_mentor_activo():
                emo = "concentrada"
        except Exception:
            pass
        if app and hasattr(app, "cola") and app.cola:
            app.cola.put(("emocion", emo))

    crudo = None
    if carril == "pro":
        try:
            crudo = cerebro_enrutador.completar_pro_flujo(
                mensajes, al_frase=al_frase, on_primer_token=on_primer_token, on_emocion=_on_emocion
            )
        except Exception as e:
            print(f"[enrutador] fallback_pro->rapido motivo={e}", flush=True)
            crudo = None

    if crudo is None:
        try:
            crudo = proveedores.completar_flujo(
                mensajes, al_frase, tarea=tarea, on_primer_token=on_primer_token,
                on_emocion=_on_emocion, carril=carril
            )
        except Exception as e:
            print(f"[respuesta_flujo] Excepción en streaming: {e}. Usando respuesta local.", flush=True)
            try:
                al_frase(pc.FRASE_EMERGENCIA_LOCAL)
            except Exception:
                pass
            crudo = pc.respuesta_emergencia_local()

    try:
        respuesta, accion, recuerdo, emocion = separar(crudo)
    except Exception as e:
        print(f"[respuesta_flujo] Error en separar(crudo): {e}", flush=True)
        respuesta, accion, recuerdo, emocion = str(crudo or ""), None, None, "neutral"

    try:
        import cerebro_mentor
        if cerebro_mentor.es_modo_mentor_activo():
            emocion = "concentrada"
            _on_emocion("concentrada")
    except Exception:
        pass

    if recuerdo and not getattr(cerebro, "turno_invitado", False):
        try:
            from memoria_adaptadores import procesar_candidato
            app = getattr(cerebro, "app", None)
            procesar_candidato(
                getattr(cerebro, "memoria", None),
                recuerdo,
                texto,
                fuente="recuerdo_modelo",
                canal=getattr(app, "origen_entrada_actual", "texto"),
            )
        except Exception as e:
            print(f"[memoria] Error procesando candidato de recuerdo: {e}", flush=True)

    try:
        if hasattr(cerebro, "historial") and isinstance(cerebro.historial, list):
            cerebro.historial.append({"role": "assistant", "content": respuesta})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
    except Exception as e:
        print(f"[historial] Error guardando historial: {e}", flush=True)

    if not getattr(cerebro, "turno_invitado", False):
        try:
            import aprendizaje
            aprendizaje.registrar_interaccion(texto, respuesta, emocion)
        except Exception as e:
            print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)

        try:
            turnos_u = sum(1 for m in getattr(cerebro, "historial", []) if m.get("role") == "user")
            if turnos_u > 0 and turnos_u % 3 == 0 and hasattr(cerebro, "memoria") and hasattr(cerebro.memoria, "extraer_hechos_conversacion"):
                import threading
                pedir_fn = getattr(cerebro, "_pedir", None)
                if pedir_fn is None:
                    import proveedores as prov_mod
                    pedir_fn = lambda msgs, tarea="charla": prov_mod.completar(msgs, tarea=tarea)
                threading.Thread(
                    target=cerebro.memoria.extraer_hechos_conversacion,
                    args=(list(cerebro.historial[-6:]), pedir_fn),
                    daemon=True,
                    name="MemoriaExtraerFlujo"
                ).start()
        except Exception as e:
            print(f"[memoria] Error en extracción en segundo plano: {e}", flush=True)

    return respuesta, accion, emocion
