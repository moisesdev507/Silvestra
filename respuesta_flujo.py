"""Manejo de respuestas en streaming para Silvestra mediante la cadena de proveedores."""
from cerebro import separar
import cerebro_enrutador
import proveedores
import proveedores_cadenas as pc


def responder_flujo(cerebro, texto, al_frase, on_primer_token=None):
    """Genera la respuesta con streaming y conmutación automática de proveedores si hay fallos."""
    from memoria_adaptadores import atender_turno
    directo = atender_turno(cerebro, texto)
    if directo:
        return directo
    cerebro.historial.append({"role": "user", "content": texto})
    # Limitar historial a los 8 turnos más recientes para ahorrar tokens y latencia
    mensajes = [{"role": "system", "content": cerebro.instrucciones(texto)}] + cerebro.historial[-8:]

    tarea = pc.clasificar_dificultad(texto)

    # Evaluación determinista del carril: rapido vs pro
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

    def _on_emocion(emo):
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
                mensajes, al_frase, tarea=tarea, on_primer_token=on_primer_token, on_emocion=_on_emocion
            )
        except Exception as e:
            print(f"[respuesta_flujo] Excepción en streaming: {e}. Usando respuesta local.", flush=True)
            try:
                al_frase(pc.FRASE_EMERGENCIA_LOCAL)
            except Exception:
                pass
            crudo = pc.respuesta_emergencia_local()

    respuesta, accion, recuerdo, emocion = separar(crudo)
    if recuerdo and not getattr(cerebro, "turno_invitado", False):
        from memoria_adaptadores import procesar_candidato
        app = getattr(cerebro, "app", None)
        procesar_candidato(cerebro.memoria, recuerdo, texto, fuente="recuerdo_modelo",
            canal=getattr(app, "origen_entrada_actual", "texto"))
    cerebro.historial.append({"role": "assistant", "content": respuesta})
    if hasattr(cerebro, "_podar_historial"):
        cerebro._podar_historial()
    if not getattr(cerebro, "turno_invitado", False):
        try:
            import aprendizaje
            aprendizaje.registrar_interaccion(texto, respuesta, emocion)
        except Exception as e:
            print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)

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
    return respuesta, accion, emocion
