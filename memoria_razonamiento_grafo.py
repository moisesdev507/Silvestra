"""Análisis relacional acotado y de solo lectura sobre el grafo existente."""
import memoria_relaciones


def analizar(grafo, consulta, recuerdos, usuario_id="local", token_cancelacion=None,
             profundidad=2, limite=24):
    """Devuelve aristas activas, débiles o contradictorias sin alterar el grafo."""
    uid = grafo._uid(usuario_id)
    max_prof = max(0, min(int(profundidad), 4))
    max_items = max(1, min(int(limite), 60))
    nodos, errores, relaciones, caminos = {}, [], {}, []
    textos = [str(x.get("contenido", "")) for x in (recuerdos or [])]
    texto_busqueda = " ".join([str(consulta or "")] + textos)[:2500]
    if token_cancelacion is not None and token_cancelacion.is_set():
        return _salida(cancelado=True)
    try:
        paquete = memoria_relaciones.consultar_relacional(
            grafo, consulta, uid, contexto=" ".join(textos)[:1400],
            max_profundidad=max_prof, max_resultados=max_items)
        errores.extend(paquete.get("errores", []))
        for nodo in paquete.get("entidades", []):
            nodos[nodo["id"]] = nodo
        for rel in paquete.get("relaciones", []):
            relaciones[rel["id"]] = rel
    except Exception as exc:
        errores.append(type(exc).__name__)
    if token_cancelacion is not None and token_cancelacion.is_set():
        return _salida(errores, cancelado=True)
    try:
        for nodo in grafo.buscar_nodos(texto_busqueda, uid, limite=12):
            nodos[nodo["id"]] = nodo
        for nodo_id in list(nodos)[:12]:
            if token_cancelacion is not None and token_cancelacion.is_set():
                return _salida(errores, cancelado=True)
            for item in grafo.recorrer(nodo_id, uid, max_prof, max_items):
                nodos[item["nodo"]["id"]] = item["nodo"]
                caminos.append({"nodo_id": item["nodo"]["id"],
                    "profundidad": item["profundidad"],
                    "relacion_ids": [e["id"] for e in item.get("camino", [])]})
                for rel in item.get("camino", []):
                    relaciones[rel["id"]] = rel
    except Exception as exc:
        errores.append(type(exc).__name__)
    todas = list(relaciones.values())
    activas = [r for r in todas if r.get("estado") == "activo" and float(r.get("confianza", 0)) >= .65]
    debiles = [r for r in todas if r.get("estado") == "activo" and float(r.get("confianza", 0)) < .65]
    contradichas = [r for r in todas if r.get("estado") == "contradicho"]
    return {"entidades": list(nodos.values())[:max_items], "relaciones_activas": activas[:max_items],
        "relaciones_debiles": debiles[:max_items], "relaciones_contradictorias": contradichas[:max_items],
        "conexiones": caminos[:max_items], "errores": errores, "cancelado": False}


def _salida(errores=None, cancelado=False):
    return {"entidades": [], "relaciones_activas": [], "relaciones_debiles": [],
        "relaciones_contradictorias": [], "conexiones": [], "errores": errores or [],
        "cancelado": cancelado}
