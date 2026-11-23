import re

import memoria_calidad
import memoria_formacion
import memoria_filtro

detectar_directiva = memoria_formacion.detectar_directiva
historial_prohibido = memoria_formacion.historial_prohibido


def procesar_candidato(memoria, candidato, texto_usuario="", fuente="recuerdo_modelo",
                       canal="texto", contexto=None, explicito=False, usuario_id=None, frecuencia=1):
    if getattr(memoria, "bloqueo_invitado", False):
        return {"aceptado": False, "motivo": "usuario_invitado"}
    uid = usuario_id or memoria.usuario_id
    directiva = detectar_directiva(texto_usuario)
    if directiva["accion"] == "no_guardar":
        return {"aceptado": False, "motivo": "directiva_no_guardar"}
    if directiva["accion"] in ("revisar", "corregir"):
        return {"aceptado": False, "motivo": "directiva_" + directiva["accion"]}
    if directiva["accion"] == "guardar":
        candidato, explicito = directiva["contenido"], True
        if fuente not in ("multimodal", "tarea"):
            fuente = "orden_explicita"
    resultado = memoria_formacion.evaluar_candidato(
        candidato, usuario_id=uid, fuente=fuente, explicito=explicito,
        contexto=contexto, canal=canal, frecuencia=frecuencia)
    if not resultado["aceptado"]:
        return resultado
    item = resultado["recuerdo"]
    if item.tipo_memoria == "trabajo":
        memoria.gestor.agregar_trabajo("trabajo:" + str(id(item)), item.contenido, usuario_id=uid, ttl=900)
        return resultado
    hechos = memoria.datos.get("hechos", [])
    if memoria_filtro.es_duplicado(item.contenido, hechos):
        return {"aceptado": False, "motivo": "duplicado", "recuerdo": item}
    if memoria_calidad.es_duplicado_semantico(item.contenido, hechos):
        return {"aceptado": False, "motivo": "duplicado_semantico", "recuerdo": item}
    fecha = item.fecha_evento[:10]
    if not re.match(r"^\[\d{4}-\d{2}-\d{2}\]", item.contenido):
        item.contenido = f"[{fecha}] {item.contenido}"
    guardado = memoria.gestor.guardar(item, usuario_id=uid)
    try:
        from memoria_relaciones import extraer_desde_recuerdo
        extraer_desde_recuerdo(memoria.gestor.grafo, item.contenido, uid,
            guardado.get("id"), item.origen, item.confianza)
    except Exception:
        pass
    memoria.datos.setdefault("hechos", []).append(item.contenido)
    if len(memoria.datos["hechos"]) > 200:
        import memoria_busqueda
        memoria_busqueda.resumir_memoria_antigua(memoria)
    memoria.guardar()
    return resultado


def procesar_extraccion(memoria, candidato, historial):
    if historial_prohibido(historial):
        return {"aceptado": False, "motivo": "directiva_no_guardar"}
    frase = memoria_formacion.normalizar(candidato)
    freq = max(1, sum(frase in memoria_formacion.normalizar(m.get("content", ""))
        for m in (historial or []) if m.get("role") == "user"))
    return procesar_candidato(memoria, candidato, fuente="extraccion", frecuencia=freq)


def adaptar_evento(memoria, evento, usuario_id=None, guardar_explicito=False, texto_usuario=""):
    if getattr(memoria, "bloqueo_invitado", False):
        return {"aceptado": False, "motivo": "usuario_invitado"}
    if not isinstance(evento, dict):
        return {"aceptado": False, "motivo": "evento_invalido"}
    resumen = evento.get("resumen") or evento.get("hecho")
    if not isinstance(resumen, str) or len(resumen) > 400:
        return {"aceptado": False, "motivo": "sin_resumen_sanitizado"}
    uid = usuario_id or memoria.usuario_id
    if detectar_directiva(texto_usuario)["accion"] == "no_guardar":
        return {"aceptado": False, "motivo": "directiva_no_guardar"}
    guardar_explicito = guardar_explicito and detectar_directiva(texto_usuario)["accion"] == "guardar"
    if not guardar_explicito:
        memoria.gestor.agregar_trabajo("observacion", resumen, uid, ttl=300)
        return {"aceptado": False, "motivo": "solo_contexto_temporal"}
    if evento.get("nivel_epistemico") not in ("confirmado", "detectado"):
        return {"aceptado": False, "motivo": "evidencia_insuficiente"}
    return procesar_candidato(memoria, resumen, texto_usuario, "multimodal", "contexto",
                              explicito=True, usuario_id=uid)


