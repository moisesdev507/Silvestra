"""Motor concurrente acotado de tareas simuladas con permisos y supervision."""
from __future__ import annotations

import inspect
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from ejecucion_modelo import (
    ESTADO_CANCELADA,
    ESTADO_COMPLETADA,
    ESTADO_FALLIDA,
    ESTADO_RECHAZADA,
    ResultadoEjecucion,
    SolicitudEjecucion,
)
from ejecucion_registro import RegistroHerramientas
from motor_ejecucion_estado import (
    CANCELANDO,
    CANCELADA,
    COMPLETADA,
    EJECUTANDO,
    EN_COLA,
    ESPERANDO_AUTORIZACION,
    EXPIRADA,
    FALLIDA,
    VALIDANDO,
    FichaTareaEjecucion,
    ColaPrioridadEjecucion,
    PENDIENTE,
)
from motor_ejecucion_control import MotorEjecucionControlMixin


class MotorEjecucionTareas(MotorEjecucionControlMixin):
    def __init__(
        self,
        registro: Optional[RegistroHerramientas] = None,
        motor_permisos: Optional[Any] = None,
        max_workers: int = 2,
        app_cola: Optional[Any] = None,
    ) -> None:
        if motor_permisos is None:
            raise ValueError("PERMISOS_NO_DISPONIBLES")
        self.registro = registro or RegistroHerramientas()
        try:
            import correo_unificado
            correo_unificado.registrar_en_motor(self.registro)
        except Exception:
            pass
        self.motor_permisos = motor_permisos
        self.app_cola = app_cola
        self.max_workers = max(1, min(4, int(max_workers)))
        self._bloqueo = threading.RLock()
        self._cola = ColaPrioridadEjecucion()
        self._fichas: dict[str, FichaTareaEjecucion] = {}
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._detener = threading.Event()
        self._iniciado = False
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="SilvestraEjecucion",
        )
        self._supervisor = threading.Thread(
            target=self._vigilar,
            daemon=True,
            name="SupervisorEjecucion",
        )

    def iniciar(self) -> None:
        with self._bloqueo:
            if self._iniciado:
                return
            self._iniciado = True
        self._supervisor.start()

    def suscribir_eventos(self, callback: Callable[[dict[str, Any]], None]) -> bool:
        if not callable(callback):
            return False
        with self._bloqueo:
            self._callbacks.append(callback)
        return True

    def _emitir(self, tipo: str, ficha: FichaTareaEjecucion) -> None:
        payload = {
            "tipo": tipo,
            "tarea": ficha.a_dict(),
            "timestamp": time.time(),
        }
        with self._bloqueo:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(dict(payload))
            except Exception:
                pass
        if self.app_cola is not None:
            try:
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("ejecucion_evento", payload))
                else:
                    self.app_cola.put(("ejecucion_evento", payload), block=False)
            except Exception:
                pass

    def encolar(
        self,
        solicitud: SolicitudEjecucion,
        prioridad: int = 0,
    ) -> ResultadoEjecucion:
        if self._detener.is_set():
            return self._resultado(solicitud, ESTADO_RECHAZADA,
                                   "MOTOR_DETENIDO", "El motor no admite nuevas solicitudes.")
        if not isinstance(solicitud, SolicitudEjecucion):
            return self._resultado(
                SolicitudEjecucion("sistema", ""),
                ESTADO_RECHAZADA,
                "SOLICITUD_MALFORMADA",
                "La solicitud no es SolicitudEjecucion.",
            )

        with self._bloqueo:
            if solicitud.id_solicitud in self._fichas:
                return self._resultado(
                    solicitud, ESTADO_RECHAZADA,
                    "SOLICITUD_DUPLICADA",
                    "Ya existe una ficha con este id_solicitud.",
                )

        ficha = FichaTareaEjecucion(solicitud, prioridad=int(prioridad))
        try:
            if not ficha.transicionar(VALIDANDO):
                return self._resultado(solicitud, ESTADO_RECHAZADA,
                                       "TRANSICION_INVALIDA", "No pudo iniciar validacion.")

            valido, motivo, contrato = self.registro.validar_solicitud(solicitud)
            if not valido:
                self._finalizar_fallo(ficha, "VALIDACION_CONTRATO", motivo)
                return ficha.resultado

            decision = self.motor_permisos.evaluar_solicitud(solicitud, contrato)
            if decision.get("decision") == "pendiente_autorizacion":
                ficha.id_autorizacion = decision.get("id_autorizacion")
                ficha.diagnostico["id_autorizacion"] = ficha.id_autorizacion
                if ficha.transicionar(ESPERANDO_AUTORIZACION,
                                      "Confirmacion humana pendiente"):
                    with self._bloqueo:
                        self._fichas[solicitud.id_solicitud] = ficha
                    self._emitir("esperando_autorizacion", ficha)
                    return ResultadoEjecucion(
                        solicitud.id_solicitud, solicitud.herramienta,
                        "esperando_autorizacion", False,
                        datos=None,
                        error={"codigo": "PENDIENTE_AUTORIZACION",
                               "mensaje": "Requiere confirmacion explicita del usuario.",
                               "recuperable": True},
                        metadatos={"id_autorizacion": ficha.id_autorizacion},
                    )

            if decision.get("decision") != "permitida":
                codigo = decision.get("motivo", "PERMISOS_DENEGADOS")
                self._finalizar_fallo(ficha, codigo,
                                      "Solicitud denegada por la compuerta de permisos.")
                return ficha.resultado

            with self._bloqueo:
                self._fichas[solicitud.id_solicitud] = ficha
            if not self._cola.encolar(ficha):
                return self._resultado(solicitud, ESTADO_RECHAZADA,
                                       "SOLICITUD_DUPLICADA",
                                       "Solicitud ya activa o pendiente.")
            if not self._iniciado:
                self.iniciar()
            self._emitir("en_colada", ficha)
            self._despachar()
            return ResultadoEjecucion(
                solicitud.id_solicitud, solicitud.herramienta,
                "en_cola", True,
                datos={"prioridad": ficha.prioridad},
                metadatos={"estado": "en_cola"},
            )
        except Exception:
            ficha.resultado = self._resultado(
                solicitud, ESTADO_RECHAZADA,
                "PERMISOS_NO_DISPONIBLES",
                "La compuerta de permisos fallo; ninguna ejecucion fue admitida.",
            )
            if ficha.transicionar(FALLIDA if ficha.estado == VALIDANDO else ficha.estado):
                pass
            with self._bloqueo:
                self._fichas[solicitud.id_solicitud] = ficha
            self._emitir("fallida", ficha)
            return ficha.resultado

    def _despachar(self) -> None:
        while not self._detener.is_set():
            with self._bloqueo:
                activos = sum(
                    1 for f in self._fichas.values()
                    if f.worker_activo
                )
            if activos >= self.max_workers:
                return
            ficha = self._cola.retirar()
            if ficha is None:
                return
            if ficha.token_cancelacion.esta_cancelado():
                ficha.transicionar(ESTADO_CANCELADA, "Cancelacion antes del despacho")
                self._cola.quitar(ficha.solicitud.id_solicitud)
                self._emitir("cancelada", ficha)
                continue
            if not ficha.transicionar(EJECUTANDO):
                continue
            ficha.worker_activo = True
            ficha.diagnostico["worker_en_segundo_plano"] = False
            self._emitir("ejecutando", ficha)
            self._executor.submit(self._ejecutar, ficha)

    def _ejecutar(self, ficha: FichaTareaEjecucion) -> None:
        inicio = time.perf_counter()
        solicitud = ficha.solicitud
        try:
            contrato = self.registro.obtener(solicitud.herramienta)
            if contrato is None:
                raise RuntimeError("HERRAMIENTA_INEXISTENTE")

            if ficha.token_cancelacion.esta_cancelado():
                self._completar_cancelacion(ficha)
                return

            validacion = self.motor_permisos.validar_antes_de_ejecutar(
                solicitud, contrato
            )
            if not validacion.get("permitida"):
                codigo = validacion.get("codigo", "PERMISOS_DENEGADOS")
                duracion = (time.perf_counter() - inicio) * 1000.0
                resultado = self._resultado(
                    solicitud, ESTADO_RECHAZADA, codigo,
                    "Validacion previa al worker rechazada.",
                    duracion,
                )
                ficha.resultado = resultado
                ficha.transicionar(FALLIDA, codigo)
                ficha.worker_activo = False
                self._cola.quitar(solicitud.id_solicitud)
                self._emitir("fallida", ficha)
                self._despachar()
                return

            if contrato.handler is None:
                datos = {"modo": "informativo", "descripcion": contrato.descripcion,
                         "simulado": True}
            else:
                datos = self._llamar_handler(
                    contrato.handler,
                    dict(solicitud.parametros),
                    ficha.token_cancelacion,
                )

            if ficha.estado == EXPIRADA or ficha.estado == CANCELADA:
                ficha.worker_activo = False
                return
            if ficha.token_cancelacion.esta_cancelado():
                self._completar_cancelacion(ficha)
                return

            duracion = (time.perf_counter() - inicio) * 1000.0
            resultado = ResultadoEjecucion(
                solicitud.id_solicitud, solicitud.herramienta,
                ESTADO_COMPLETADA, True, datos=datos,
                duracion_ms=duracion,
                metadatos=contrato.metadatos(),
            )
            ficha.resultado = resultado
            ficha.transicionar(COMPLETADA, "Handler finalizado")
            ficha.worker_activo = False
            self._cola.quitar(solicitud.id_solicitud)
            self._emitir("completada", ficha)
        except Exception:
            if ficha.estado == EXPIRADA:
                ficha.worker_activo = False
                return
            duracion = (time.perf_counter() - inicio) * 1000.0
            ficha.resultado = self._resultado(
                solicitud, ESTADO_FALLIDA, "ERROR_INTERNO_HANDLER",
                "El handler seguro lanzo una excepcion controlada.",
                duracion,
            )
            ficha.transicionar(FALLIDA, "Error interno del handler")
            ficha.worker_activo = False
            self._cola.quitar(solicitud.id_solicitud)
            self._emitir("fallida", ficha)
        finally:
            ficha.worker_activo = False
            self._despachar()

    def _llamar_handler(
        self,
        handler: Callable[..., Any],
        parametros: dict[str, Any],
        token: Any,
    ) -> Any:
        firma = inspect.signature(handler)
        nombres = set(firma.parameters)
        acepta_cancelacion = (
            "token_cancelacion" in nombres
            or "token" in nombres
        )
        if acepta_cancelacion:
            nombre = "token_cancelacion" if "token_cancelacion" in nombres else "token"
            kwargs = {nombre: token}
            return handler(parametros, **kwargs)
        try:
            firma.bind(parametros)
            return handler(parametros)
        except TypeError:
            firma.bind(parametros, token)
            return handler(parametros, token)

    def reanudar_autorizada(self, id_solicitud: str) -> bool:
        ficha = self.obtener_ficha(id_solicitud)
        if ficha is None or ficha.estado != ESPERANDO_AUTORIZACION:
            return False
        try:
            contrato = self.registro.obtener(ficha.solicitud.herramienta)
            if contrato is None:
                return False
            decision = self.motor_permisos.evaluar_solicitud(
                ficha.solicitud, contrato
            )
            if decision.get("decision") != "permitida":
                return False
            with self._bloqueo:
                self._fichas[id_solicitud] = ficha
            if not self._cola.encolar(ficha):
                return False
            self._emitir("en_colada", ficha)
            self._despachar()
            return True
        except Exception:
            return False

