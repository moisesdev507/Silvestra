"""Motor concurrente seguro de percepcion multimodal."""
from __future__ import annotations

import heapq
import inspect
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from percepcion_modelo import (
    RECIBIDO, NORMALIZADO, EN_COLA, PROCESANDO,
    PROCESADO, DESCARTADO, CANCELADO, EXPIRADO, FALLIDO,
    EventoPerceptivo,
)
from percepcion_adaptadores import RegistroAdaptadoresPercepcion


class MotorPercepcion:
    def __init__(
        self,
        registro: Optional[RegistroAdaptadoresPercepcion] = None,
        max_workers: int = 2,
        ventana_dedupe_seg: float = 2.0,
        max_caracteres_resumen: int = 300,
        app_cola: Optional[Any] = None,
        contexto_motor: Optional[Any] = None,
        cerebro: Optional[Any] = None,
        orquestador: Optional[Any] = None,
    ) -> None:
        self.registro = registro or RegistroAdaptadoresPercepcion()
        self.max_workers = max(1, min(4, int(max_workers)))
        self.ventana_dedupe_seg = max(0.0, float(ventana_dedupe_seg))
        self.max_caracteres_resumen = max(20, int(max_caracteres_resumen))
        self.app_cola = app_cola
        self.contexto_motor = contexto_motor
        self.cerebro = cerebro
        self.orquestador = orquestador
        self._bloqueo = threading.RLock()
        self._heap: list[tuple[int, int, str, EventoPerceptivo]] = []
        self._eventos: dict[str, EventoPerceptivo] = {}
        self._dedupe: dict[str, float] = {}
        self._tokens: dict[str, Any] = {}
        self._activos: dict[str, bool] = {}
        self._futuros: dict[str, Any] = {}
        self._secuencia = 0
        self._detener = threading.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="SilvestraPercepcion",
        )

    def _cancelar_token(self, id_evento: str):
        import threading as th
        token = self._tokens.get(id_evento)
        if token is None:
            token = th.Event()
            token.esta_cancelado = token.is_set
            token.cancelar = token.set
            self._tokens[id_evento] = token
        return token

    def recibir(self, evento: EventoPerceptivo,
                duracion_seg: float = 0.0) -> dict:
        if not isinstance(evento, EventoPerceptivo):
            return self._respuesta_error("EVENTO_INVALIDO")
        if evento.modalidad not in (
            "camara", "imagen", "captura_screenshot",
            "captura_pantalla", "audio",
            "contexto_sistema", "evento_interno",
        ):
            evento.transicionar(DESCARTADO)
            evento.liberar_recurso()
            return self._respuesta(evento, "modalidad invalida")

        politica = self.registro.obtener_politica(evento.modalidad)
        if evento.referencia_contenido:
            tamano = evento.referencia_contenido.tamano
            ruta = evento.referencia_contenido.ruta
            if ruta and (not os.path.isfile(ruta)):
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "archivo inexistente")
            if tamano > politica.max_bytes:
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "max_bytes excedido")
            evento.referencia_contenido.duracion_seg = float(
                duracion_seg or evento.referencia_contenido.duracion_seg
            )
            if evento.referencia_contenido.duracion_seg > politica.max_duracion_seg:
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "max_duracion_seg excedida")

        if not self.registro.esta_habilitada(
            evento.fuente, evento.modalidad
        ):
            evento.transicionar(DESCARTADO)
            evento.liberar_recurso()
            return self._respuesta(evento, "fuente o modalidad deshabilitada")

        if not evento.transicionar(NORMALIZADO):
            evento.liberar_recurso()
            return self._respuesta_error("TRANSICION_INVALIDA")

        huella = evento.huella()
        ahora = time.time()
        with self._bloqueo:
            ultimo = self._dedupe.get(huella)
            if ultimo is not None and ahora - ultimo < self.ventana_dedupe_seg:
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "duplicado")
            pendientes = sum(
                1 for e in self._eventos.values()
                if e.modalidad == evento.modalidad
                and e.estado in (NORMALIZADO, EN_COLA, PROCESANDO)
            )
            if pendientes >= politica.max_pendientes:
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "max_pendientes excedido")
            if evento.id_evento in self._eventos:
                evento.transicionar(DESCARTADO)
                evento.liberar_recurso()
                return self._respuesta(evento, "id_evento duplicado")
            if not evento.transicionar(EN_COLA):
                evento.liberar_recurso()
                return self._respuesta_error("TRANSICION_INVALIDA")
            self._secuencia += 1
            secuencia = self._secuencia
            self._eventos[evento.id_evento] = evento
            self._dedupe[huella] = ahora
            import threading as th
            token = th.Event()
            token.esta_cancelado = token.is_set
            token.cancelar = token.set
            self._tokens[evento.id_evento] = token
            heapq.heappush(
                self._heap,
                (-int(evento.prioridad), secuencia,
                 evento.id_evento, evento),
            )
        self._despachar()
        return self._respuesta(evento, "encolado")

    def _respuesta(self, evento: EventoPerceptivo,
                   motivo: str) -> dict:
        return {
            "id_evento": evento.id_evento,
            "estado": evento.estado,
            "motivo": motivo,
            "huella_sha256": evento.huella(),
        }

    def _respuesta_error(self, codigo: str) -> dict:
        return {"estado": "fallido", "motivo": codigo}

    def cancelar_evento(self, id_evento: str, motivo: str = "cancelado") -> bool:
        with self._bloqueo:
            evento = self._eventos.get(id_evento)
            if evento is None:
                return False
            if evento.estado in (EN_COLA, RECIBIDO, NORMALIZADO):
                evento.transicionar(CANCELADO)
                try:
                    self._tokens[id_evento].cancelar(motivo)
                except Exception:
                    pass
                evento.liberar_recurso()
                self._emitir(evento)
                return True
            if evento.estado == PROCESANDO:
                try:
                    self._tokens[id_evento].cancelar(motivo)
                except Exception:
                    pass
                return True
        return False

    def cancelar_modalidad(self, modalidad: str) -> int:
        cantidad = 0
        with self._bloqueo:
            eventos = [
                e for e in self._eventos.values()
                if e.modalidad == modalidad
            ]
        for evento in eventos:
            if self.cancelar_evento(evento.id_evento, "cancelado modalidad"):
                cantidad += 1
        return cantidad

    def _despachar(self) -> None:
        while not self._detener.is_set():
            with self._bloqueo:
                activos = sum(1 for v in self._activos.values() if v)
                if activos >= self.max_workers:
                    return
                ficha = None
                while self._heap:
                    _, _, id_evento, evento = heapq.heappop(self._heap)
                    if self._eventos.get(id_evento) is evento:
                        ficha = evento
                        break
                if ficha is None:
                    return
                if ficha.estado != EN_COLA:
                    continue
                politica = self.registro.obtener_politica(ficha.modalidad)
                if self._caducado(ficha, politica.ttl_seg):
                    ficha.transicionar(EXPIRADO)
                    ficha.liberar_recurso()
                    self._emitir(ficha)
                    continue
                if not ficha.transicionar(PROCESANDO):
                    continue
                self._activos[ficha.id_evento] = True
            futuro = self._executor.submit(self._procesar, ficha)
            self._futuros[ficha.id_evento] = futuro
            timeout_seg = float(ficha.metadatos.get("timeout_seg", 5.0))
            if timeout_seg > 0:
                threading.Thread(
                    target=self._vigilar_timeout,
                    args=(ficha, timeout_seg),
                    daemon=True,
                ).start()

    def _vigilar_timeout(self, evento: EventoPerceptivo,
                         timeout_seg: float) -> None:
        time.sleep(timeout_seg)
        futuro = self._futuros.get(evento.id_evento)
        if futuro is not None and not futuro.done():
            with self._bloqueo:
                if evento.estado == PROCESANDO:
                    evento.transicionar(EXPIRADO)
                    try:
                        evento.liberar_recurso()
                    except Exception:
                        pass
                    self._emitir(evento)

    def _caducado(self, evento: EventoPerceptivo, ttl_seg: float) -> bool:
        return bool(ttl_seg > 0 and time.time() - evento.timestamp > ttl_seg)

    def _procesar(self, evento: EventoPerceptivo) -> None:
        try:
            procesador = self.registro.obtener(evento.modalidad)
            if procesador is None:
                evento.transicionar(FALLIDO)
                return
            token = self._tokens.get(evento.id_evento)
            if token is not None and token.is_set():
                evento.transicionar(CANCELADO)
                return
            if evento.estado == EXPIRADO:
                return
            resultado = procesador.procesar(evento, token)
            if token is not None and token.is_set():
                evento.transicionar(CANCELADO)
                return
            evento.resultado_estructurado = (
                resultado if isinstance(resultado, dict)
                else {"resultado": str(resultado)}
            )
            evento.transicionar(PROCESADO)
            self._publicar_integraciones(evento)
        except Exception:
            try:
                evento.transicionar(FALLIDO)
            except Exception:
                pass
        finally:
            try:
                evento.liberar_recurso()
                with self._bloqueo:
                    self._activos[evento.id_evento] = False
                self._emitir(evento)
            finally:
                self._despachar()

    def _publicar_integraciones(self, evento: EventoPerceptivo) -> None:
        datos = evento.resultado_estructurado or {}
        resumen = str(datos).replace("\n", " ")[:self.max_caracteres_resumen]
        payload = {
            "tipo": "percepcion",
            "modalidad": evento.modalidad,
            "id_evento": evento.id_evento,
            "resumen": resumen,
            "huella_sha256": evento.huella(),
        }
        if self.app_cola is not None:
            try:
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("percepcion_evento", payload))
                else:
                    self.app_cola.put(("percepcion_evento", payload), block=False)
            except Exception:
                pass
        if self.contexto_motor is not None:
            try:
                confirmar = getattr(self.contexto_motor, "confirmar_contexto", None)
                if callable(confirmar):
                    confirmar(
                        f"percepcion_{evento.modalidad}",
                        evento.resultado_estructurado,
                        origen="percepcion",
                        ttl_seg=30.0,
                    )
            except Exception:
                pass
        if self.cerebro is not None:
            try:
                self.cerebro.historial.append({
                    "role": "system",
                    "content": "[PERCEPCION] " + resumen,
                })
            except Exception:
                pass
        sugerencia = datos.get("sugerencia_accion")
        if sugerencia and self.orquestador is not None:
            try:
                recibir = getattr(self.orquestador, "recibir", None)
                if callable(recibir):
                    recibir(
                        str(sugerencia),
                        origen="percepcion",
                        requiere_ejecucion=True,
                        modo="restringido",
                    )
            except Exception:
                pass

    def _emitir(self, evento: EventoPerceptivo) -> None:
        if self.app_cola is not None:
            payload = {
                "tipo": "percepcion",
                "id_evento": evento.id_evento,
                "estado": evento.estado,
                "modalidad": evento.modalidad,
            }
            try:
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("percepcion_evento", payload))
                else:
                    self.app_cola.put(("percepcion_evento", payload), block=False)
            except Exception:
                pass

    def obtener_estado(self, id_evento: str) -> Optional[dict]:
        with self._bloqueo:
            evento = self._eventos.get(id_evento)
            return evento.a_dict() if evento else None

    def detener(self, esperar: bool = True, timeout: float = 5.0) -> None:
        self._detener.set()
        with self._bloqueo:
            eventos = list(self._eventos.values())
        for evento in eventos:
            if evento.estado in (NORMALIZADO, EN_COLA, PROCESANDO):
                try:
                    evento.transicionar(CANCELADO)
                except Exception:
                    pass
                evento.liberar_recurso()
                self._emitir(evento)
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
