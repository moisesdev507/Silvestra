"""Normaliza fuentes existentes a referencias epistémicas; no realiza consultas."""
from razonamiento_modelos import EvidenciaReferenciada


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


def extraer_evidencia(memoria, token=None):
    hechos, vivo, inferencias, ids = [], [], [], {}
    actual = memoria.get("contexto_actual", {}) if isinstance(memoria, dict) else {}
    for key, fuente in (("context_engine", "vivo_confirmado"), ("multimodal", "multimodal")):
        datos = actual.get(key, {}) if isinstance(actual, dict) else {}
        if not isinstance(datos, dict):
            continue
        for campo in ("ventana", "titulo", "actividad_probable", "audio", "situacion"):
            valor = datos.get(campo)
            if not isinstance(valor, str) or not valor.strip() or valor == "omitido por privacidad":
                continue
            clase = "inferencia" if campo == "actividad_probable" else "hecho"
            ref = EvidenciaReferenciada(f"vivo:{key}:{campo}", f"{campo}: {valor[:220]}", fuente, None, clase, True)
            destino = inferencias if clase == "inferencia" else hechos
            if ref.contenido not in {x.contenido for x in destino}:
                destino.append(ref)
            if ref.contenido not in {x.contenido for x in vivo}:
                vivo.append(ref)
    for ref in memoria.get("evidencia", []) if isinstance(memoria, dict) else []:
        if _cancelado(token):
            break
        fuente = "memoria_explicita" if ref.get("origen") == "explicito" and ref.get("naturaleza") != "temporal" else "memoria_inferida"
        clase = "hecho" if fuente == "memoria_explicita" else "inferencia"
        item = EvidenciaReferenciada(ref.get("id"), ref.get("contenido", ""), fuente, ref.get("confianza"), clase)
        ids[str(item.id)] = item
        (hechos if clase == "hecho" else inferencias).append(item)
    grafo = memoria.get("relaciones", {}) if isinstance(memoria, dict) else {}
    for rel in grafo.get("relaciones_activas", []) if isinstance(grafo, dict) else []:
        item = EvidenciaReferenciada(f"rel:{rel.get('id')}", str(rel.get("tipo_relacion", "relación activa")),
            "grafo", rel.get("confianza"), "inferencia")
        inferencias.append(item)
        ids[str(item.id)] = item
    return hechos, vivo, inferencias, ids
