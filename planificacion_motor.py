"""Coordinación segura del planificador existente y la memoria SQLite."""
import json
import threading
import uuid
from dataclasses import replace

import planificador as legado
import planificador_modelo as pm
import planificacion_adaptativa as adapt
import planificacion_evaluador as evaluar
from planificacion_almacen import AlmacenPlanes
from planificacion_modelos import AnalisisPlan, DecisionPlan
from ejecucion_modelo import SolicitudEjecucion


def cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


def es_solicitud_explicita(texto):
    import re
    t = str(texto or "").casefold().strip()
    return bool(re.match(r"^(?:silvestra[:,]?\s*)?(?:planifica|organiza|desglosa|crea un plan|diseña un plan|ay[uú]dame a planear|ay[uú]dame a organizar)\b", t))


class _CerebroSeguro:
    def __init__(self, cerebro, token):
        self.cerebro, self.token = cerebro, token

    def _pedir(self, mensajes, tarea="fondo"):
        if cancelado(self.token) or self.cerebro is None:
            return ""
        try:
            salida = self.cerebro._pedir(mensajes, tarea=tarea)
            import re
            import json
            match = re.search(r"\{.*\}", str(salida or ""), re.S)
            data = json.loads(match.group(0)) if match else {}
            import planificador_modelo as pm
            if not isinstance(data, dict) or not isinstance(data.get("fases"), list):
                return ""
            plan = pm.PlanObjetivo.de_dict(data)
            valido, _ = pm.validar_dependencias(plan)
            return json.dumps(plan.a_dict(), ensure_ascii=False) if valido and plan.fases else ""
        except Exception:
            return ""


class _PlanificadorSQLite(legado.Planificador):
    """Reusa el DAG legado; persiste solo por el backend SQLite inyectado."""
    def __init__(self, repo, usuario_id):
        self.repo, self.usuario_id = repo, usuario_id
        self._lock_plan = threading.RLock()
        self._aplazar = True
        self._planes, self._analisis = {}, {}
        self.recargar()
        self._aplazar = False

    def recargar(self):
        self._planes, self._analisis = self.repo.cargar(self.usuario_id)

    def guardar(self):
        if self._aplazar:
            return True
        return bool(self.repo.guardar_lote(self._planes, self._analisis, self.usuario_id) >= 0)

    def crear_plan(self, texto, cerebro=None, razonamiento=None, contexto=None, alternativas=None, token_cancelacion=None):
        if cancelado(token_cancelacion):
            return None, None
        with self._lock_plan:
            anteriores = dict(self._planes)
            self._aplazar = True
            try:
                plan = super().crear_plan(texto, _CerebroSeguro(cerebro, token_cancelacion) if cerebro else None)
            finally:
                self._aplazar = False
            if cancelado(token_cancelacion):
                self._planes = anteriores
                return None, None
            self._planes = anteriores
            plan.id_plan = "plan_" + uuid.uuid4().hex
            self._planes[plan.id_plan] = plan
            analisis = evaluar.evaluar(texto, razonamiento, contexto, plan, alternativas, token_cancelacion)
            self._analisis[plan.id_plan] = analisis.a_dict()
            self.repo.guardar_lote(self._planes, self._analisis, self.usuario_id)
            return plan, analisis


