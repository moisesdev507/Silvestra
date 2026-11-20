"""Modelo de datos jerárquico, grafo de dependencias y replanificación (Etapa 6)."""
from __future__ import annotations

import time
from typing import Any, Optional

ESTADO_PENDIENTE = "pendiente"
ESTADO_EN_PROGRESO = "en_progreso"
ESTADO_COMPLETADA = "completada"
ESTADO_BLOQUEADA = "bloqueada"
ESTADO_CANCELADA = "cancelada"

ESTADOS_VALIDOS = {
    ESTADO_PENDIENTE, ESTADO_EN_PROGRESO, ESTADO_COMPLETADA,
    ESTADO_BLOQUEADA, ESTADO_CANCELADA,
}
FACTOR_COMPLEJIDAD = {"baja": 1.0, "media": 0.5, "alta": 0.0}


class Subtarea:
    """Subtarea atómica dentro de una tarea mayor."""

    def __init__(self, id_subtarea: str, titulo: str, estado: str = ESTADO_PENDIENTE):
        self.id_subtarea = str(id_subtarea)
        self.titulo = str(titulo).strip()
        self.estado = estado if estado in ESTADOS_VALIDOS else ESTADO_PENDIENTE

    def a_dict(self) -> dict[str, Any]:
        return {"id_subtarea": self.id_subtarea, "titulo": self.titulo, "estado": self.estado}

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> Subtarea:
        return cls(d.get("id_subtarea", ""), d.get("titulo", ""), d.get("estado", ESTADO_PENDIENTE))