def adaptar_resultado_tarea(memoria, resultado, usuario_id=None, guardar_explicito=False, texto_usuario=""):
    if getattr(memoria, "bloqueo_invitado", False):
        return {"aceptado": False, "motivo": "usuario_invitado"}
    if not isinstance(resultado, dict):
        return {"aceptado": False, "motivo": "resultado_invalido"}
    texto = resultado.get("resumen") or resultado.get("resultado")
    if not isinstance(texto, str):
        return {"aceptado": False, "motivo": "sin_resultado"}
    uid = usuario_id or memoria.usuario_id
    if detectar_directiva(texto_usuario)["accion"] == "no_guardar":
        return {"aceptado": False, "motivo": "directiva_no_guardar"}
    guardar_explicito = guardar_explicito and detectar_directiva(texto_usuario)["accion"] == "guardar"
    if not guardar_explicito:
        memoria.gestor.agregar_trabajo("resultado_tarea", texto[:400], uid, ttl=300)
        return {"aceptado": False, "motivo": "solo_contexto_temporal"}
    return procesar_candidato(memoria, texto, texto_usuario, "tarea", "accion",
                              explicito=True, usuario_id=uid)


def atender_directiva(memoria, texto):
    d = detectar_directiva(texto)
    if getattr(memoria, "bloqueo_invitado", False) and d["accion"] in ("guardar", "revisar", "corregir"):
        return {"atendida": True, "respuesta": "No puedo acceder a memoria privada en un turno invitado."}
    if d["accion"] == "no_guardar":
        return {"atendida": True, "respuesta": "Entendido. No guardaré información de este turno."}
    if d["accion"] == "guardar":
        r = procesar_candidato(memoria, d["contenido"], texto, "orden_explicita", explicito=True)
        return {"atendida": True, "respuesta": "Listo, lo recordaré." if r["aceptado"] else "No puedo guardar ese dato de forma segura."}
    if d["accion"] == "revisar":
        return {"atendida": True, "respuesta": memoria.consultar(d["consulta"])}
    if d["accion"] == "corregir":
        encontrados = memoria.gestor.buscar(d["anterior"], limite=20)
        exactos = [r for r in encontrados if memoria_formacion.normalizar(d["anterior"]) in r["contenido_norm"]]
        if len(exactos) != 1:
            return {"atendida": True, "respuesta": "No puedo identificar un único recuerdo para corregir."}
        try:
            nuevo = memoria.gestor.reemplazar(exactos[0]["id"], d["nuevo"],
                usuario_id=memoria.usuario_id, origen="explicito", confianza=.95)
            memoria.datos["hechos"] = [h for h in memoria.datos.get("hechos", [])
                if memoria_formacion.normalizar(d["anterior"]) not in memoria_formacion.normalizar(h)]
            memoria.datos["hechos"].append(nuevo["contenido"])
            memoria.guardar()
            return {"atendida": True, "respuesta": "Recuerdo corregido."}
        except (ValueError, KeyError):
            return {"atendida": True, "respuesta": "No pude corregir el recuerdo de forma segura."}
    return {"atendida": False}


def atender_turno(cerebro, texto):
    if getattr(cerebro, "turno_invitado", False) and detectar_directiva(texto)["accion"] in ("guardar", "revisar", "corregir"):
        return "No puedo acceder a memoria privada en un turno invitado.", None, "neutral"
    resultado = atender_directiva(cerebro.memoria, texto)
    if not resultado.get("atendida"):
        return None
    cerebro.historial.append({"role": "user", "content": texto})
    cerebro.historial.append({"role": "assistant", "content": resultado["respuesta"]})
    if hasattr(cerebro, "_podar_historial"):
        cerebro._podar_historial()
    return resultado["respuesta"], None, "neutral"