class PlanificacionMotor:
    def __init__(self, almacen, usuario_id=None):
        self.repo = AlmacenPlanes(almacen)
        self.usuario_id = self.repo._uid(usuario_id)
        self.planificador = _PlanificadorSQLite(self.repo, self.usuario_id)

    def crear_plan(self, objetivo, razonamiento=None, contexto=None, cerebro=None,
                   alternativas=None, token_cancelacion=None):
        if cancelado(token_cancelacion):
            return {"cancelado": True, "plan": None, "analisis": None}
        plan, analisis = self.planificador.crear_plan(str(objetivo or ""), cerebro,
            razonamiento, contexto, alternativas, token_cancelacion)
        if cancelado(token_cancelacion) or plan is None:
            return {"cancelado": True, "plan": None, "analisis": None}
        return {"cancelado": False, "plan": plan, "analisis": analisis}

    def obtener(self, id_plan):
        plan, raw = self.repo.obtener(id_plan, self.usuario_id)
        if plan:
            self.planificador._planes[plan.id_plan] = plan
            self.planificador._analisis[plan.id_plan] = raw or {}
        return plan, AnalisisPlan.de_dict(raw) if raw else None

    def actualizar_estado(self, id_plan, id_tarea, estado, motivo=""):
        plan, _ = self.obtener(id_plan)
        if not plan:
            return False, "Plan no encontrado", []
        try:
            impactadas = adapt.actualizar_estado(plan, id_tarea, estado, motivo)
            self.planificador.guardar()
            return True, "Estado actualizado", impactadas
        except (KeyError, ValueError) as exc:
            return False, str(exc), []

    def replanificar_contexto(self, id_plan, nueva_version, contexto):
        plan, analisis = self.obtener(id_plan)
        if not plan or not analisis:
            return {"actualizado": False, "motivo": "plan_no_encontrado"}
        huella = adapt.huella_contexto(contexto)
        if not huella or huella == analisis.contexto_huella:
            return {"actualizado": False, "motivo": "contexto_sin_cambios"}
        adapt.replanificar_incremental(plan, nueva_version, nueva_version.requisitos, nueva_version.restricciones)
        self.planificador._analisis[id_plan] = replace(analisis, contexto_huella=huella).a_dict()
        self.planificador.guardar()
        return {"actualizado": True, "completadas_preservadas": True}

    def preparar_ejecucion(self, id_plan, id_tarea, herramienta, parametros=None):
        plan, _ = self.obtener(id_plan)
        if not plan:
            raise KeyError(id_plan)
        valido, errores = pm.validar_dependencias(plan)
        tarea = plan.mapa_tareas().get(id_tarea)
        if not valido or tarea not in pm.obtener_tareas_accionables(plan):
            raise PermissionError("La tarea no está validada o no es accionable")
        return SolicitudEjecucion(origen="planificador", herramienta=herramienta,
            parametros=dict(parametros or {}), id_plan=id_plan, id_tarea=id_tarea)

    def aprobar_recomendacion(self, id_plan, actor="usuario"):
        if actor != "usuario":
            return False
        plan, analisis = self.obtener(id_plan)
        if not plan or not analisis or not analisis.decision.alternativa_id:
            return False
        decision = replace(analisis.decision, aprobacion_usuario="aprobada",
                           autorizacion_ejecucion="no_solicitada")
        self.planificador._analisis[id_plan] = replace(analisis, decision=decision).a_dict()
        self.planificador.guardar()
        return True

    def progreso(self, id_plan):
        plan, _ = self.obtener(id_plan)
        if not plan:
            return None
        return adapt.progreso(plan)


def formatear(resultado, limite=1200):
    if not resultado or resultado.get("cancelado") or not resultado.get("plan"):
        return ""
    plan, analisis = resultado["plan"], resultado["analisis"]
    lineas = ["[PLAN RECOMENDADO — REQUIERE APROBACIÓN]", "Objetivo: " + plan.objetivo_general,
        "Estrategia sugerida: " + analisis.decision.justificacion]
    if plan.preguntas_pendientes:
        lineas.append("Información pendiente: " + "; ".join(plan.preguntas_pendientes[:4]))
    for fase in plan.fases:
        lineas.append(f"{fase.orden}. {fase.nombre}")
        for tarea in fase.tareas[:8]:
            deps = " (depende de " + ", ".join(tarea.dependencias) + ")" if tarea.dependencias else ""
            lineas.append(f"- [{tarea.id_tarea}] {tarea.titulo}{deps}")
    lineas.append("No se ejecutó ninguna tarea. La recomendación, su aprobación y los permisos de ejecución son pasos distintos.")
    return "\n".join(lineas)[:max(0, int(limite))]
