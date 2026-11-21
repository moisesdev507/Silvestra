"""Orquestador puro, cancelable y de solo lectura del razonamiento cognitivo."""
from razonamiento_modelos import (ProblemaEstructurado, Subproblema,
    EvidenciaReferenciada, HipotesisEvaluada, ConclusionJustificada,
    ResultadoRazonamientoInteligente)
import razonamiento_evaluador


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


def _titulo(valor):
    texto = str(valor or "")[:180]
    try:
        import gui_seguridad
        return "omitido por privacidad" if gui_seguridad.titulo_es_sensible(texto) else texto
    except Exception:
        return "omitido por privacidad" if texto else ""


def razonar(consulta, resultado_memoria=None, contexto_engine=None, multimodal=None,
            memoria=None, gestor=None, usuario_id=None, token_cancelacion=None,
            aprendizajes_experienciales=None):
    """Estructura un resultado existente; consulta memoria una sola vez si falta."""
    bruto = resultado_memoria if isinstance(resultado_memoria, dict) else None
    errores = []
    if bruto is None and not _cancelado(token_cancelacion):
        origen = gestor or memoria
        if origen is not None:
            metodo = getattr(origen, "razonar", None)
            if callable(metodo):
                try:
                    bruto = metodo(consulta, usuario_id=usuario_id, contexto_engine=contexto_engine,
                                   multimodal=multimodal, token_cancelacion=token_cancelacion)
                except Exception as exc:
                    errores.append(type(exc).__name__)
    if bruto is None:
        bruto = {"evidencia": [], "errores": errores}
    if contexto_engine or multimodal:
        actual = bruto.setdefault("contexto_actual", {"fuente": "en_vivo", "context_engine": {}, "multimodal": {}})
        if not isinstance(actual, dict):
            actual = bruto["contexto_actual"] = {"fuente": "en_vivo", "context_engine": {}, "multimodal": {}}
        if isinstance(contexto_engine, dict):
            detectado = contexto_engine.get("detectado", {})
            win = detectado.get("ventana", {}) if isinstance(detectado, dict) else {}
            actual["context_engine"] = {"ventana": str(win.get("ejecutable", ""))[:100], "titulo": _titulo(win.get("titulo"))}
        if isinstance(multimodal, dict):
            mm = dict(multimodal)
            win = mm.get("ventana")
            if isinstance(win, dict):
                win = dict(win)
                win["titulo"] = "omitido por privacidad" if win.get("titulo_omitido") else _titulo(win.get("titulo"))
                mm["ventana"] = win
            actual["multimodal"] = mm
    evaluado = razonamiento_evaluador.evaluar(consulta, bruto, token_cancelacion, aprendizajes_experienciales)
    if errores:
        evaluado["errores"] = tuple(errores)
    p = evaluado.get("problema") or ProblemaEstructurado(str(consulta or ""), str(consulta or ""), "simple")
    return ResultadoRazonamientoInteligente(problema=p,
        subproblemas=tuple(evaluado.get("subproblemas", ())), hechos=tuple(evaluado.get("hechos", ())),
        contexto_vivo=tuple(evaluado.get("contexto_vivo", ())), inferencias=tuple(evaluado.get("inferencias", ())),
        hipotesis=tuple(evaluado.get("hipotesis", ())), alternativas=tuple(evaluado.get("alternativas", ())),
        conclusiones=tuple(evaluado.get("conclusiones", ())), contradicciones=tuple(evaluado.get("contradicciones", ())),
        informacion_faltante=tuple(evaluado.get("informacion_faltante", ())), confianza_global=evaluado.get("confianza_global"),
        incertidumbre=tuple(evaluado.get("incertidumbre", ())), errores=tuple(evaluado.get("errores", ())),
        aprendizajes_experienciales=tuple(evaluado.get("aprendizajes_experienciales", ())),
        cancelado=bool(evaluado.get("cancelado") or _cancelado(token_cancelacion)))


def formatear(resultado, limite=900):
    """Resumen acotado con observaciones en vivo separadas de memoria histórica."""
    if not isinstance(resultado, ResultadoRazonamientoInteligente) or resultado.cancelado:
        return ""
    lineas = [f"[ANÁLISIS COGNITIVO: {resultado.problema.complejidad}]",
        "[RAZONAMIENTO DE MEMORIA — HISTÓRICO, TRAZABLE]", "Objetivo: " + resultado.problema.objetivo]
    if resultado.contexto_vivo:
        lineas.append("[ESTADO ACTUAL EN VIVO DE WINDOWS]")
        lineas.extend("- " + x.contenido for x in resultado.contexto_vivo[:4])
        lineas.append("[FIN ESTADO ACTUAL EN VIVO DE WINDOWS]")
    if resultado.hechos:
        lineas.append("Hechos/recuerdos explícitos con referencias: " + "; ".join(
            f"{x.contenido} [id {x.id}]" for x in resultado.hechos[:4]))
    if resultado.aprendizajes_experienciales:
        lineas.append("[APRENDIZAJES DE EXPERIENCIAS — HISTÓRICOS, NO HECHOS ACTUALES]")
        lineas.extend("- " + str(x.get("interpretacion", ""))[:220] +
            f" (estado={x.get('estado')}, confianza={x.get('confianza')}, origen={','.join(x.get('origen_ids',())[:3])})"
            for x in resultado.aprendizajes_experienciales[:4])
    if resultado.inferencias:
        lineas.append("Inferencias no confirmadas: " + "; ".join(
            f"{x.contenido} [id {x.id}; confianza {x.confianza}]" for x in resultado.inferencias[:3]))
    for h in resultado.hipotesis[:3]:
        lineas.append(f"Hipótesis (no hecho): {h.texto}; a favor={h.evidencia_favor}, contra={h.evidencia_contra}.")
    for h in resultado.alternativas[:3]:
        lineas.append(f"Alternativa: {h.texto}; referencias={h.evidencia_favor}.")
    for c in resultado.conclusiones[:2]:
        lineas.append(f"Conclusión trazable: {c.texto} [evidencias {c.evidencias}; confianza {c.confianza}]")
    if resultado.informacion_faltante:
        lineas.append("Información faltante: " + "; ".join(resultado.informacion_faltante[:3]))
    if resultado.incertidumbre:
        lineas.append("Incertidumbre: " + "; ".join(resultado.incertidumbre[:2]))
    if resultado.errores:
        lineas.append("Una fuente cognitiva no estuvo disponible; no se sustituyó por datos inventados.")
    return "\n".join(lineas)[:max(0, int(limite))]
