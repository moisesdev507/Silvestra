"""Razonamiento trazable sobre memoria existente; no escribe ni ejecuta acciones."""
import memoria_recuperacion
import memoria_razonamiento_grafo
import memoria_razonamiento_evidencia
from memoria_modelos import validar_usuario_id


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


def _texto(valor, limite=240):
    if not isinstance(valor, str):
        return ""
    return " ".join(valor.split())[:limite]


def _titulo(valor):
    titulo = _texto(valor)
    try:
        import gui_seguridad
        return "omitido por privacidad" if gui_seguridad.titulo_es_sensible(titulo) else titulo
    except Exception:
        return "omitido por privacidad" if titulo else ""


def _contexto_actual(ctx, multimodal):
    salida = {"fuente": "en_vivo", "context_engine": {}, "multimodal": {}}
    if isinstance(ctx, dict):
        detectado = ctx.get("detectado", {})
        win = detectado.get("ventana", {}) if isinstance(detectado, dict) else {}
        salida["context_engine"] = {"nivel": "detectado", "ventana": _texto(win.get("ejecutable")),
            "titulo": _titulo(win.get("titulo"))}
        prob = ctx.get("probable", {})
        act = prob.get("actividad", {}) if isinstance(prob, dict) else {}
        salida["context_engine"]["actividad_probable"] = _texto(act.get("valor"))
    if isinstance(multimodal, dict):
        win = multimodal.get("ventana", {})
        salida["multimodal"] = {"ventana": _texto(win.get("ejecutable")) if isinstance(win, dict) else "",
            "titulo": ("omitido por privacidad" if isinstance(win, dict) and win.get("titulo_omitido")
                       else _titulo(win.get("titulo")) if isinstance(win, dict) else ""),
            "audio": _texto(multimodal.get("audio")), "situacion": _texto(multimodal.get("situacion"))}
    return salida


def _ejes(consulta):
    t = str(consulta or "").casefold()
    ejes = ["recuerdos pertinentes"]
    for nombre, claves in (("temporal", ("antes", "después", "cambió", "actualmente", "cuando")),
        ("relacional", ("relación", "conexión", "depende", "usa", "entre")),
        ("comparación", (" o ", "mejor", "comparar", "alternativa")),
        ("contextual", ("ahora", "ventana", "aplicación", "situación", "sonido"))):
        if any(k in t for k in claves):
            ejes.append(nombre)
    return ejes


