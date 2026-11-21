"""Consultas, supervision, cancelacion y cierre del motor de ejecucion."""
from __future__ import annotations

import time
from typing import Any, Optional

from ejecucion_modelo import ESTADO_CANCELADA, ESTADO_RECHAZADA, ResultadoEjecucion
from motor_ejecucion_estado import (
    CANCELANDO,
    EJECUTANDO,
    EN_COLA,
    ESPERANDO_AUTORIZACION,
    EXPIRADA,
    FALLIDA,
    PENDIENTE,
)


class MotorEjecucionControlMixin:
    def cancelar(self, id_solicitud: str, motivo: str = "cancelacion solicitada") -> bool:
        ficha = self.obtener_ficha(id_solicitud)
        if ficha is None:
            return False
        with self._bloqueo:
            estado = ficha.estado
            if estado in (PENDIENTE, ESPERANDO_AUTORIZACION, EN_COLA):
                ficha.token_cancelacion.cancelar(motivo)
                if ficha.transicionar(ESTADO_CANCELADA, motivo):
                    self._cola.quitar(id_solicitud)
                    self._emitir("cancelada", ficha)
                    self._despachar()
                    return True
            if estado == EJECUTANDO:
                ficha.token_cancelacion.cancelar(motivo)
                if ficha.transicionar(CANCELANDO, motivo):
                    self._emitir("cancelando", ficha)
                    return True
        return False

    def obtener_ficha(self, id_solicitud: str):
        with self._bloqueo:
            return self._fichas.get(id_solicitud)

    def obtener_estado_tarea(self, id_solicitud: str) -> Optional[dict[str, Any]]:
        ficha = self.obtener_ficha(id_solicitud)
        return ficha.a_dict() if ficha else None

    def obtener_resultado(self, id_solicitud: str) -> Optional[ResultadoEjecucion]:
        ficha = self.obtener_ficha(id_solicitud)
        return ficha.resultado if ficha else None

    def listar_tareas(self, estado: Optional[str] = None) -> list[dict[str, Any]]:
        with self._bloqueo:
            fichas = list(self._fichas.values())
        if estado:
            fichas = [f for f in fichas if f.estado == estado]
        return [f.a_dict() for f in fichas]

    def estadisticas(self) -> dict[str, Any]:
        with self._bloqueo:
            fichas = list(self._fichas.values())
        conteo: dict[str, int] = {}
        for ficha in fichas:
            conteo[ficha.estado] = conteo.get(ficha.estado, 0) + 1
        return {
            "total": len(fichas),
            "por_estado": conteo,
            "max_workers": self.max_workers,
            "detenido": self._detener.is_set(),
        }

    def _vigilar(self) -> None:
        while not self._detener.is_set():
            time.sleep(0.02)
            ahora = time.time()
            with self._bloqueo:
                fichas = list(self._fichas.values())
            for ficha in fichas:
                if ficha.estado != EJECUTANDO:
                    continue
                contrato = self.registro.obtener(ficha.solicitud.herramienta)
                timeout = float(getattr(contrato, "timeout_seg", 30.0))
                if ahora - ficha.timestamp_estado < timeout:
                    continue
                ficha.token_cancelacion.cancelar("timeout cooperativo")
                if ficha.transicionar(EXPIRADA, "TIMEOUT_EJECUCION"):
                    ficha.resultado = ResultadoEjecucion(
                        ficha.solicitud.id_solicitud,
                        ficha.solicitud.herramienta,
                        EXPIRADA,
                        False,
                        error={
                            "codigo": "TIMEOUT_EJECUCION",
                            "mensaje": "El timeout se activo; el worker puede seguir finalizando.",
                            "recuperable": False,
                        },
                        duracion_ms=(ahora - ficha.timestamp_estado) * 1000.0,
                        metadatos={"worker_en_segundo_plano": True},
                    )
                    self._emitir("expirada", ficha)

    def _completar_cancelacion(self, ficha) -> None:
        ficha.worker_activo = False
        ficha.transicionar(ESTADO_CANCELADA, ficha.token_cancelacion.motivo)
        self._cola.quitar(ficha.solicitud.id_solicitud)
        self._emitir("cancelada", ficha)
        ficha.resultado = ResultadoEjecucion(
            ficha.solicitud.id_solicitud,
            ficha.solicitud.herramienta,
            ESTADO_CANCELADA,
            False,
            error={"codigo": "CANCELADA",
                   "mensaje": ficha.token_cancelacion.motivo,
                   "recuperable": True},
        )

    def _finalizar_fallo(self, ficha, codigo: str, mensaje: str) -> None:
        ficha.resultado = self._resultado(
            ficha.solicitud, ESTADO_RECHAZADA, codigo, mensaje
        )
        ficha.transicionar(FALLIDA, codigo)
        ficha.worker_activo = False
        with self._bloqueo:
            self._fichas[ficha.solicitud.id_solicitud] = ficha
        self._emitir("fallida", ficha)

    def _resultado(self, solicitud, estado: str, codigo: str,
                   mensaje: str, duracion_ms: float = 0.0):
        return ResultadoEjecucion(
            solicitud.id_solicitud,
            solicitud.herramienta,
            estado,
            False,
            error={"codigo": codigo, "mensaje": mensaje,
                   "recuperable": True},
            duracion_ms=duracion_ms,
        )

    def detener(self, esperar: bool = True, timeout: float = 5.0) -> None:
        self._detener.set()
        with self._bloqueo:
            fichas = list(self._fichas.values())
        for ficha in fichas:
            if ficha.estado in (PENDIENTE, ESPERANDO_AUTORIZACION, EN_COLA):
                ficha.token_cancelacion.cancelar("motor detenido")
                ficha.transicionar(ESTADO_CANCELADA, "motor detenido")
                ficha.resultado = self._resultado(
                    ficha.solicitud, ESTADO_CANCELADA, "CANCELADA",
                    "Motor detenido antes de ejecutar.",
                )
                self._emitir("cancelada", ficha)
        self._cola.limpiar()
        if esperar:
            try:
                self._executor.shutdown(wait=True, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=True)
        else:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=False)
