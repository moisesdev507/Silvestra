"""Motor continuo de percepcion visual desde la fuente de camara existente."""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from typing import Any, Callable, Optional

from percepcion_adaptadores import ProcesadorModalidad
from percepcion_modelo import EventoPerceptivo, ReferenciaContenido
from camara_percepcion_modelo import (
    PoliticaCapturaCamara,
    ObservacionCamara,
    EventoVisualCamara,
)
from camara_comparador import ComparadorFotogramas
from camara_contexto_temporal import ContextoVisualTemporal


class MotorPercepcionCamara:
    def __init__(
        self,
        fuente_frames: Optional[Callable[[], Any]] = None,
        camara=None,
        motor_percepcion=None,
        motor_visual=None,
        contexto_motor=None,
        cerebro=None,
        app_cola=None,
        politica: Optional[PoliticaCapturaCamara] = None,
    ) -> None:
        self._bloqueo = threading.RLock()
        self._fuente = fuente_frames
        self._camara = camara
        self.motor_percepcion = motor_percepcion
        self.motor_visual = motor_visual
        self.contexto_motor = contexto_motor
        self.cerebro = cerebro
        self.app_cola = app_cola
        self.politica = politica or PoliticaCapturaCamara()
        self.comparador = ComparadorFotogramas()
        self.contexto = ContextoVisualTemporal(
            maxlen=self.politica.max_observaciones_temporales,
            ttl_observacion_seg=self.politica.ttl_observacion_seg,
        )
        self._detener = threading.Event()
        self._activo = False
        self._hilo: Optional[threading.Thread] = None
        self._ultima_actualizacion_vlm = 0.0
        self._ultima_huella = ""
        self._conectada = True
        self._contador_fallos = 0

    def iniciar(self) -> None:
        with self._bloqueo:
            if self._hilo and self._hilo.is_alive():
                return
            self._detener.clear()
            self._activo = bool(self.politica.habilitada)
            self._hilo = threading.Thread(
                target=self._bucle,
                daemon=True,
                name="CamaraPercepcionContinuo",
            )
            self._hilo.start()

    def detener(self) -> None:
        self._detener.set()
        with self._bloqueo:
            self._activo = False
            hilo = self._hilo
        if hilo and hilo.is_alive():
            hilo.join(timeout=2.0)
        self.contexto.limpiar()
        self.comparador.reiniciar()

    def activar(self) -> None:
        with self._bloqueo:
            self._activo = True

    def desactivar(self) -> None:
        with self._bloqueo:
            self._activo = False

    def _leer_frame(self):
        if self._fuente is not None:
            return self._fuente()
        if self._camara is not None:
            frame = getattr(self._camara, "ultimo_frame", None)
            return frame
        return None

    def _bucle(self) -> None:
        while not self._detener.is_set():
            if not self._activo:
                self._detener.wait(self.politica.intervalo_reposo_seg)
                continue
            try:
                frame = self._leer_frame()
                if frame is None:
                    self._manejar_desconexion()
                    self._detener.wait(self.politica.intervalo_reposo_seg)
                    continue
                if not self._conectada:
                    self._conectada = True
                    self._emitir(EventoVisualCamara(
                        "camara_recuperada",
                        "deteccion",
                        4,
                        datos_sanitizados={"estado": "recuperada"},
                    ))
                resultado = self.comparador.comparar(
                    frame,
                    self.politica.umbral_cambio_significativo,
                )
                if resultado.huella_frame == self._ultima_huella:
                    self._detener.wait(self.politica.intervalo_reposo_seg)
                    continue
                self._ultima_huella = resultado.huella_frame
                if resultado.anomalia_sensor:
                    self._emitir(EventoVisualCamara(
                        "anomalia_sensor",
                        "deteccion",
                        5,
                        datos_sanitizados={"anomalia": resultado.anomalia_sensor},
                    ))
                if resultado.hay_cambio_significativo:
                    self._procesar_cambio(frame, resultado)
                self._detener.wait(self.politica.intervalo_activo_seg)
            except Exception:
                self._manejar_desconexion()
                self._detener.wait(self.politica.intervalo_reposo_seg)

    def _manejar_desconexion(self) -> None:
        if self._conectada:
            self._conectada = False
            self._emitir(EventoVisualCamara(
                "camara_desconectada",
                "deteccion",
                5,
                datos_sanitizados={"estado": "desconectada"},
            ))

    def _procesar_cambio(self, frame, resultado) -> None:
        ahora = time.time()
        observacion = ObservacionCamara(
            timestamp=ahora,
            fuente="camara",
            puntuacion_cambio=resultado.puntuacion_cambio,
            observaciones_verificables=[
                "Cambio visual local significativo detectado"
                if resultado.hay_cambio_significativo else ""
            ],
            interpretaciones_inciertas=[],
            resumen_breve="Cambio visual significativo detectado",
            significativa=True,
        )
        observacion.detecciones_locales = [
            {"region": list(r), "tipo": "movimiento"}
            for r in resultado.regiones_movimiento
        ]
        self.contexto.agregar(observacion)
        self._emitir(EventoVisualCamara(
            "movimiento" if resultado.hay_movimiento else "cambio_escena",
            "deteccion",
            4,
            datos_sanitizados={
                "puntuacion_cambio": round(resultado.puntuacion_cambio, 4),
                "regiones": resultado.regiones_movimiento,
            },
        ))
        if self.motor_visual is not None:
            if ahora - self._ultima_actualizacion_vlm >= (
                self.politica.intervalo_resumen_vlm_seg
            ):
                self._invocar_visual_temp(frame)

    def _invocar_visual_temp(self, frame) -> None:
        ruta = None
        img = None
        try:
            try:
                import cv2
                import numpy as np
                if hasattr(frame, "save"):
                    ruta = tempfile.mktemp(prefix="silvestra_cam_", suffix=".jpg")
                    frame.save(ruta, "JPEG")
                elif isinstance(frame, np.ndarray):
                    ruta = tempfile.mktemp(prefix="silvestra_cam_", suffix=".jpg")
                    ok = cv2.imwrite(ruta, frame)
                    if not ok:
                        ruta = None
            except Exception:
                ruta = None
            if ruta is None:
                return
            from vision_modelo import SolicitudVisual
            solicitud = SolicitudVisual(
                ruta_imagen=ruta,
                modalidad="captura_pantalla",
                pregunta="Describe el cambio visual",
                autorizacion_externa=self.politica.autorizacion_externa,
            )
            self.motor_visual.procesar(solicitud)
            self._ultima_actualizacion_vlm = time.time()
        finally:
            if ruta and os.path.exists(ruta):
                try:
                    os.remove(ruta)
                except Exception:
                    pass

    def _emitir(self, evento: EventoVisualCamara) -> None:
        if self.app_cola is None:
            return
        payload = {
            "tipo": "camara_visual",
            "evento": evento.a_dict(),
        }
        try:
            if hasattr(self.app_cola, "put_nowait"):
                self.app_cola.put_nowait(("percepcion_evento", payload))
            else:
                self.app_cola.put(("percepcion_evento", payload), block=False)
        except Exception:
            pass

    def capturar_una_vez(self) -> dict:
        frame = self._leer_frame()
        if frame is None:
            return {"estado": "camara_desconectada"}
        resultado = self.comparador.comparar(
            frame,
            self.politica.umbral_cambio_significativo,
        )
        return {
            "estado": "capturada",
            "comparacion": {
                "puntuacion_cambio": resultado.puntuacion_cambio,
                "hay_movimiento": resultado.hay_movimiento,
                "huella_frame": resultado.huella_frame,
                "anomalia_sensor": resultado.anomalia_sensor,
            },
        }

    def consultar_estado_actual(self, pregunta: str = "") -> dict:
        return self.contexto.consultar_entorno_reciente(pregunta)

    def consultar_entorno_reciente(self, pregunta: str = "") -> dict:
        return self.contexto.consultar_entorno_reciente(pregunta)


class ProcesadorCamaraContinuo(ProcesadorModalidad):
    def __init__(self, motor: MotorPercepcionCamara) -> None:
        self.motor = motor

    def procesar(self, evento, token_cancelacion=None) -> dict:
        if token_cancelacion and getattr(token_cancelacion, "is_set", lambda: False)():
            return {"cancelado": True}
        return self.motor.capturar_una_vez()
