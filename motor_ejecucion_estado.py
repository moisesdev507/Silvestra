"""Estados, cancelacion, fichas y cola prioritaria del motor de tareas."""
from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ejecucion_modelo import ResultadoEjecucion, SolicitudEjecucion
from permisos_modelo import sanitizar_parametros


PENDIENTE = "pendiente"
VALIDANDO = "validando"
ESPERANDO_AUTORIZACION = "esperando_autorizacion"
EN_COLA = "en_cola"
EJECUTANDO = "ejecutando"
COMPLETADA = "completada"
FALLIDA = "fallida"
CANCELANDO = "cancelando"
CANCELADA = "cancelada"
EXPIRADA = "expirada"

TRANSICIONES_VALIDAS = {
    PENDIENTE: {VALIDANDO, CANCELADA},
    VALIDANDO: {ESPERANDO_AUTORIZACION, EN_COLA, FALLIDA, CANCELADA},
    ESPERANDO_AUTORIZACION: {EN_COLA, CANCELADA, EXPIRADA, FALLIDA},
    EN_COLA: {EJECUTANDO, CANCELADA, EXPIRADA},
    EJECUTANDO: {COMPLETADA, FALLIDA, CANCELANDO, EXPIRADA},
    CANCELANDO: {CANCELADA, FALLIDA},
    COMPLETADA: set(),
    FALLIDA: set(),
    CANCELADA: set(),
    EXPIRADA: set(),
}


@dataclass
class TokenCancelacion:
    motivo: str = ""
    timestamp_solicitud: float = field(default_factory=time.time)
    event: threading.Event = field(default_factory=threading.Event)

    def cancelar(self, motivo: str = "cancelacion solicitada") -> None:
        self.motivo = str(motivo or "cancelacion solicitada")
        self.event.set()

    def esta_cancelado(self) -> bool:
        return self.event.is_set()


@dataclass
class FichaTareaEjecucion:
    solicitud: SolicitudEjecucion
    prioridad: int = 0
    estado: str = PENDIENTE
    historial_estados: list[str] = field(default_factory=list)
    token_cancelacion: TokenCancelacion = field(default_factory=TokenCancelacion)
    resultado: Optional[ResultadoEjecucion] = None
    worker_activo: bool = False
    diagnostico: dict[str, Any] = field(default_factory=dict)
    timestamp_creacion: float = field(default_factory=time.time)
    timestamp_estado: float = field(default_factory=time.time)
    id_autorizacion: Optional[str] = None
    worker_en_segundo_plano: bool = False
    secuencia: int = 0

    def __post_init__(self) -> None:
        self.historial_estados = [PENDIENTE]
        self.diagnostico = {
            "parametros_sanitizados": sanitizar_parametros(self.solicitud.parametros),
            "worker_en_segundo_plano": False,
        }

    def transicionar(self, nuevo: str, detalle: str = "") -> bool:
        if nuevo not in TRANSICIONES_VALIDAS.get(self.estado, set()):
            return False
        self.estado = nuevo
        self.timestamp_estado = time.time()
        self.historial_estados.append(nuevo)
        if detalle:
            self.diagnostico["ultimo_detalle"] = detalle
        if nuevo == EXPIRADA:
            self.diagnostico["worker_en_segundo_plano"] = self.worker_activo
            self.worker_en_segundo_plano = self.worker_activo
        return True

    def a_dict(self) -> dict[str, Any]:
        diag = dict(self.diagnostico)
        diag["parametros_sanitizados"] = sanitizar_parametros(
            self.solicitud.parametros
        )
        return {
            "id_solicitud": self.solicitud.id_solicitud,
            "herramienta": self.solicitud.herramienta,
            "origen": self.solicitud.origen,
            "prioridad": self.prioridad,
            "estado": self.estado,
            "historial_estados": list(self.historial_estados),
            "worker_activo": self.worker_activo,
            "worker_en_segundo_plano": self.worker_en_segundo_plano,
            "id_autorizacion": self.id_autorizacion,
            "timestamp_creacion": self.timestamp_creacion,
            "timestamp_estado": self.timestamp_estado,
            "diagnostico": diag,
        }


class ColaPrioridadEjecucion:
    def __init__(self) -> None:
        self._bloqueo = threading.RLock()
        self._heap: list[tuple[int, int, str, FichaTareaEjecucion]] = []
        self._activas: dict[str, FichaTareaEjecucion] = {}
        self._secuencia = 0

    def existe_activa(self, id_solicitud: str) -> bool:
        with self._bloqueo:
            return id_solicitud in self._activas

    def encolar(self, ficha: FichaTareaEjecucion) -> bool:
        with self._bloqueo:
            id_s = ficha.solicitud.id_solicitud
            if id_s in self._activas:
                return False
            self._secuencia += 1
            ficha.secuencia = self._secuencia
            ficha.transicionar(EN_COLA)
            self._activas[id_s] = ficha
            heapq.heappush(
                self._heap,
                (-int(ficha.prioridad), ficha.secuencia, id_s, ficha),
            )
            return True

    def retirar(self) -> Optional[FichaTareaEjecucion]:
        with self._bloqueo:
            while self._heap:
                _, _, id_s, ficha = heapq.heappop(self._heap)
                if self._activas.get(id_s) is ficha:
                    return ficha
            return None

    def obtener(self, id_solicitud: str) -> Optional[FichaTareaEjecucion]:
        with self._bloqueo:
            return self._activas.get(id_solicitud)

    def quitar(self, id_solicitud: str) -> Optional[FichaTareaEjecucion]:
        with self._bloqueo:
            ficha = self._activas.pop(id_solicitud, None)
            return ficha

    def pendientes(self) -> list[FichaTareaEjecucion]:
        with self._bloqueo:
            return [
                ficha for ficha in self._activas.values()
                if ficha.estado in (PENDIENTE, VALIDANDO, ESPERANDO_AUTORIZACION, EN_COLA)
            ]

    def activas(self) -> list[FichaTareaEjecucion]:
        with self._bloqueo:
            return list(self._activas.values())

    def limpiar(self) -> list[FichaTareaEjecucion]:
        with self._bloqueo:
            fichas = list(self._activas.values())
            self._heap.clear()
            self._activas.clear()
            return fichas