def razonar(gestor, consulta, usuario_id=None, contexto_engine=None, multimodal=None,
            token_cancelacion=None, limite=8):
    uid = validar_usuario_id(usuario_id or gestor.usuario_id)
    salida = {"usuario_id": uid, "consulta": _texto(str(consulta or ""), 500),
        "ejes_analisis": _ejes(consulta), "conocida": [], "desconocida": [],
        "evidencia": [], "inferencias": [], "hipotesis": [], "conclusiones": [],
        "incertidumbre": [], "contradicciones": [], "alternativas": [],
        "contexto_actual": _contexto_actual(contexto_engine, multimodal),
        "trazabilidad": [], "errores": [], "cancelado": False}
    if _cancelado(token_cancelacion):
        salida["cancelado"] = True
        return salida
    try:
        paquete = memoria_recuperacion.recuperar(gestor, consulta, uid,
            contexto=_texto(str(multimodal or ""), 300), limite=max(1, min(int(limite), 12)))
    except Exception as exc:
        salida["errores"].append("recuperacion:" + type(exc).__name__)
        paquete = {"resultados": [], "contradicciones": [], "relaciones": []}
    salida["recuperacion"] = paquete
    if _cancelado(token_cancelacion):
        salida["cancelado"] = True
        return salida
    evidencia_grafo = []
    for item in paquete.get("resultados", []):
        if _cancelado(token_cancelacion):
            salida["cancelado"] = True
            return salida
        temporal = item.get("tipo_memoria") == "trabajo" or item.get("metadatos", {}).get("volatil")
        ref = {"id": item.get("id"), "tipo_memoria": item.get("tipo_memoria", "semantica"),
            "origen": item.get("origen", "inferido"), "fecha": str(item.get("fecha_evento") or item.get("creado_en") or "")[:32],
            "confianza": _confianza(item.get("confianza")), "estado": item.get("estado", "activo"),
            "contenido": _texto(item.get("contenido"), 360), "naturaleza": "temporal" if temporal else "recuerdo"}
        if item.get("estado", "activo") != "activo":
            continue
        salida["evidencia"].append(ref)
        if ref["origen"] == "explicito" and not temporal:
            salida["conocida"].append(ref)
        if ref["origen"] == "inferido" or temporal:
            salida["inferencias"].append({"descripcion": ref["contenido"], "certeza": "limitada",
                "referencias": [ref["id"]], "no_confirmada": True})
        if ref["origen"] == "inferido" and isinstance(ref["id"], int):
            salida["hipotesis"].append({"descripcion": ref["contenido"], "recuerdo_ids": [ref["id"]],
                "confianza": min(.65, ref["confianza"] or .0), "no_confirmada": True})
        if isinstance(ref["id"], int):
            evidencia_grafo.append(item)
            try:
                ref["reemplaza_a_id"] = item.get("reemplaza_a_id")
                ref["cronologia"] = memoria_razonamiento_evidencia.cronologia(
                    gestor.almacen, item, uid, _texto, _confianza)
                ref["historial"] = sum(len(x["snapshots"]) for x in ref["cronologia"])
                ref["linaje"] = [x.get("origen_id") for x in gestor.almacen.listar_linaje(ref["id"], uid)]
            except Exception as exc:
                salida["errores"].append("historial:" + type(exc).__name__)
        salida["trazabilidad"].append({k: ref.get(k) for k in
            ("id", "tipo_memoria", "origen", "fecha", "confianza", "estado", "reemplaza_a_id", "historial", "linaje", "cronologia")})
    for item in paquete.get("contradicciones", []):
        a, b = item.get("recuerdo_a", {}), item.get("recuerdo_b", {})
        salida["contradicciones"].append({"ids": [a.get("id"), b.get("id")],
            "estado": "posible_contradiccion", "fuentes": [a.get("origen"), b.get("origen")]})
    comparables, comparacion = memoria_razonamiento_evidencia.comparar(consulta, salida["evidencia"])
    if comparacion and len(comparables) >= 2:
        salida["alternativas"] = comparables
    elif comparacion:
        salida["incertidumbre"].append("No hay evidencia para comparar las alternativas planteadas.")
    if _cancelado(token_cancelacion):
        salida["cancelado"] = True
        return salida
    try:
        grafo = memoria_razonamiento_grafo.analizar(gestor.grafo, consulta, evidencia_grafo, uid, token_cancelacion)
        if grafo.get("cancelado"):
            salida["cancelado"] = True
            return salida
        salida["errores"].extend("grafo:" + x for x in grafo.get("errores", []))
        salida["relaciones"] = grafo
        salida["contradicciones"].extend({"relacion_id": r.get("id"), "estado": r.get("estado"),
            "origen": r.get("origen"), "confianza": r.get("confianza")} for r in grafo.get("relaciones_contradictorias", []))
        salida["inferencias"].extend({"descripcion": "Conexión relacional entre entidades",
            "certeza": "probable", "relacion_ids": [r.get("id")], "confianza": min(.65, float(r.get("confianza", 0))), "no_confirmada": True}
            for r in grafo.get("relaciones_activas", []))
        for r in grafo.get("relaciones_debiles", []):
            if isinstance(r.get("id"), int):
                salida["hipotesis"].append({"descripcion": "Relación débil entre entidades",
                    "relacion_ids": [r["id"]], "confianza": min(.5, float(r.get("confianza", 0))), "no_confirmada": True})
    except Exception as exc:
        salida["errores"].append("grafo:" + type(exc).__name__)
    fuertes = [x for x in salida["conocida"] if x["confianza"] is not None and x["confianza"] >= .75]
    if fuertes and not salida["contradicciones"]:
        elegido = max(fuertes, key=lambda x: x["confianza"])
        salida["conclusiones"].append({"texto": "El recuerdo explícito con mayor respaldo indica: " + elegido["contenido"],
            "tipo": "respaldada", "recuerdo_ids": [elegido["id"]], "confianza": elegido["confianza"]})
    elif len(salida["evidencia"]) >= 2 and not salida["contradicciones"]:
        refs = salida["evidencia"][:4]
        salida["conclusiones"].append({"texto": "Hay varios recuerdos pertinentes; su contenido requiere interpretación contextual.",
            "tipo": "limitada", "recuerdo_ids": [x["id"] for x in refs], "confianza": None})
        salida["incertidumbre"].append("La evidencia no justifica una conclusión específica.")
    else:
        salida["desconocida"].append("No hay respaldo suficiente para responder con certeza.")
        salida["incertidumbre"].append("Información insuficiente o confianza baja.")
    if salida["contradicciones"]:
        salida["incertidumbre"].append("Hay fuentes contradictorias; se conservan sin elegir una como cierta.")
    if _cancelado(token_cancelacion):
        salida["cancelado"] = True
    return salida


def _confianza(valor):
    try:
        return max(0.0, min(1.0, float(valor)))
    except (TypeError, ValueError):
        return None


def formatear(resultado, limite=650):
    if not isinstance(resultado, dict) or resultado.get("cancelado"):
        return ""
    lineas = ["[RAZONAMIENTO DE MEMORIA — HISTÓRICO, TRAZABLE]"]
    if resultado.get("evidencia"):
        lineas.append("Evidencias desarrolladas en el bloque de memoria; IDs: " +
            ", ".join(str(e.get("id")) for e in resultado["evidencia"][:8]))
    for c in resultado.get("contradicciones", [])[:3]:
        lineas.append(f"- Contradicción posible, referencias {c.get('ids', c.get('relacion_id'))}; no resuelta.")
    for c in resultado.get("conclusiones", [])[:2]:
        lineas.append(f"- Conclusión limitada: {c.get('texto')} [IDs {c.get('recuerdo_ids')}]")
    for h in resultado.get("hipotesis", [])[:3]:
        lineas.append(f"- Hipótesis no confirmada [IDs {h.get('recuerdo_ids', h.get('relacion_ids'))}; confianza {h.get('confianza')}].")
    if resultado.get("incertidumbre"):
        lineas.append("- Incertidumbre: " + "; ".join(resultado["incertidumbre"][:2]))
    lineas.append("El contexto actual en vivo se conserva aparte; estas evidencias son históricas.")
    return "\n".join(lineas)[:max(0, int(limite))]
