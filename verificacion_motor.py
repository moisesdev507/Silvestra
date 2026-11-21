"""Motor central de verificacion independiente y recuperacion segura."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from ejecucion_modelo import ResultadoEjecucion, SolicitudEjecucion
from persistencia_segura import guardar_json_atomico
from verificacion_modelo import (
    PENDIENTE,
    VERIFICANDO,
    VERIFICADO,
    FALLIDO,
    RESULTADO_PARCIAL,
    RECUPERACION_PENDIENTE,
    RECUPERANDO,
    RECUPERADO,
    REQUIERE_INTERVENCION,
    CategoriaError,
    EvidenciaVerificacion,
    InformeVerificacion,
    sanitizar_datos,
)
from verificacion_estrategias import RegistroEstrategiasVerificacion


class MotorVerificacionRecuperacion:
    def __init__(
        self,
        motor_permisos: Optional[Any] = None,
        motor_ejecucion: Optional[Any] = None,
        planificador: Optional[Any] = None,
        contexto_motor: Optional[Any] = None,
        app_cola: Optional[Any] = None,
        archivo_persistencia: Optional[str] = None,
        reexecutor: Optional[Callable[..., ResultadoEjecucion]] = None,
    ) -> None:
        self._bloqueo = threading.RLock()
        self.registro = RegistroEstrategiasVerificacion()
        self.motor_permisos = motor_permisos
        self.motor_ejecucion = motor_ejecucion
        self.planificador = planificador
        self.contexto_motor = contexto_motor
        self.app_cola = app_cola
        self.archivo_persistencia = archivo_persistencia
        self.reexecutor = reexecutor
        self._informes: dict[str, InformeVerificacion] = {}
        self._id_solicitudes: set[str] = set()
        self._informe_ids: set[str] = set()

    def suscribir_eventos(self) -> bool:
        if self.motor_ejecucion is None:
            return False
        suscribir = getattr(self.motor_ejecucion, "suscribir_eventos", None)
        if not callable(suscribir):
            return False
        return bool(suscribir(self._evento_ejecucion))

    def _evento_ejecucion(self, evento: dict) -> None:
        tarea = evento.get("tarea", {})
        id_solicitud = tarea.get("id_solicitud")
        if not id_solicitud:
            return
        payload = {
            "tipo": "verificacion_evento",
            "id_solicitud": id_solicitud,
            "estado": evento.get("tipo", "evento"),
        }
        if self.app_cola is not None:
            try:
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("verificacion_evento", payload))
                else:
                    self.app_cola.put(("verificacion_evento", payload), block=False)
            except Exception:
                pass

    def registrar_estrategia(
        self,
        criterio: Any,
        verificador: Callable[..., EvidenciaVerificacion],
        sobrescribir: bool = False,
    ) -> bool:
        return self.registro.registrar(criterio, verificador, sobrescribir)

    def _emitir(self, informe: InformeVerificacion) -> None:
        payload = {"tipo": "verificacion", "informe": informe.a_dict()}
        if self.app_cola is not None:
            try:
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("verificacion_evento", payload))
                else:
                    self.app_cola.put(("verificacion_evento", payload), block=False)
            except Exception:
                pass
        if self.planificador is not None:
            try:
                id_plan = informe.solicitud_original.get("id_plan")
                id_tarea = informe.solicitud_original.get("id_tarea")
                if id_plan and id_tarea and hasattr(self.planificador, "actualizar_estado_tarea"):
                    nuevo = "completada" if informe.estado_final in (
                        "verificado", "recuperado"
                    ) else "bloqueada"
                    motivo = "; ".join(informe.errores_detectados) or informe.estado_final
                    self.planificador.actualizar_estado_tarea(
                        id_plan, id_tarea, nuevo, motivo
                    )
            except Exception:
                pass
        if self.archivo_persistencia:
            try:
                guardar_json_atomico(
                    self.archivo_persistencia,
                    {"informes": [i.a_dict() for i in self._informes.values()]},
                )
            except Exception:
                pass

    def obtener_informe(self, id_solicitud: str) -> Optional[InformeVerificacion]:
        with self._bloqueo:
            return self._informes.get(id_solicitud)

    def listar_informes(self) -> list[dict]:
        with self._bloqueo:
            return [i.a_dict() for i in self._informes.values()]

    def _clasificar_error(self, resultado: ResultadoEjecucion) -> list[str]:
        if not resultado or getattr(resultado, "exito", False):
            return []
        error = getattr(resultado, "error", None) or {}
        codigo = str(error.get("codigo", "")).upper()
        mensaje = str(error.get("mensaje", "")).lower()
        categorias = []
        if "TIMEOUT" in codigo:
            categorias.append(CategoriaError.TIMEOUT)
        if "CANCEL" in codigo:
            categorias.append(CategoriaError.CANCELADA)
        if "PERMISO" in codigo or "AUTORIZ" in codigo:
            categorias.append(CategoriaError.PERMISOS)
        if "TEMPOR" in codigo or "COMUNIC" in codigo or "CONNECTION" in mensaje:
            categorias.append(CategoriaError.TEMPORAL)
        if "DESAPARECID" in codigo or "RECURSO" in codigo:
            categorias.append(CategoriaError.RECURSO_DESAPARECIDO)
        if "PERMANENT" in codigo:
            categorias.append(CategoriaError.PERMANENTE)
        return categorias or [CategoriaError.INCONSISTENTE]

    def verificar_resultado(
        self,
        solicitud: SolicitudEjecucion,
        resultado_ejecucion: ResultadoEjecucion,
        resultado_esperado: Any = None,
    ) -> InformeVerificacion:
        id_s = solicitud.id_solicitud
        with self._bloqueo:
            if id_s in self._id_solicitudes:
                existente = self._informes.get(id_s)
                if existente is not None:
                    return existente
            self._id_solicitudes.add(id_s)
            informe = InformeVerificacion(
                id_solicitud=id_s,
                herramienta=solicitud.herramienta,
                solicitud_original={
                    "origen": solicitud.origen,
                    "herramienta": solicitud.herramienta,
                    "parametros": sanitizar_datos(solicitud.parametros),
                    "id_plan": solicitud.id_plan,
                    "id_tarea": solicitud.id_tarea,
                },
                resultado_esperado=sanitizar_datos(resultado_esperado),
            )
            if not informe.transicionar(VERIFICANDO):
                informe.estado_final = REQUIERE_INTERVENCION
            self._informes[id_s] = informe

        errores = self._clasificar_error(resultado_ejecucion)
        informe.errores_detectados = errores

        criterio = self.registro.obtener_criterio(solicitud.herramienta)
        if criterio is None:
            evidencia = EvidenciaVerificacion(
                "sin_verificador", False, False,
                insuficiente=True,
                datos={"motivo": "verificador ausente"},
            )
        else:
            evidencia = self.registro.verificar(
                solicitud.herramienta,
                solicitud,
                resultado_ejecucion,
                resultado_esperado,
            )
        informe.evidencia = evidencia

        if evidencia.positiva():
            informe.transicionar(VERIFICADO)
            self._emitir(informe)
            return informe

        parcial = evidencia.es_parcial
        if evidencia.insuficiente and not parcial:
            informe.errores_detectados.append(CategoriaError.INCONSISTENTE)
        if parcial:
            if not informe.transicionar(RESULTADO_PARCIAL):
                informe.estado_final = REQUIERE_INTERVENCION
            else:
                if not informe.transicionar(RECUPERACION_PENDIENTE):
                    informe.estado_final = REQUIERE_INTERVENCION
        if parcial and criterio is not None:
            recuperado = self._recuperar(
                solicitud, resultado_ejecucion, criterio, informe,
                punto_seguro=True,
            )
            if recuperado:
                informe.transicionar(RECUPERADO)
            elif informe.estado_final not in (
                REQUIERE_INTERVENCION, RECUPERADO
            ):
                informe.estado_final = REQUIERE_INTERVENCION
        else:
            seguro = self._puede_recuperar(
                resultado_ejecucion, criterio, informe, parcial
            )
            if seguro:
                recuperado = self._recuperar(
                    solicitud, resultado_ejecucion, criterio, informe,
                    punto_seguro=False,
                )
                if recuperado:
                    informe.transicionar(RECUPERADO)
            if informe.estado_final not in (RECUPERADO, REQUIERE_INTERVENCION):
                informe.estado_final = REQUIERE_INTERVENCION
        with self._bloqueo:
            self._informes[id_s] = informe
        self._emitir(informe)
        return informe

    def _puede_recuperar(
        self,
        resultado: ResultadoEjecucion,
        criterio: Any,
        informe: InformeVerificacion,
        parcial: bool,
    ) -> bool:
        if criterio is None:
            return False
        if not criterio.idempotente:
            return False
        if criterio.estrategia_recuperacion not in (
            "reintento_idempotente", "reanudar_punto_seguro"
        ):
            return False
        if informe.intentos_realizados >= criterio.max_reintentos:
            return False
        categorias = set(informe.errores_detectados)
        if CategoriaError.PERMISOS in categorias:
            return False
        if CategoriaError.PERMANENTE in categorias:
            return False
        if CategoriaError.CANCELADA in categorias:
            return False
        if parcial:
            return criterio.estrategia_recuperacion == "reanudar_punto_seguro"
        return (
            CategoriaError.TEMPORAL in categorias
            or CategoriaError.COMUNICACION in categorias
        )

    def _permiso_valido(
        self,
        solicitud: SolicitudEjecucion,
        criterio: Any,
    ) -> bool:
        if self.motor_permisos is None:
            return False
        try:
            metodo = getattr(self.motor_permisos, "validar_antes_de_ejecutar", None)
            if callable(metodo):
                return bool(metodo(solicitud, criterio).get("permitida"))
            evaluar = getattr(self.motor_permisos, "evaluar_solicitud", None)
            if not callable(evaluar):
                return False
            decision = evaluar(solicitud, criterio)
            return decision.get("decision") == "permitida"
        except Exception:
            return False

    def _recuperar(
        self,
        solicitud: SolicitudEjecucion,
        resultado: ResultadoEjecucion,
        criterio: Any,
        informe: InformeVerificacion,
        punto_seguro: bool,
    ) -> bool:
        if informe.intentos_realizados >= criterio.max_reintentos:
            informe.estado_final = REQUIERE_INTERVENCION
            return False
        if not self._permiso_valido(solicitud, criterio):
            informe.estado_final = REQUIERE_INTERVENCION
            informe.errores_detectados.append(CategoriaError.PERMISOS)
            informe.acciones_recuperacion.append("permiso_revocado_o_fallido")
            return False
        if not criterio.idempotente:
            informe.estado_final = REQUIERE_INTERVENCION
            return False
        if informe.estado_final == RECUPERACION_PENDIENTE:
            if not informe.transicionar(RECUPERANDO):
                informe.estado_final = REQUIERE_INTERVENCION
                return False
        elif informe.estado_final == VERIFICANDO:
            if not informe.transicionar(RECUPERACION_PENDIENTE):
                informe.estado_final = REQUIERE_INTERVENCION
                return False
            if not informe.transicionar(RECUPERANDO):
                informe.estado_final = REQUIERE_INTERVENCION
                return False
        else:
            informe.estado_final = REQUIERE_INTERVENCION
            return False
        informe.intentos_realizados += 1
        informe.acciones_recuperacion.append(
            "reanudar_punto_seguro" if punto_seguro else "reintento_idempotente"
        )
        if criterio.backoff_seg:
            time.sleep(min(1.0, criterio.backoff_seg))
        if self.reexecutor is None:
            evidencia = EvidenciaVerificacion(
                "recuperacion_sin_reexecutor",
                False,
                False,
                insuficiente=True,
                datos={"motivo": "sin evidencia posterior"},
            )
        else:
            try:
                nuevo_resultado = self.reexecutor(solicitud)
                evidencia = self.registro.verificar(
                    solicitud.herramienta,
                    solicitud,
                    nuevo_resultado,
                    resultado,
                )
            except Exception:
                evidencia = EvidenciaVerificacion(
                    "recuperacion",
                    False,
                    False,
                    insuficiente=True,
                    datos={"motivo": "reexecutor fallo"},
                )
        informe.evidencia = evidencia
        if evidencia.positiva():
            informe.transicionar(RECUPERADO)
            return True
        if informe.intentos_realizados >= criterio.max_reintentos:
            informe.estado_final = REQUIERE_INTERVENCION
        return False
