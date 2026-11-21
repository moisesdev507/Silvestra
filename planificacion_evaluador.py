"""Evaluación determinista de objetivos, alternativas, riesgos y vacíos."""
import re
from razonamiento_modelos import ResultadoRazonamientoInteligente
import planificador_modelo as pm
from planificacion_adaptativa import huella_contexto
from planificacion_modelos import (ObjetivoPlan, CriterioExito, AlternativaEvaluada,
    RiesgoPlan, DecisionPlan, AnalisisPlan)


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _lista(valor):
    return tuple(str(x).strip() for x in (valor or ()) if str(x).strip())


def _alternativa(raw, i):
    d = dict(raw) if isinstance(raw, dict) else {"titulo": str(raw)}
    beneficio = max(0., min(1., float(d.get("beneficio", .65))))
    complejo = max(0., min(1., float(d.get("complejidad", .45))))
    riesgo = max(0., min(1., float(d.get("riesgo", .35))))
    costo = None if d.get("costo") is None else float(d["costo"])
    costo_score = min(1., costo / 100.) if costo is not None else .45
    score = max(0., min(1., .55 * beneficio + .25 * (1 - complejo) + .2 * (1 - riesgo) - .1 * costo_score))
    return AlternativaEvaluada(str(d.get("id", f"estrategia_{i}")),
        str(d.get("titulo", d.get("nombre", f"Estrategia {i}")))[:180],
        _lista(d.get("ventajas")), _lista(d.get("desventajas")), costo, complejo, riesgo,
        score, str(d.get("justificacion", "Puntaje ponderado por beneficio, costo, complejidad y riesgo."))[:300],
        _lista(d.get("evidencia")))


def _riesgos(objetivo, plan, contexto):
    texto = (objetivo + " " + " ".join(plan.restricciones if plan else ())).casefold()
    riesgos = []
    reglas = ((r"borrar|eliminar|pagar|comprar|publicar|enviar", "impacto externo o irreversible",
               "alto", "Exigir autorización explícita y validar permisos antes de ejecutar."),
              (r"contraseña|token|clave|credencial|privad", "exposición de información sensible",
               "alto", "Minimizar datos y aplicar el filtro de privacidad antes de persistir."),
              (r"depende|integración|proveedor|conexión", "dependencia externa puede bloquear tareas",
               "medio", "Verificar disponibilidad y mantener una alternativa reversible."))
    for i, (pat, desc, impact, prevent) in enumerate(reglas, 1):
        if re.search(pat, texto):
            riesgos.append(RiesgoPlan(f"riesgo_{i}", desc, None, impact, prevent))
    if plan.preguntas_pendientes:
        riesgos.append(RiesgoPlan("riesgo_informacion", "Requisitos sin confirmar pueden cambiar el alcance.",
            None, "medio", "Resolver preguntas pendientes antes de aprobar la estrategia."))
    return tuple(riesgos)


def evaluar(objetivo, razonamiento=None, contexto=None, plan=None, alternativas=None, token_cancelacion=None):
    if token_cancelacion is not None and token_cancelacion.is_set():
        return AnalisisPlan(ObjetivoPlan(str(objetivo or "")), cancelado=True)
    if razonamiento is not None and not isinstance(razonamiento, (dict, ResultadoRazonamientoInteligente)):
        raise TypeError("razonamiento debe ser resultado de Etapa 1")
    if plan is not None:
        valido, errores = pm.validar_dependencias(plan)
        if not valido:
            raise ValueError("DAG inválido: " + "; ".join(errores[:3]))
    gaps = list(_lista(_get(razonamiento, "informacion_faltante", ())))
    if not str(objetivo or "").strip():
        gaps.append("Falta el objetivo principal.")
    preguntas = _get(plan, "preguntas_pendientes", ()) if plan else ()
    gaps.extend(_lista(preguntas))
    recursos = _lista(_get(contexto, "recursos_disponibles", ())) if contexto else ()
    if not recursos:
        gaps.append("Faltan recursos o disponibilidad para estimar el plan.")
    sub = _get(razonamiento, "subproblemas", ()) if razonamiento else ()
    secundarios = tuple(str(_get(x, "descripcion", "")) for x in sub if _get(x, "descripcion"))
    objetivo_plan = ObjetivoPlan(str(objetivo or "").strip()[:800], secundarios,
        _lista(_get(plan, "requisitos", ())), _lista(_get(plan, "restricciones", ())),
        tuple(dict.fromkeys(gaps)), recursos)
    tareas = plan.todas_las_tareas() if plan and hasattr(plan, "todas_las_tareas") else []
    criterios = tuple(CriterioExito(t.id_tarea, "Completar: " + t.titulo,
        "Evidencia verificable y confirmación del usuario.") for t in tareas)
    raw_alts = list(alternativas or ())
    if not raw_alts:
        raw_alts = [{"id": "iterativa", "titulo": "Avanzar por hitos verificables",
            "ventajas": ["Permite revisar resultados temprano", "Limita el costo de cambios"],
            "desventajas": ["Requiere coordinación entre hitos"], "beneficio": .8,
            "complejidad": .4, "riesgo": .25},
            {"id": "minimo", "titulo": "Entregar primero un alcance mínimo",
             "ventajas": ["Reduce el alcance inicial"], "desventajas": ["Puede requerir ampliación posterior"],
             "beneficio": .65, "complejidad": .3, "riesgo": .3}]
    evaluadas = tuple(_alternativa(x, i + 1) for i, x in enumerate(raw_alts[:6]))
    mejor = max(evaluadas, key=lambda a: a.puntaje or 0) if evaluadas else None
    riesgos = _riesgos(str(objetivo or ""), plan, contexto or {})
    conf = _get(razonamiento, "confianza_global") if razonamiento else None
    if conf is not None:
        conf = max(0., min(1., float(conf) - min(.25, .08 * len(gaps) + .05 * len(riesgos))))
    just = (f"Se recomienda {mejor.titulo}: pondera beneficio, costo, complejidad y riesgo; "
            "la aprobación y autorización de ejecución siguen pendientes.") if mejor else "No hay alternativa evaluable."
    evs = _get(razonamiento, "evidencia", ()) if isinstance(razonamiento, dict) else (
        list(_get(razonamiento, "hechos", ())) + list(_get(razonamiento, "inferencias", ())) if razonamiento else ())
    refs = tuple(str(_get(x, "id", "")) for x in evs[:5] if _get(x, "id") is not None)
    decision = DecisionPlan(mejor.id if mejor else None, just, bool(mejor),
        "pendiente" if mejor else "no_requerida", "no_solicitada",
        refs, conf)
    probable = _get(_get(contexto, "probable", {}), "actividad", {}) if contexto else {}
    contexto_probable = ("Actividad probable: " + str(_get(probable, "valor", "")),) if _get(probable, "valor") else ()
    confirmado = _get(contexto, "confirmado", {}) if contexto else {}
    contexto_confirmado = tuple(f"{k}: {v.get('valor')}" for k, v in confirmado.items()
        if isinstance(v, dict) and v.get("valor"))
    huella = huella_contexto(contexto or {})
    return AnalisisPlan(objetivo_plan, criterios, evaluadas, riesgos, decision,
                        contexto_probable, contexto_confirmado, huella, False)
