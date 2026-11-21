"""Progreso verificable, bloqueos y replanificación incremental de tareas."""
import hashlib
import json

import planificador_modelo as pm


def huella_contexto(contexto):
    if not isinstance(contexto, dict):
        contexto = {}
    datos = {k: contexto.get(k, {}) for k in ("detectado", "probable", "confirmado", "multimodal")}
    return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def progreso(plan):
    tareas = plan.todas_las_tareas()
    estados = (pm.ESTADO_PENDIENTE, pm.ESTADO_EN_PROGRESO, pm.ESTADO_BLOQUEADA,
               pm.ESTADO_COMPLETADA, pm.ESTADO_FALLIDA, pm.ESTADO_CANCELADA)
    conteo = {x: sum(t.estado == x for t in tareas) for x in estados}
    return {"total": len(tareas), "estados": conteo,
            "porcentaje": round(100 * conteo[pm.ESTADO_COMPLETADA] / len(tareas), 1) if tareas else 0.0}


def verificar_criterio(criterio, evidencia, confirmacion_usuario=False):
    """No marca progreso por texto generado; exige evidencia y aprobación explícitas."""
    if not criterio or not str(evidencia or "").strip():
        return False
    if criterio.requiere_confirmacion_usuario and not confirmacion_usuario:
        return False
    esperado = str(criterio.evidencia_requerida or "").strip().casefold()
    return bool(esperado and esperado in str(evidencia).casefold())


def actualizar_estado(plan, id_tarea, nuevo_estado, motivo=""):
    if nuevo_estado not in pm.ESTADOS_VALIDOS:
        raise ValueError("estado de tarea inválido")
    mapa = plan.mapa_tareas()
    if id_tarea not in mapa:
        raise KeyError(id_tarea)
    if nuevo_estado == pm.ESTADO_BLOQUEADA:
        impactadas = pm.marcar_tarea_bloqueada(plan, id_tarea, motivo)
    else:
        t = mapa[id_tarea]
        t.estado = nuevo_estado
        t.motivo_bloqueo = str(motivo)[:240] if nuevo_estado == pm.ESTADO_FALLIDA else ""
        plan.registrar_cambio("estado_tarea", f"{id_tarea}:{nuevo_estado}")
        plan.actualizar_estado_general()
        impactadas = []
        if nuevo_estado == pm.ESTADO_FALLIDA:
            impactadas = pm.marcar_tarea_bloqueada(plan, id_tarea, motivo or "Dependencia fallida")
            t.estado = pm.ESTADO_FALLIDA
            for tid in impactadas:
                afectada = mapa[tid]
                if afectada.estado not in (pm.ESTADO_COMPLETADA, pm.ESTADO_CANCELADA):
                    afectada.estado = pm.ESTADO_BLOQUEADA
                    afectada.motivo_bloqueo = "Dependencia fallida: " + str(id_tarea)
            plan.actualizar_estado_general()
    return impactadas


def detectar_retraso(plan, fecha_limite=None, ahora=None):
    if fecha_limite is None:
        return False
    import time
    return float(ahora or time.time()) > float(fecha_limite) and plan.estado != pm.ESTADO_COMPLETADA


def replanificar_incremental(plan, nueva_version, requisitos=None, restricciones=None):
    """Fusiona tareas nuevas/pending; los IDs completados permanecen sin cambios."""
    if not isinstance(nueva_version, pm.PlanObjetivo):
        raise TypeError("nueva_version debe ser PlanObjetivo")
    completadas = {t.id_tarea for t in plan.todas_las_tareas() if t.estado == pm.ESTADO_COMPLETADA}
    pm.replanificar_por_cambio_requisitos(plan, requisitos, restricciones)
    actuales = plan.mapa_tareas()
    fases = {f.id_fase: f for f in plan.fases}
    for nf in nueva_version.fases:
        destino = fases.get(nf.id_fase)
        if destino is None:
            destino = pm.Fase.de_dict(nf.a_dict())
            destino.tareas = []
            plan.fases.append(destino)
            fases[destino.id_fase] = destino
        for nt in nf.tareas:
            existente = actuales.get(nt.id_tarea)
            if existente and existente.estado in (pm.ESTADO_PENDIENTE, pm.ESTADO_BLOQUEADA):
                estado, motivo = existente.estado, existente.motivo_bloqueo
                existente.titulo, existente.descripcion = nt.titulo, nt.descripcion
                existente.importancia, existente.urgencia = nt.importancia, nt.urgencia
                existente.complejidad, existente.dependencias = nt.complejidad, list(nt.dependencias)
                existente.estado, existente.motivo_bloqueo = estado, motivo
            elif not existente and nt.estado == pm.ESTADO_PENDIENTE:
                destino.tareas.append(nt)
    valido, errores = pm.validar_dependencias(plan)
    if not valido:
        raise ValueError("replanificación inválida: " + "; ".join(errores[:3]))
    if not completadas.issubset({t.id_tarea for t in plan.todas_las_tareas() if t.estado == pm.ESTADO_COMPLETADA}):
        raise RuntimeError("la adaptación alteró tareas completadas")
    for tarea in plan.todas_las_tareas():
        if tarea.estado == pm.ESTADO_BLOQUEADA and tarea.motivo_bloqueo.startswith("Dependencia fallida:") and all(
                plan.mapa_tareas().get(dep) and plan.mapa_tareas()[dep].estado == pm.ESTADO_COMPLETADA
                for dep in tarea.dependencias):
            tarea.estado, tarea.motivo_bloqueo = pm.ESTADO_PENDIENTE, ""
        tarea.calcular_puntaje()
    plan.actualizar_estado_general()
    return plan
