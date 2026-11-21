"""Orquestador central de autonomia operativa controlada."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from autonomia_modelo import (
    COMPLETADA, CANCELADA, ESPERANDO_AUTORIZACION, EJECUTANDO,
    FALLIDA, PARCIAL, PLANIFICANDO, RECIBIDA,
    RESPONDIDA_SIN_EJECUCION, RESTRINGIDO, SUPERVISADO,
    PREAUTORIZADO, REQUIERE_INTERVENCION,
    InformeOperativoFinal, OrdenOperativa, PasoPlanOperativo,
)
from ejecucion_modelo import ResultadoEjecucion, SolicitudEjecucion
from persistencia_segura import guardar_json_atomico


class OrquestadorAutonomiaSilvestra:
    def __init__(
        self,
        registro=None,
        motor_permisos=None,
        motor_ejecucion=None,
        verificador=None,
        planificador=None,
        contexto_motor=None,
        app_cola=None,
        archivo_persistencia=None,
    ) -> None:
        self.registro = registro
        self.motor_permisos = motor_permisos
        self.motor_ejecucion = motor_ejecucion
        self.verificador = verificador
        self.planificador = planificador
        self.contexto_motor = contexto_motor
        self.app_cola = app_cola
        self.archivo_persistencia = archivo_persistencia
        self._bloqueo = threading.RLock()
        self._ordenes: dict[str, OrdenOperativa] = {}
        self._modo = SUPERVISADO
        self._cerrando = False

    def cambiar_modo(self, modo: str, actor: str = "usuario") -> bool:
        actor_norm = str(actor).strip().lower()
        if actor_norm != "usuario":
            return False
        if modo not in (RESTRINGIDO, SUPERVISADO, PREAUTORIZADO):
            return False
        with self._bloqueo:
            self._modo = modo
        return True

    def modo_actual(self) -> str:
        with self._bloqueo:
            return self._modo

    def validar_dag(self, pasos: list[PasoPlanOperativo]) -> tuple[bool, str]:
        ids = {p.id_paso for p in pasos}
        if len(ids) != len(pasos):
            return False, "DEPENDENCIAS_INVALIDAS"
        for paso in pasos:
            if any(dep not in ids for dep in paso.dependencias):
                return False, "DEPENDENCIAS_INVALIDAS"
        visitado: dict[str, int] = {id_paso: 0 for id_paso in ids}
        mapa = {p.id_paso: p for p in pasos}

        def dfs(id_paso: str) -> bool:
            visitado[id_paso] = 1
            for dep in mapa[id_paso].dependencias:
                if visitado[dep] == 1:
                    return False
                if visitado[dep] == 0 and not dfs(dep):
                    return False
            visitado[id_paso] = 2
            return True

        for id_paso in ids:
            if visitado[id_paso] == 0 and not dfs(id_paso):
                return False, "DEPENDENCIAS_INVALIDAS"
        return True, ""

    def recibir(
        self,
        objetivo: str,
        origen: str = "usuario",
        requiere_ejecucion: bool = False,
        pasos: Optional[list[PasoPlanOperativo]] = None,
        modo: Optional[str] = None,
    ) -> OrdenOperativa:
        modo_orden = modo or self.modo_actual()
        orden = OrdenOperativa(
            objetivo=objetivo,
            origen=origen,
            modo_autonomia=modo_orden,
            requiere_ejecucion=bool(requiere_ejecucion),
            pasos=list(pasos or []),
        )
        if not requiere_ejecucion:
            orden.estado = RESPONDIDA_SIN_EJECUCION
            orden.registrar_evento("respondida_sin_ejecucion", "Sin herramientas")
        elif modo_orden == RESTRINGIDO:
            orden.estado = PLANIFICANDO
            orden.registrar_evento("rechazada_modo_restringido",
                                   "Modo restringido sin ejecucion")
        else:
            orden.estado = PLANIFICANDO
            orden.registrar_evento("planificacion", "Plan recibido")
        with self._bloqueo:
            self._ordenes[orden.id_orden] = orden
        self._emitir(orden)
        return orden

    def obtener_orden(self, id_orden: str) -> Optional[OrdenOperativa]:
        with self._bloqueo:
            return self._ordenes.get(id_orden)

    def listar_ordenes(self) -> list[OrdenOperativa]:
        with self._bloqueo:
            return list(self._ordenes.values())

    def _emitir(self, orden: OrdenOperativa) -> None:
        if self.app_cola is not None:
            try:
                payload = {
                    "tipo": "autonomia_estado",
                    "orden": orden.a_dict(),
                }
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("autonomia_estado", payload))
                else:
                    self.app_cola.put(("autonomia_estado", payload), block=False)
            except Exception:
                pass

    def ejecutar_plan(self, id_orden: str) -> OrdenOperativa:
        orden = self.obtener_orden(id_orden)
        if orden is None:
            raise KeyError("Orden inexistente")
        if orden.estado == RESPONDIDA_SIN_EJECUCION:
            return orden
        if orden.modo_autonomia == RESTRINGIDO:
            orden.estado = FALLIDA
            orden.registrar_evento("rechazada_modo_restringido")
            self._emitir(orden)
            return orden

        valido, motivo = self.validar_dag(orden.pasos)
        if not valido:
            orden.estado = FALLIDA
            orden.registrar_evento(motivo)
            orden.actualizar_progreso()
            self._emitir(orden)
            return orden
        orden.estado = EJECUTANDO
        orden.registrar_evento("ejecutando", "Plan validado")
        pendientes = {p.id_paso: p for p in orden.pasos}

        while pendientes:
            completados = {
                p.id_paso for p in orden.pasos
                if p.estado == COMPLETADA
            }
            listos = [
                p for p in list(pendientes.values())
                if set(p.dependencias).issubset(completados)
            ]
            if not listos:
                break
            for paso in listos:
                if self._cerrando:
                    paso.estado = CANCELADA
                    self._emitir(orden)
                else:
                    self._ejecutar_paso(orden, paso)
                pendientes.pop(paso.id_paso, None)
            orden.actualizar_progreso()
            self._emitir(orden)
        self._finalizar(orden)
        return orden

    def _ejecutar_paso(
        self,
        orden: OrdenOperativa,
        paso: PasoPlanOperativo,
    ) -> None:
        if self.registro is None or self.motor_permisos is None:
            paso.estado = REQUIERE_INTERVENCION
            orden.registrar_evento("componente_no_disponible", paso.id_paso)
            return
        contrato = self.registro.obtener(paso.herramienta)
        if contrato is None:
            paso.estado = FALLIDA
            orden.registrar_evento("herramienta_inexistente", paso.id_paso)
            return
        solicitud = SolicitudEjecucion(
            origen="planificador",
            herramienta=paso.herramienta,
            parametros=paso.parametros,
        )
        paso.id_solicitud = solicitud.id_solicitud

        decision = self.motor_permisos.evaluar_solicitud(solicitud, contrato)
        permitido_sin_pausa = False
        if orden.modo_autonomia == PREAUTORIZADO:
            politica = None
            try:
                politica = self.motor_permisos._obtener_politica(
                    solicitud, contrato
                )
            except Exception:
                politica = None
            permitido_sin_pausa = (
                decision.get("decision") == "permitida"
                and politica is not None
                and getattr(politica, "nivel_autorizacion", "") == "solo_lectura"
                and getattr(contrato, "nivel_riesgo", "critico") == "bajo"
            )
        if decision.get("decision") == "pendiente_autorizacion":
            paso.id_autorizacion = decision.get("id_autorizacion")
            paso.estado = ESPERANDO_AUTORIZACION
            orden.estado = ESPERANDO_AUTORIZACION
            orden.registrar_evento("esperando_autorizacion", paso.id_paso)
            return
        if decision.get("decision") != "permitida":
            paso.estado = FALLIDA
            orden.registrar_evento("permiso_denegado", paso.id_paso)
            return
        if orden.modo_autonomia == PREAUTORIZADO and not permitido_sin_pausa:
            paso.estado = ESPERANDO_AUTORIZACION
            orden.estado = ESPERANDO_AUTORIZACION
            orden.registrar_evento("confirmacion_requerida", paso.id_paso)
            return

        if self.motor_ejecucion is None:
            paso.estado = REQUIERE_INTERVENCION
            return
        paso.estado = EJECUTANDO
        resultado = self.motor_ejecucion.encolar(solicitud)
        if hasattr(resultado, "estado") and resultado.estado in (
            "esperando_autorizacion", "pendiente_autorizacion"
        ):
            paso.estado = ESPERANDO_AUTORIZACION
            orden.estado = ESPERANDO_AUTORIZACION
            return
        if getattr(resultado, "exito", False) is False:
            paso.estado = FALLIDA
            return
        if self.verificador is not None:
            informe = self.verificador.verificar_resultado(
                solicitud, resultado, resultado.datos
            )
            paso.informe_verificacion = informe.a_dict()
            if informe.estado_final in ("verificado", "recuperado"):
                paso.estado = COMPLETADA
            elif informe.estado_final == "resultado_parcial":
                paso.estado = PARCIAL
            elif informe.estado_final == "requiere_intervencion_humana":
                paso.estado = REQUIERE_INTERVENCION
            else:
                paso.estado = FALLIDA
        else:
            paso.estado = REQUIERE_INTERVENCION

    def continuar_tras_autorizacion(self, id_orden: str, id_paso: str) -> OrdenOperativa:
        orden = self.obtener_orden(id_orden)
        if orden is None:
            raise KeyError("Orden inexistente")
        paso = next((p for p in orden.pasos if p.id_paso == id_paso), None)
        if paso is None:
            raise KeyError("Paso inexistente")
        if paso.estado != ESPERANDO_AUTORIZACION:
            return orden
        if not paso.id_autorizacion:
            return orden
        self._ejecutar_paso(orden, paso)
        orden.actualizar_progreso()
        self._emitir(orden)
        return orden

    def cancelar_orden(self, id_orden: str) -> bool:
        orden = self.obtener_orden(id_orden)
        if orden is None:
            return False
        self._cerrando = True
        for paso in orden.pasos:
            if paso.estado in (RECIBIDA, PLANIFICANDO, ESPERANDO_AUTORIZACION):
                paso.estado = CANCELADA
        orden.estado = CANCELADA
        orden.registrar_evento("cancelada", "Orden cancelada cooperativamente")
        orden.actualizar_progreso()
        self._emitir(orden)
        self._cerrando = False
        return True

    def _finalizar(self, orden: OrdenOperativa) -> InformeOperativoFinal:
        completados = [p.id_paso for p in orden.pasos if p.estado == COMPLETADA]
        parciales = [p.id_paso for p in orden.pasos if p.estado == PARCIAL]
        fallidas = [p.id_paso for p in orden.pasos
                    if p.estado in (FALLIDA, REQUIERE_INTERVENCION)]
        pendientes = [p.id_paso for p in orden.pasos if p.estado in (
            RECIBIDA, PLANIFICANDO, ESPERANDO_AUTORIZACION
        )]
        cancelados = [p.id_paso for p in orden.pasos if p.estado == CANCELADA]
        if completados and (fallidas or parciales or pendientes):
            orden.estado = PARCIAL
        elif fallidas:
            orden.estado = FALLIDA
        elif pendientes or parciales:
            orden.estado = PARCIAL
        elif cancelados:
            orden.estado = CANCELADA
        else:
            orden.estado = COMPLETADA
        orden.actualizar_progreso()
        informe = InformeOperativoFinal(
            id_orden=orden.id_orden,
            completados=completados,
            parciales=parciales,
            fallidas=fallidas,
            pendientes=pendientes,
            cancelados=cancelados,
            resumen_legible=f"Orden {orden.estado}: {len(completados)} completados.",
            auditoria_sanitizada={
                "modo": orden.modo_autonomia,
                "pasos": [p.a_dict() for p in orden.pasos],
            },
        )
        if self.archivo_persistencia:
            guardar_json_atomico(
                self.archivo_persistencia,
                {"ordenes": [o.a_dict() for o in self._ordenes.values()],
                 "ultimo_informe": informe.a_dict()},
            )
        orden.registrar_evento("finalizada", orden.estado)
        self._emitir(orden)
        return informe
