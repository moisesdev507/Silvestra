"""Motor inteligente de planificación, descomposición y persistencia (Etapa 6)."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Optional

import planificador_modelo as pm

ARCHIVO_PLANES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planes_objetivos.json")
_bloqueo_persistencia = threading.RLock()


def _cargar_planes_disco() -> dict[str, pm.PlanObjetivo]:
    with _bloqueo_persistencia:
        if not os.path.exists(ARCHIVO_PLANES):
            return {}
        try:
            with open(ARCHIVO_PLANES, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, dict):
                return {}
            return {k: pm.PlanObjetivo.de_dict(v) for k, v in datos.items() if isinstance(v, dict)}
        except Exception as e:
            print(f"[planificador] Error cargando planes: {e}", flush=True)
            return {}


def _guardar_planes_disco(planes: dict[str, pm.PlanObjetivo]) -> bool:
    with _bloqueo_persistencia:
        ruta_tmp = ARCHIVO_PLANES + ".tmp"
        try:
            datos = {k: v.a_dict() for k, v in planes.items()}
            with open(ruta_tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            os.replace(ruta_tmp, ARCHIVO_PLANES)
            return True
        except Exception as e:
            print(f"[planificador] Error guardando planes: {e}", flush=True)
            if os.path.exists(ruta_tmp):
                try:
                    os.remove(ruta_tmp)
                except Exception:
                    pass
            return False


def _detectar_preguntas_faltantes(texto: str) -> list[str]:
    t = texto.lower()
    preguntas: list[str] = []
    if not any(k in t for k in ("python", "fastapi", "react", "django", "sql", "postgres", "node", "java", "stack", "lenguaje")):
        preguntas.append("¿Qué stack tecnológico o lenguaje prefieres para este desarrollo?")
    if not any(k in t for k in ("mes", "semana", "días", "dias", "plazo", "fecha", "urgente", "cronograma")):
        preguntas.append("¿Existe un plazo límite o fecha tentativa para completar este objetivo?")
    if not any(k in t for k in ("usuario", "rol", "estudiante", "profesor", "cliente", "admin", "alcance", "módulo", "modulo")):
        preguntas.append("¿Cuáles son los tipos de usuarios o módulos prioritarios en la primera versión?")
    return preguntas


def _descomposicion_determinista(texto_objetivo: str) -> pm.PlanObjetivo:
    t_limpio = texto_objetivo.strip()
    titulo = t_limpio[:45] + ("..." if len(t_limpio) > 45 else "")
    id_plan = f"plan_{int(time.time())}"
    preguntas = _detectar_preguntas_faltantes(t_limpio)

    es_sistema = any(k in t_limpio.lower() for k in ("sistema", "app", "software", "web", "plataforma", "universit"))
    if es_sistema:
        reqs = ["Autenticación y roles", "Base de datos relacional", "Gestión administrativa"]
        rests = ["Desarrollo modular sin servicios de pago", "Pruebas unitarias"]
        f1 = pm.Fase("f1", 1, "Análisis y Requisitos", "Alcance y entidades", pm.ESTADO_PENDIENTE, [
            pm.Tarea("t1_1", "Levantamiento de entidades y roles", "Modelar actores y permisos", "f1", pm.ESTADO_PENDIENTE, 5, 4, "baja", [], "", [
                pm.Subtarea("st1_1_1", "Definir tabla de roles"), pm.Subtarea("st1_1_2", "Validar flujos"),
            ]),
            pm.Tarea("t1_2", "Especificación de API y contratos", "Endpoints requeridos", "f1", pm.ESTADO_PENDIENTE, 4, 3, "media", ["t1_1"]),
        ])
        f2 = pm.Fase("f2", 2, "Arquitectura y Datos", "Base de datos y backend núcleo", pm.ESTADO_PENDIENTE, [
            pm.Tarea("t2_1", "Diseño relacional y migraciones", "Tablas y relaciones", "f2", pm.ESTADO_PENDIENTE, 5, 4, "media", ["t1_2"], "", [
                pm.Subtarea("st2_1_1", "Modelar entidades"), pm.Subtarea("st2_1_2", "Crear migraciones"),
            ]),
            pm.Tarea("t2_2", "Estructura base del proyecto", "Entorno y configs", "f2", pm.ESTADO_PENDIENTE, 4, 3, "baja", ["t1_2"]),
        ])
        f3 = pm.Fase("f3", 3, "Implementación Núcleo", "CRUD y autenticación", pm.ESTADO_PENDIENTE, [
            pm.Tarea("t3_1", "Módulos de gestión principal", "Operaciones clave", "f3", pm.ESTADO_PENDIENTE, 5, 3, "alta", ["t2_1", "t2_2"]),
            pm.Tarea("t3_2", "Control de acceso", "Rutas protegidas", "f3", pm.ESTADO_PENDIENTE, 4, 4, "media", ["t2_2"]),
        ])
        f4 = pm.Fase("f4", 4, "Validación y Cierre", "Pruebas y entrega", pm.ESTADO_PENDIENTE, [
            pm.Tarea("t4_1", "Pruebas integrales", "Verificar flujos críticos", "f4", pm.ESTADO_PENDIENTE, 4, 3, "media", ["t3_1", "t3_2"]),
            pm.Tarea("t4_2", "Documentación y entrega", "Guía de despliegue", "f4", pm.ESTADO_PENDIENTE, 3, 2, "baja", ["t4_1"]),
        ])
        fases = [f1, f2, f3, f4]
    else:
        reqs = ["Definir entregables específicos", "Establecer métricas de éxito"]
        rests = ["Recursos y tiempo limitados"]
        fases = [
            pm.Fase("f1", 1, "Alcance y Plan", "Metas y límites", pm.ESTADO_PENDIENTE, [
                pm.Tarea("t1_1", "Definir alcance detallado", "Clarificar metas", "f1", pm.ESTADO_PENDIENTE, 5, 4, "baja"),
            ]),
            pm.Fase("f2", 2, "Ejecución Principal", "Actividades clave", pm.ESTADO_PENDIENTE, [
                pm.Tarea("t2_1", "Implementar entregables", "Ejecución directa", "f2", pm.ESTADO_PENDIENTE, 5, 4, "media", ["t1_1"]),
            ]),
            pm.Fase("f3", 3, "Revisión Final", "Verificación y cierre", pm.ESTADO_PENDIENTE, [
                pm.Tarea("t3_1", "Cierre y validación", "Validar resultados", "f3", pm.ESTADO_PENDIENTE, 4, 3, "baja", ["t2_1"]),
            ]),
        ]

    plan = pm.PlanObjetivo(id_plan, titulo, t_limpio, reqs, rests, preguntas, pm.ESTADO_PENDIENTE, fases)
    pm.validar_dependencias(plan)
    return plan


class Planificador:
    """Motor central de planificación, seguimiento y persistencia."""

    def __init__(self):
        self._planes: dict[str, pm.PlanObjetivo] = {}
        self.recargar()

    def recargar(self) -> None:
        with _bloqueo_persistencia:
            self._planes = _cargar_planes_disco()

    def guardar(self) -> bool:
        with _bloqueo_persistencia:
            return _guardar_planes_disco(self._planes)

    def crear_plan(self, texto_objetivo: str, cerebro: Any = None) -> pm.PlanObjetivo:
        plan: Optional[pm.PlanObjetivo] = None
        if cerebro is not None and hasattr(cerebro, "_pedir"):
            try:
                prm = (
                    "Descompón el objetivo en un JSON estricto con: titulo, requisitos (lista), "
                    "restricciones (lista), preguntas_pendientes (lista), fases (lista con id_fase, orden, nombre, descripcion, "
                    "tareas con id_tarea, titulo, descripcion, importancia (1-5), urgencia (1-5), complejidad (baja/media/alta), dependencias (lista)). "
                    "Sin markdown."
                )
                resp = cerebro._pedir([{"role": "system", "content": prm}, {"role": "user", "content": texto_objetivo}], tarea="fondo")
                if resp:
                    m = re.search(r"\{.*\}", resp, re.DOTALL)
                    if m:
                        datos = json.loads(m.group(0))
                        datos["id_plan"] = f"plan_{int(time.time())}"
                        datos["objetivo_general"] = texto_objetivo
                        cand = pm.PlanObjetivo.de_dict(datos)
                        ok, _ = pm.validar_dependencias(cand)
                        if ok and cand.fases:
                            plan = cand
            except Exception as e:
                print(f"[planificador] Error en LLM, usando determinista: {e}", flush=True)

        if plan is None:
            plan = _descomposicion_determinista(texto_objetivo)

        with _bloqueo_persistencia:
            self._planes[plan.id_plan] = plan
            self.guardar()
        return plan

    def obtener_plan(self, id_plan: str) -> Optional[pm.PlanObjetivo]:
        with _bloqueo_persistencia:
            return self._planes.get(id_plan)

    def listar_planes(self) -> list[pm.PlanObjetivo]:
        with _bloqueo_persistencia:
            return list(self._planes.values())

    def actualizar_estado_tarea(
        self, id_plan: str, id_tarea: str, nuevo_estado: str, motivo_bloqueo: str = ""
    ) -> tuple[bool, str, list[str]]:
        with _bloqueo_persistencia:
            plan = self._planes.get(id_plan)
            if not plan:
                return False, f"Plan '{id_plan}' no encontrado.", []
            mapa = plan.mapa_tareas()
            if id_tarea not in mapa:
                return False, f"Tarea '{id_tarea}' no existe.", []
            if nuevo_estado not in pm.ESTADOS_VALIDOS:
                return False, f"Estado '{nuevo_estado}' inválido.", []

            impactadas: list[str] = []
            if nuevo_estado == pm.ESTADO_BLOQUEADA:
                impactadas = pm.marcar_tarea_bloqueada(plan, id_tarea, motivo_bloqueo)
            else:
                mapa[id_tarea].estado = nuevo_estado
                if nuevo_estado == pm.ESTADO_COMPLETADA:
                    mapa[id_tarea].motivo_bloqueo = ""
                plan.registrar_cambio("estado_tarea", f"Tarea '{id_tarea}' pasó a '{nuevo_estado}'")
                plan.actualizar_estado_general()

            self.guardar()
            return True, f"Tarea '{id_tarea}' en '{nuevo_estado}'.", impactadas

    def recomendar_siguiente_paso(self, id_plan: Optional[str] = None, app: Any = None) -> dict[str, Any]:
        with _bloqueo_persistencia:
            cands = [self._planes[id_plan]] if id_plan and id_plan in self._planes else list(self._planes.values())
            activos = [p for p in cands if p.estado in (pm.ESTADO_PENDIENTE, pm.ESTADO_EN_PROGRESO, pm.ESTADO_BLOQUEADA)]
            if not activos:
                return {"hay_recomendacion": False, "mensaje": "Sin planes activos."}

            plan = activos[0]
            accionables = pm.obtener_tareas_accionables(plan)
            modo = ""
            if app is not None:
                try:
                    import contexto_motor
                    ctx = contexto_motor.obtener_motor_contexto(app).obtener_contexto()
                    modo = ctx.get("detectado", {}).get("modo_sistema", {}).get("modo", "")
                except Exception:
                    pass

            if accionables:
                top = accionables[0]
                return {
                    "hay_recomendacion": True, "id_plan": plan.id_plan, "plan_titulo": plan.titulo,
                    "tarea": top.a_dict(), "total_accionables": len(accionables), "contexto_modo": modo,
                    "recomendacion_texto": f"Siguiente paso: [{top.id_tarea}] {top.titulo} (Prioridad: {top.puntaje_prioridad}).",
                }
            if plan.preguntas_pendientes:
                return {
                    "hay_recomendacion": False, "id_plan": plan.id_plan, "plan_titulo": plan.titulo,
                    "bloqueo_por_preguntas": True, "preguntas_pendientes": list(plan.preguntas_pendientes),
                    "mensaje": f"Pregunta pendiente: {plan.preguntas_pendientes[0]}",
                }
            return {"hay_recomendacion": False, "id_plan": plan.id_plan, "mensaje": "Sin tareas accionables."}

    def obtener_resumen_planes_activos(self) -> list[dict[str, Any]]:
        with _bloqueo_persistencia:
            resumen = []
            for p in self._planes.values():
                tot = len(p.todas_las_tareas())
                comp = sum(1 for t in p.todas_las_tareas() if t.estado == pm.ESTADO_COMPLETADA)
                bloq = sum(1 for t in p.todas_las_tareas() if t.estado == pm.ESTADO_BLOQUEADA)
                resumen.append({
                    "id_plan": p.id_plan, "titulo": p.titulo, "estado": p.estado,
                    "progreso": f"{comp}/{tot}", "tareas_bloqueadas": bloq,
                    "preguntas_pendientes": len(p.preguntas_pendientes),
                })
            return resumen

    def formatear_plan_legible(self, id_plan: str) -> str:
        with _bloqueo_persistencia:
            plan = self._planes.get(id_plan)
            if not plan:
                return f"Plan '{id_plan}' no encontrado."
            lineas = [f"=== PLAN: {plan.titulo.upper()} [{plan.estado.upper()}] ===", f"Objetivo: {plan.objetivo_general}"]
            if plan.preguntas_pendientes:
                lineas.append("\nPreguntas pendientes:")
                for pr in plan.preguntas_pendientes:
                    lineas.append(f"  ? {pr}")
            for f in plan.fases:
                lineas.append(f"\n[Fase {f.orden}: {f.nombre}] ({f.estado})")
                for t in f.tareas:
                    m = "✔" if t.estado == pm.ESTADO_COMPLETADA else ("✖" if t.estado == pm.ESTADO_BLOQUEADA else "•")
                    deps = f" [requiere: {', '.join(t.dependencias)}]" if t.dependencias else ""
                    lineas.append(f"  {m} [{t.id_tarea}] {t.titulo} (Prioridad: {t.puntaje_prioridad}){deps}")
                    if t.motivo_bloqueo:
                        lineas.append(f"      Bloqueo: {t.motivo_bloqueo}")
                    for st in t.subtareas:
                        sm = "✔" if st.estado == pm.ESTADO_COMPLETADA else "○"
                        lineas.append(f"      {sm} {st.titulo}")
            return "\n".join(lineas)


_planificador_instancia: Optional[Planificador] = None
_bloqueo_singleton = threading.Lock()


def obtener_planificador() -> Planificador:
    global _planificador_instancia
    with _bloqueo_singleton:
        if _planificador_instancia is None:
            _planificador_instancia = Planificador()
        return _planificador_instancia


def instalar(app: Any = None) -> Planificador:
    planif = obtener_planificador()
    try:
        import acciones
        acciones.registrar("consultar_planes", lambda: f"Planes: {len(planif.listar_planes())}", "consulta planes activos")
        acciones.registrar("siguiente_paso_plan", lambda: planif.recomendar_siguiente_paso(app=app).get("recomendacion_texto", "Sin tareas."), "siguiente tarea recomendada")
    except Exception as e:
        print(f"[planificador] Error registrando acciones: {e}", flush=True)
    return planif
