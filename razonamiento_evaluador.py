"""Clasificación determinista y evaluación de evidencia ya disponible."""
import re

from razonamiento_modelos import (ProblemaEstructurado, Subproblema,
    HipotesisEvaluada, ConclusionJustificada)
from razonamiento_fuentes import extraer_evidencia as _evidencia, _cancelado

PESOS = {"vivo_confirmado": 1.0, "memoria_explicita": .95, "multimodal": .8,
         "grafo": .68, "vivo_probable": .55, "memoria_inferida": .45}


def _problema(consulta):
    q = " ".join(str(consulta or "").split())[:1000]
    t = q.casefold()
    comparativo = bool(re.search(r"\b(o|compara|comparar|comparacion|alternativas?|mejor que)\b", t))
    diagnostico = any(x in t for x in ("error", "falla", "fallo", "no funciona", "por qué no", "causa"))
    plan = any(x in t for x in ("plan", "pasos para", "cómo puedo", "organizar", "qué debo hacer"))
    piezas = [x.strip() for x in re.split(r"[;\n]+|\b(?:ademas|luego|despues|tambien|primero|segundo)\b", q, flags=re.I) if x.strip()]
    tipo = ("comparativo" if comparativo else "diagnostico" if diagnostico else
            "planificacion_preliminar" if plan else "compuesto" if len(piezas) > 1 else "simple")
    objetivo = re.sub(r"^(?:oye|silvestra|por favor|puedes|podrias|me ayudas a)\s*[,;:]?\s*", "", q, flags=re.I).strip(" ¿?¡!.") or q
    restricciones = tuple(dict.fromkeys(m.group(0).strip()[:140] for m in re.finditer(
        r"\b(?:sin|solo|solamente|antes de|excepto|máximo|no más de)\s+([^,;.]+)", t)))
    problema = ProblemaEstructurado(q, objetivo[:500], tipo, restricciones)
    sub = tuple(Subproblema(f"sp{n}", n, x[:280]) for n, x in enumerate(piezas, 1)) if len(piezas) > 1 else ()
    return problema, sub


def _alternativas(memoria, token):
    salida, pares = [], []
    contrad = memoria.get("contradicciones", []) if isinstance(memoria, dict) else []
    for c in contrad:
        if isinstance(c, dict):
            pares.append(tuple(str(x) for x in c.get("ids", []) if x is not None))
    for campo, tipo in (("hipotesis", "hipotesis"), ("alternativas", "alternativa")):
        for n, h in enumerate(memoria.get(campo, []) if isinstance(memoria, dict) else []):
            if _cancelado(token):
                return salida, pares
            refs = list(h.get("recuerdo_ids", h.get("referencias", [])) or [])
            refs.extend(h.get("relacion_ids", []) or [])
            refs = tuple(str(x) for x in refs if x is not None)
            relacionados = tuple(x for par in pares for x in par if x in refs)
            contra = tuple(x for par in pares for x in par if any(r in par for r in refs) and x not in refs)
            confianza = h.get("confianza")
            if confianza is not None and tipo == "hipotesis":
                confianza = min(float(confianza), .65)
            salida.append(HipotesisEvaluada(f"{tipo}:{n+1}", str(h.get("descripcion", h.get("opcion", "posibilidad")))[:280],
                tipo, refs, contra, relacionados, ("hay evidencia contradictoria",) if contra else (), confianza, bool(contra)))
    return salida, pares


def evaluar(consulta, memoria=None, token_cancelacion=None, aprendizajes_experienciales=None):
    problema, subs = _problema(consulta)
    if _cancelado(token_cancelacion):
        return {"problema": problema, "subproblemas": subs, "cancelado": True}
    memoria = memoria if isinstance(memoria, dict) else {}
    hechos, vivo, inferencias, ids = _evidencia(memoria, token_cancelacion)
    opciones, contrad = _alternativas(memoria, token_cancelacion)
    faltan = []
    if not hechos and not inferencias:
        faltan.append("No hay evidencia suficiente vinculada con esta consulta.")
    if problema.complejidad == "diagnostico" and len(hechos) + len(inferencias) < 2:
        faltan.extend(("Falta el mensaje de error exacto.", "Faltan pasos para reproducir el problema."))
    if problema.complejidad == "comparativo" and not opciones:
        faltan.append("Faltan criterios y evidencia para comparar las opciones.")
    if problema.complejidad == "planificacion_preliminar" and not problema.restricciones:
        faltan.append("Faltan restricciones, plazo o recursos disponibles.")
    nums = [x.confianza * PESOS[x.procedencia] for x in hechos + inferencias if x.confianza is not None]
    confianza = sum(nums) / len(nums) if nums else None
    if confianza is not None:
        confianza = max(0., confianza - min(.25, .12 * len(contrad)) - min(.2, .04 * len(faltan)))
    conclusiones = []
    for c in memoria.get("conclusiones", []):
        refs = tuple(str(x) for x in c.get("recuerdo_ids", []) if x is not None)
        score = c.get("confianza")
        if score is not None and float(score) >= .75 and not contrad and refs and all(x in ids for x in refs):
            conclusiones.append(ConclusionJustificada(str(c.get("texto", ""))[:350], refs, refs,
                (), tuple(x.id for x in opciones if x.descartada), min(float(score), confianza if confianza is not None else .65)))
    lecciones = tuple(dict(x) for x in (aprendizajes_experienciales or ())
        if isinstance(x, dict) and x.get("estado") in {"preliminar", "validado"})
    return {"problema": problema, "subproblemas": subs, "hechos": tuple(hechos), "contexto_vivo": tuple(vivo),
        "inferencias": tuple(inferencias), "hipotesis": tuple(x for x in opciones if x.tipo == "hipotesis"),
        "alternativas": tuple(x for x in opciones if x.tipo == "alternativa"), "conclusiones": tuple(conclusiones),
        "contradicciones": tuple(contrad), "informacion_faltante": tuple(dict.fromkeys(faltan)),
        "confianza_global": confianza, "incertidumbre": ("Evidencia incompleta o no numérica.",) if faltan or confianza is None else (),
        "errores": tuple(memoria.get("errores", [])), "aprendizajes_experienciales": lecciones,
        "cancelado": _cancelado(token_cancelacion)}