class Tarea:
    """Tarea ejecutable con dependencias, estimaciones y prioridad calculada."""

    def __init__(
        self,
        id_tarea: str,
        titulo: str,
        descripcion: str = "",
        fase_id: str = "",
        estado: str = ESTADO_PENDIENTE,
        importancia: int = 3,
        urgencia: int = 3,
        complejidad: str = "media",
        dependencias: Optional[list[str]] = None,
        motivo_bloqueo: str = "",
        subtareas: Optional[list[Subtarea]] = None,
    ):
        self.id_tarea = str(id_tarea)
        self.titulo = str(titulo).strip()
        self.descripcion = str(descripcion).strip()
        self.fase_id = str(fase_id)
        self.estado = estado if estado in ESTADOS_VALIDOS else ESTADO_PENDIENTE
        self.importancia = max(1, min(5, int(importancia)))
        self.urgencia = max(1, min(5, int(urgencia)))
        self.complejidad = complejidad.lower() if complejidad.lower() in FACTOR_COMPLEJIDAD else "media"
        self.dependencias = [str(dep) for dep in (dependencias or [])]
        self.motivo_bloqueo = str(motivo_bloqueo)
        self.subtareas = subtareas or []
        self.puntaje_prioridad = self.calcular_puntaje()

    def calcular_puntaje(self, desbloqueadas: int = 0) -> float:
        fc = FACTOR_COMPLEJIDAD.get(self.complejidad, 0.5)
        puntaje = (self.importancia * 2.0) + (self.urgencia * 1.5) + (desbloqueadas * 1.0) + fc
        self.puntaje_prioridad = round(puntaje, 2)
        return self.puntaje_prioridad

    def a_dict(self) -> dict[str, Any]:
        return {
            "id_tarea": self.id_tarea, "titulo": self.titulo, "descripcion": self.descripcion,
            "fase_id": self.fase_id, "estado": self.estado, "importancia": self.importancia,
            "urgencia": self.urgencia, "complejidad": self.complejidad,
            "puntaje_prioridad": self.puntaje_prioridad, "dependencias": list(self.dependencias),
            "motivo_bloqueo": self.motivo_bloqueo, "subtareas": [st.a_dict() for st in self.subtareas],
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> Tarea:
        sts = [Subtarea.de_dict(st) for st in d.get("subtareas", [])]
        t = cls(
            d.get("id_tarea", ""), d.get("titulo", ""), d.get("descripcion", ""),
            d.get("fase_id", ""), d.get("estado", ESTADO_PENDIENTE),
            d.get("importancia", 3), d.get("urgencia", 3), d.get("complejidad", "media"),
            d.get("dependencias", []), d.get("motivo_bloqueo", ""), sts,
        )
        t.puntaje_prioridad = float(d.get("puntaje_prioridad", t.calcular_puntaje()))
        return t


class Fase:
    """Fase estructurada que agrupa tareas ordenadas."""

    def __init__(
        self,
        id_fase: str,
        orden: int,
        nombre: str,
        descripcion: str = "",
        estado: str = ESTADO_PENDIENTE,
        tareas: Optional[list[Tarea]] = None,
    ):
        self.id_fase = str(id_fase)
        self.orden = int(orden)
        self.nombre = str(nombre).strip()
        self.descripcion = str(descripcion).strip()
        self.estado = estado if estado in ESTADOS_VALIDOS else ESTADO_PENDIENTE
        self.tareas = tareas or []

    def actualizar_estado(self) -> str:
        if not self.tareas:
            return self.estado
        estados = {t.estado for t in self.tareas}
        if estados == {ESTADO_COMPLETADA}:
            self.estado = ESTADO_COMPLETADA
        elif ESTADO_BLOQUEADA in estados:
            self.estado = ESTADO_BLOQUEADA
        elif ESTADO_EN_PROGRESO in estados or (ESTADO_COMPLETADA in estados and ESTADO_PENDIENTE in estados):
            self.estado = ESTADO_EN_PROGRESO
        elif estados == {ESTADO_CANCELADA}:
            self.estado = ESTADO_CANCELADA
        else:
            self.estado = ESTADO_PENDIENTE
        return self.estado

    def a_dict(self) -> dict[str, Any]:
        return {
            "id_fase": self.id_fase, "orden": self.orden, "nombre": self.nombre,
            "descripcion": self.descripcion, "estado": self.estado,
            "tareas": [t.a_dict() for t in self.tareas],
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> Fase:
        ts = [Tarea.de_dict(t) for t in d.get("tareas", [])]
        return cls(
            d.get("id_fase", ""), d.get("orden", 1), d.get("nombre", ""),
            d.get("descripcion", ""), d.get("estado", ESTADO_PENDIENTE), ts,
        )


class RegistroCambio:
    """Registro auditado de modificaciones, replanificaciones y bloqueos."""

    def __init__(self, tipo: str, detalle: str, timestamp: Optional[float] = None):
        self.tipo = str(tipo)
        self.detalle = str(detalle)
        self.timestamp = time.time() if timestamp is None else float(timestamp)

    def a_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "detalle": self.detalle, "timestamp": self.timestamp}

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> RegistroCambio:
        return cls(d.get("tipo", "general"), d.get("detalle", ""), d.get("timestamp", 0.0))


class PlanObjetivo:
    """Entidad principal que almacena el objetivo descompuesto y su historial."""

    def __init__(
        self,
        id_plan: str,
        titulo: str,
        objetivo_general: str,
        requisitos: Optional[list[str]] = None,
        restricciones: Optional[list[str]] = None,
        preguntas_pendientes: Optional[list[str]] = None,
        estado: str = ESTADO_PENDIENTE,
        fases: Optional[list[Fase]] = None,
        historial_cambios: Optional[list[RegistroCambio]] = None,
        creado_en: Optional[float] = None,
        actualizado_en: Optional[float] = None,
    ):
        t_ahora = time.time()
        self.id_plan = str(id_plan)
        self.titulo = str(titulo).strip()
        self.objetivo_general = str(objetivo_general).strip()
        self.requisitos = [str(r).strip() for r in (requisitos or []) if str(r).strip()]
        self.restricciones = [str(res).strip() for res in (restricciones or []) if str(res).strip()]
        self.preguntas_pendientes = [str(p).strip() for p in (preguntas_pendientes or []) if str(p).strip()]
        self.estado = estado if estado in ESTADOS_VALIDOS else ESTADO_PENDIENTE
        self.fases = sorted(fases or [], key=lambda f: f.orden)
        self.historial_cambios = historial_cambios or [RegistroCambio("creacion", "Plan inicial creado", t_ahora)]
        self.creado_en = t_ahora if creado_en is None else float(creado_en)
        self.actualizado_en = t_ahora if actualizado_en is None else float(actualizado_en)

    def registrar_cambio(self, tipo: str, detalle: str) -> None:
        self.actualizado_en = time.time()
        self.historial_cambios.append(RegistroCambio(tipo, detalle, self.actualizado_en))

    def todas_las_tareas(self) -> list[Tarea]:
        return [t for f in self.fases for t in f.tareas]

    def mapa_tareas(self) -> dict[str, Tarea]:
        return {t.id_tarea: t for t in self.todas_las_tareas()}

    def actualizar_estado_general(self) -> str:
        for f in self.fases:
            f.actualizar_estado()
        estados = {f.estado for f in self.fases} if self.fases else {self.estado}
        if estados == {ESTADO_COMPLETADA}:
            self.estado = ESTADO_COMPLETADA
        elif ESTADO_BLOQUEADA in estados:
            self.estado = ESTADO_BLOQUEADA
        elif ESTADO_EN_PROGRESO in estados or (ESTADO_COMPLETADA in estados and ESTADO_PENDIENTE in estados):
            self.estado = ESTADO_EN_PROGRESO
        elif estados == {ESTADO_CANCELADA}:
            self.estado = ESTADO_CANCELADA
        else:
            self.estado = ESTADO_PENDIENTE
        self.actualizado_en = time.time()
        return self.estado

    def a_dict(self) -> dict[str, Any]:
        return {
            "id_plan": self.id_plan, "titulo": self.titulo,
            "objetivo_general": self.objetivo_general,
            "requisitos": list(self.requisitos), "restricciones": list(self.restricciones),
            "preguntas_pendientes": list(self.preguntas_pendientes), "estado": self.estado,
            "fases": [f.a_dict() for f in self.fases],
            "historial_cambios": [h.a_dict() for h in self.historial_cambios],
            "creado_en": self.creado_en, "actualizado_en": self.actualizado_en,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> PlanObjetivo:
        fs = [Fase.de_dict(f) for f in d.get("fases", [])]
        hs = [RegistroCambio.de_dict(h) for h in d.get("historial_cambios", [])]
        return cls(
            d.get("id_plan", ""), d.get("titulo", ""), d.get("objetivo_general", ""),
            d.get("requisitos", []), d.get("restricciones", []),
            d.get("preguntas_pendientes", []), d.get("estado", ESTADO_PENDIENTE),
            fs, hs, d.get("creado_en"), d.get("actualizado_en"),
        )


def validar_dependencias(plan: PlanObjetivo) -> tuple[bool, list[str]]:
    """Valida dependencias y detecta referencias rotas o ciclos mediante DFS."""
    mapa = plan.mapa_tareas()
    errores: list[str] = []

    for tid, tarea in mapa.items():
        for dep in tarea.dependencias:
            if dep not in mapa:
                errores.append(f"Tarea '{tid}' depende de '{dep}' inexistente.")
            elif dep == tid:
                errores.append(f"Tarea '{tid}' tiene auto-dependencia cíclica.")

    if errores:
        return False, errores

    visitado: dict[str, int] = {tid: 0 for tid in mapa}

    def dfs(tid: str, camino: list[str]) -> bool:
        visitado[tid] = 1
        camino.append(tid)
        for dep in mapa[tid].dependencias:
            if dep not in visitado:
                continue
            if visitado[dep] == 1:
                idx = camino.index(dep)
                errores.append("Ciclo: " + " -> ".join(camino[idx:] + [dep]))
                return False
            if visitado[dep] == 0:
                if not dfs(dep, camino):
                    return False
        visitado[tid] = 2
        camino.pop()
        return True

    for tid in mapa:
        if visitado[tid] == 0 and not dfs(tid, []):
            return False, errores

    return True, []


def obtener_tareas_accionables(plan: PlanObjetivo) -> list[Tarea]:
    """Retorna las tareas listas para ejecutar (pendientes con dependencias resueltas)."""
    mapa = plan.mapa_tareas()
    desbloqueadas: dict[str, int] = {tid: 0 for tid in mapa}
    for tid, tarea in mapa.items():
        for dep in tarea.dependencias:
            if dep in desbloqueadas:
                desbloqueadas[dep] += 1

    accionables: list[Tarea] = []
    for tid, tarea in mapa.items():
        if tarea.estado != ESTADO_PENDIENTE:
            continue
        if all(dep in mapa and mapa[dep].estado == ESTADO_COMPLETADA for dep in tarea.dependencias):
            tarea.calcular_puntaje(desbloqueadas=desbloqueadas.get(tid, 0))
            accionables.append(tarea)

    accionables.sort(key=lambda t: t.puntaje_prioridad, reverse=True)
    return accionables


def marcar_tarea_bloqueada(plan: PlanObjetivo, id_tarea: str, motivo: str) -> list[str]:
    """Marca una tarea como bloqueada, propaga impacto sobre dependientes y audita."""
    mapa = plan.mapa_tareas()
    if id_tarea not in mapa:
        return []

    tarea = mapa[id_tarea]
    tarea.estado = ESTADO_BLOQUEADA
    tarea.motivo_bloqueo = str(motivo).strip() or "Bloqueo no especificado"

    impactadas: set[str] = set()
    cola = [id_tarea]
    while cola:
        actual = cola.pop(0)
        for tid, t in mapa.items():
            if actual in t.dependencias and tid not in impactadas:
                impactadas.add(tid)
                cola.append(tid)

    det = f"Tarea '{id_tarea}' bloqueada por: '{tarea.motivo_bloqueo}'. Impacta en {len(impactadas)} dependientes."
    plan.registrar_cambio("bloqueo", det)
    plan.actualizar_estado_general()
    return list(impactadas)


def replanificar_por_cambio_requisitos(
    plan: PlanObjetivo,
    nuevos_requisitos: Optional[list[str]] = None,
    nuevas_restricciones: Optional[list[str]] = None,
) -> list[RegistroCambio]:
    """Actualiza requisitos/restricciones, reevalúa plan y registra auditoría."""
    detalles: list[str] = []
    if nuevos_requisitos is not None:
        plan.requisitos = [str(r).strip() for r in nuevos_requisitos if str(r).strip()]
        detalles.append(f"Requisitos actualizados ({len(plan.requisitos)} ítems)")

    if nuevas_restricciones is not None:
        plan.restricciones = [str(res).strip() for res in nuevas_restricciones if str(res).strip()]
        detalles.append(f"Restricciones actualizadas ({len(plan.restricciones)} ítems)")

    plan.registrar_cambio("replanificacion", "; ".join(detalles) if detalles else "Reevaluación de plan")
    plan.actualizar_estado_general()
    return plan.historial_cambios
