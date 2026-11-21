"""Puente no bloqueante entre orquestador, Cerebro, Planificador y HUD."""
from __future__ import annotations

from typing import Any, Optional

from autonomia_modelo import (
    COMPLETADA, CANCELADA, ESPERANDO_AUTORIZACION,
    REQUIERE_INTERVENCION,
)


class PuenteAutonomiaSilvestra:
    def __init__(self, orquestador: Any, cerebro=None, planificador=None,
                 contexto_motor=None, app_cola=None) -> None:
        self.orquestador = orquestador
        self.cerebro = cerebro
        self.planificador = planificador
        self.contexto_motor = contexto_motor
        self.app_cola = app_cola
        if getattr(orquestador, "app_cola", None) is None:
            orquestador.app_cola = app_cola

    def recibir_objetivo(
        self,
        objetivo: str,
        origen: str = "usuario",
        requiere_ejecucion: bool = False,
    ):
        return self.orquestador.recibir(
            objetivo,
            origen=origen,
            requiere_ejecucion=requiere_ejecucion,
        )

    def obtener_estado_hud(self) -> dict:
        ordenes = self.orquestador.listar_ordenes()
        activas = [
            o.a_dict() for o in ordenes
            if o.estado not in (COMPLETADA, CANCELADA)
        ]
        esperando = [
            {
                "id_orden": o.id_orden,
                "paso": p.id_paso,
                "herramienta": p.herramienta,
                "id_autorizacion": p.id_autorizacion,
            }
            for o in ordenes
            for p in o.pasos
            if p.estado == ESPERANDO_AUTORIZACION
        ]
        pendientes_plan = []
        if self.planificador is not None:
            try:
                for plan in self.planificador.listar_planes():
                    pendientes_plan.append({
                        "id_plan": plan.id_plan,
                        "titulo": plan.titulo,
                        "estado": plan.estado,
                    })
            except Exception:
                pass
        contexto = None
        if self.contexto_motor is not None:
            try:
                contexto = self.contexto_motor.obtener_contexto()
            except Exception:
                contexto = None
        historial = []
        for orden in ordenes[-10:]:
            historial.extend(orden.historial_eventos[-3:])
        return {
            "tareas_activas": activas,
            "planes": pendientes_plan,
            "progreso": [
                {"id_orden": o.id_orden, "progreso_pct": o.progreso_pct}
                for o in ordenes
            ],
            "esperando_autorizacion": esperando,
            "errores_intervencion": [
                o.id_orden for o in ordenes
                if o.estado == REQUIERE_INTERVENCION
            ],
            "canceladas": [
                o.id_orden for o in ordenes if o.estado == CANCELADA
            ],
            "historial_reciente": historial[-30:],
            "contexto": contexto,
        }

    def publicar_snapshot(self) -> dict:
        snapshot = self.obtener_estado_hud()
        if self.app_cola is not None:
            try:
                payload = {"tipo": "hud_autonomia", "snapshot": snapshot}
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("autonomia_estado", payload))
                else:
                    self.app_cola.put(("autonomia_estado", payload), block=False)
            except Exception:
                pass
        return snapshot
