"""Manejo de respuestas en streaming para Silvestra mediante la cadena de proveedores."""
from cerebro import separar
import cerebro_enrutador
import proveedores
import proveedores_cadenas as pc


def responder_flujo(cerebro, texto, al_frase, on_primer_token=None):
    """Genera la respuesta con streaming y conmutación automática de proveedores si hay fallos."""
    texto_orig = str(texto)
    try:
        import cerebro_trabajo
        texto = cerebro_trabajo.resolver_referencias(texto)
    except Exception:
        pass

    # 0. Intercepción local instantánea (< 50 ms) para escritura y lectura real de archivos
    import os
    import re
    if str(texto).startswith("escribir_archivo "):
        try:
            import habilidades_archivos as ha
            arg = str(texto)[len("escribir_archivo "):].strip()
            ok, msg = ha.escribir_archivo(arg)
            nom = os.path.basename(arg.split("|")[0].strip())
            resp = f"Listo, guardé los cambios en {nom}." if ok else msg
            if callable(al_frase):
                al_frase(resp)
            cerebro.historial.append({"role": "user", "content": texto_orig})
            cerebro.historial.append({"role": "assistant", "content": resp})
            if hasattr(cerebro, "_podar_historial"):
                cerebro._podar_historial()
            return resp, None, "alegre"
        except Exception as e:
            print(f"[archivo_local] Error escritura: {e}", flush=True)

    m_leer = re.search(r"^(?:por\s+favor\s+)?(?:lee(?:lo|la)?|léelo|léela|lee\s+(?:el\s+)?(?:archivo|documento)?\s*([a-zA-Z0-9_\-\.]+)?)(?:\s+por\s+favor)?[\.\?!]?$", str(texto).strip(), re.I)
    if m_leer:
        try:
            import habilidades_archivos as ha
            nom_obj = m_leer.group(1)
            if not nom_obj or nom_obj.lower() in ("el", "archivo", "documento", "lo", "la"):
                import cerebro_trabajo
                nom_obj = cerebro_trabajo.obtener_memoria_trabajo().get("ultimo_archivo")
            if nom_obj:
                nom_limpio = os.path.basename(str(nom_obj).strip())
                ok, res_leer = ha.leer_archivo(nom_limpio)
                if ok:
                    c_texto = res_leer.split("\n", 1)[1].strip() if "\n" in res_leer else res_leer
                    palabras = c_texto.split()
                    resumen = c_texto if len(palabras) <= 45 else (" ".join(palabras[:40]) + "... Contenido truncado en voz.")
                    resp = f"El archivo {nom_limpio} dice: {resumen}"
                else:
                    resp = res_leer
                if callable(al_frase):
                    al_frase(resp)
                cerebro.historial.append({"role": "user", "content": texto_orig})
                cerebro.historial.append({"role": "assistant", "content": resp})
                if hasattr(cerebro, "_podar_historial"):
                    cerebro._podar_historial()
                return resp, None, "alegre"
        except Exception as e:
            print(f"[archivo_local] Error lectura: {e}", flush=True)

    app = getattr(cerebro, "app", None)
    import vision_pantalla
    if vision_pantalla.detectar_peticion_vision(texto):
        ok_v, resp_v = vision_pantalla.capturar_y_analizar_pantalla(texto, app=app)
        if callable(al_frase):
            al_frase(resp_v)
        cerebro.historial.append({"role": "user", "content": texto_orig})
        cerebro.historial.append({"role": "assistant", "content": resp_v})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return resp_v, None, "atenta"

    import cerebro_rag
    ruta_idx = cerebro_rag.detectar_orden_indexacion(texto)
    if ruta_idx:
        ok_r, msg_r = cerebro_rag.indexar_ruta(ruta_idx)
        if callable(al_frase):
            al_frase(msg_r)
        cerebro.historial.append({"role": "user", "content": texto_orig})
        cerebro.historial.append({"role": "assistant", "content": msg_r})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return msg_r, None, "alegre" if ok_r else "seria"
    import pantalla_remota_accion as pra
    if pra.detectar_orden_hud(texto):
        msg = pra.activar_hud(app=app)
        if callable(al_frase):
            al_frase(msg)
        cerebro.historial.append({"role": "user", "content": texto})
        cerebro.historial.append({"role": "assistant", "content": msg})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return msg, "activar_hud", "alegre"

    # 1. Planificador cognitivo multi-paso (prioritario ante órdenes compuestas)
    try:
        import cerebro_planificador
        if cerebro_planificador.detectar_intencion_multipaso(texto):
            atendido_mp, resp_mp, acts_mp = cerebro_planificador.procesar_turno_multipaso(cerebro, texto, al_frase=al_frase)
            if atendido_mp:
                return resp_mp, None, "alegre"
    except Exception as e:
        print(f"[planificador] Error: {e}", flush=True)

    # 2. Atajo de recordatorio simple (retorna None en accion para evitar re-ejecucion doble en eventos.py)
    import recordatorios
    if recordatorios.es_recordatorio_temporal(texto):
        rec_mgr = getattr(app, "recordatorios", None)
        if rec_mgr and hasattr(rec_mgr, "poner_recordatorio"):
            msg = rec_mgr.poner_recordatorio(texto)
        else:
            ts, hora_str, que = recordatorios.parsear_tiempo(texto)
            if ts:
                import datetime
                import time
                tz = recordatorios._obtener_tz()
                dt_target = datetime.datetime.fromtimestamp(ts, tz) if tz else datetime.datetime.fromtimestamp(ts)
                item = {
                    "id": int(time.time() * 1000),
                    "texto": que,
                    "timestamp": ts,
                    "hora_exacta": hora_str,
                    "fecha": dt_target.strftime("%Y-%m-%d"),
                    "completado": False,
                }
                datos = recordatorios._cargar()
                datos.append(item)
                recordatorios._guardar(datos)
                creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
                msg = f"Listo, {creador}. Te recordaré {que} a las {hora_str}."
            else:
                msg = "No entendí la hora o el tiempo para el recordatorio."
        if callable(al_frase):
            al_frase(msg)
        cerebro.historial.append({"role": "user", "content": texto})
        cerebro.historial.append({"role": "assistant", "content": msg})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return msg, None, "alegre"

    creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"

    try:
        import cerebro_grafo
        cerebro_grafo.extraer_y_guardar_hechos(texto, creador=creador)
    except Exception:
        pass

    import aprendiz_habilidades
    es_conf, nom_hab = aprendiz_habilidades.detectar_orden_confirmacion(texto)
    if es_conf:
        ok, msg = aprendiz_habilidades.confirmar_habilidad(nom_hab, app=app)
        if callable(al_frase):
            al_frase(msg)
        cerebro.historial.append({"role": "user", "content": texto})
        cerebro.historial.append({"role": "assistant", "content": msg})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return msg, "confirmar_habilidad", "alegre" if ok else "seria"

    orden_aprender = aprendiz_habilidades.detectar_orden_aprendizaje(texto)
    if orden_aprender:
        ok, msg = aprendiz_habilidades.aprender_habilidad(orden_aprender, app=app)
        if callable(al_frase):
            al_frase(msg)
        cerebro.historial.append({"role": "user", "content": texto})
        cerebro.historial.append({"role": "assistant", "content": msg})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
        return msg, "aprender_habilidad", "alegre" if ok else "preocupada"

    try:
        import cerebro_entrenamiento
        es_lec, msg_lec = cerebro_entrenamiento.detectar_y_guardar_leccion(texto, creador=creador)
        if es_lec:
            if callable(al_frase):
                al_frase(msg_lec)
            cerebro.historial.append({"role": "user", "content": texto})
            cerebro.historial.append({"role": "assistant", "content": msg_lec})
            if hasattr(cerebro, "_podar_historial"):
                cerebro._podar_historial()
            return msg_lec, "guardar_leccion", "alegre"

        nom_difuso, info_difuso = cerebro_entrenamiento.buscar_habilidad_difusa(texto)
        if not nom_difuso:
            nom_difuso, info_difuso = aprendiz_habilidades.buscar_habilidad_por_intencion(texto)

        if nom_difuso:
            import acciones
            ok_d, res_d = acciones.ejecutar(nom_difuso, texto)
            if ok_d and res_d:
                msg_d = str(res_d)
                if callable(al_frase):
                    al_frase(msg_d)
                cerebro.historial.append({"role": "user", "content": texto})
                cerebro.historial.append({"role": "assistant", "content": msg_d})
                if hasattr(cerebro, "_podar_historial"):
                    cerebro._podar_historial()
                return msg_d, nom_difuso, "alegre"

        es_proactivo, msg_proactivo = cerebro_entrenamiento.gestionar_autoaprendizaje_proactivo(texto, app=app)
        if es_proactivo:
            if callable(al_frase):
                al_frase(msg_proactivo)
            cerebro.historial.append({"role": "user", "content": texto})
            cerebro.historial.append({"role": "assistant", "content": msg_proactivo})
            if hasattr(cerebro, "_podar_historial"):
                cerebro._podar_historial()
            return msg_proactivo, None, "animada"
    except Exception as e:
        print(f"[entrenamiento] Error: {e}", flush=True)

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
