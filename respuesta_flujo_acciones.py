"""Interceptores locales y despacho de acciones para el flujo de respuesta de Silvestra."""
from __future__ import annotations


def _reg_turno(cerebro, u_txt, a_txt, al_frase=None):
    try:
        if callable(al_frase):
            al_frase(a_txt)
    except Exception:
        pass
    try:
        if hasattr(cerebro, "historial") and isinstance(cerebro.historial, list):
            cerebro.historial.append({"role": "user", "content": u_txt})
            cerebro.historial.append({"role": "assistant", "content": a_txt})
        if hasattr(cerebro, "_podar_historial"):
            cerebro._podar_historial()
    except Exception:
        pass


def atender(cerebro, texto_orig, texto, al_frase, app=None):
    """Atiende en local los comandos interceptados; devuelve None si no aplica."""
    if app is None:
        app = getattr(cerebro, "app", None)

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
            _reg_turno(cerebro, texto_orig, resp, al_frase)
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
                _reg_turno(cerebro, texto_orig, resp, al_frase)
                return resp, None, "alegre"
        except Exception as e:
            print(f"[archivo_local] Error lectura: {e}", flush=True)

    import vision_pantalla
    if vision_pantalla.detectar_peticion_vision(texto):
        ok_v, resp_v = vision_pantalla.capturar_y_analizar_pantalla(texto, app=app)
        _reg_turno(cerebro, texto_orig, resp_v, al_frase)
        return resp_v, None, "atenta"

    import cerebro_rag
    ruta_idx = cerebro_rag.detectar_orden_indexacion(texto)
    if ruta_idx:
        ok_r, msg_r = cerebro_rag.indexar_ruta(ruta_idx)
        _reg_turno(cerebro, texto_orig, msg_r, al_frase)
        return msg_r, None, "alegre" if ok_r else "seria"

    import pantalla_remota_accion as pra
    if pra.detectar_orden_hud(texto):
        msg = pra.activar_hud(app=app)
        _reg_turno(cerebro, texto, msg, al_frase)
        return msg, "activar_hud", "alegre"

    import cerebro_mentor
    orden_m = cerebro_mentor.detectar_orden_mentora(texto)
    if orden_m:
        tipo_m, resp_m, emo_m = orden_m
        _reg_turno(cerebro, texto_orig, resp_m, al_frase)
        return resp_m, None, emo_m

    import presentacion
    if presentacion.detectar_orden_presentacion(texto):
        resp_p, emo_p = presentacion.generar_presentacion_dinamica(app=app)
        _reg_turno(cerebro, texto_orig, resp_p, al_frase)
        return resp_p, None, emo_p

    import memoria_sueno, memoria_progreso
    if memoria_sueno.detectar_orden_sueno(texto):
        r_s = memoria_sueno.ejecutar_orden_sueno(texto, app=app); _reg_turno(cerebro, texto_orig, r_s, al_frase); return r_s, None, "calida"
    if memoria_progreso.detectar_orden_progreso(texto):
        r_p = memoria_progreso.consultar_mi_progreso(); _reg_turno(cerebro, texto_orig, r_p, al_frase); return r_p, None, "orgullosa"

    # 1. Núcleo agéntico real (voz/chat); sin al_frase propio para no duplicar voz.
    try:
        import agente_conector
        interactivo = callable(al_frase) or bool(getattr(app, "_agente_interactivo", False))
        atendido_ag = agente_conector.atender(
            cerebro, texto, al_frase=None, app=app,
            canal=getattr(app, "origen_entrada_actual", None),
            interactivo=interactivo,
        )
        if atendido_ag is not None:
            _reg_turno(cerebro, texto_orig, atendido_ag[0], al_frase)
            return atendido_ag[0], atendido_ag[1], atendido_ag[2] or "alegre"
    except Exception as e:
        print(f"[agente_conector] Error: {e}", flush=True)

    # 2. Fallback retrocompatible con el planificador histórico.
    try:
        import cerebro_planificador
        if cerebro_planificador.detectar_intencion_multipaso(texto):
            atendido_mp, resp_mp, acts_mp = cerebro_planificador.procesar_turno_multipaso(cerebro, texto, al_frase=al_frase)
            if atendido_mp:
                return resp_mp, None, "alegre"
    except Exception as e:
        print(f"[planificador] Error: {e}", flush=True)

    # 3. Atajo de recordatorio simple (retorna None en accion para evitar re-ejecucion doble en eventos.py)
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
        _reg_turno(cerebro, texto, msg, al_frase)
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
                _reg_turno(cerebro, texto, msg_d, al_frase)
                return msg_d, nom_difuso, "alegre"

        es_proactivo, msg_proactivo = cerebro_entrenamiento.gestionar_autoaprendizaje_proactivo(texto, app=app)
        if es_proactivo:
            _reg_turno(cerebro, texto, msg_proactivo, al_frase)
            return msg_proactivo, None, "animada"
    except Exception as e:
        print(f"[entrenamiento] Error: {e}", flush=True)

    from memoria_adaptadores import atender_turno
    directo = atender_turno(cerebro, texto)
    if directo:
        return directo
    return None
