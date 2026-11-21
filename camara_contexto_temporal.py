"""Contexto temporal acotado de observaciones visuales."""
from __future__ import annotations

import threading
import time
from collections import deque

from camara_percepcion_modelo import ObservacionCamara


class ContextoVisualTemporal:
    def __init__(self, maxlen=40, ttl_observacion_seg=60.0) -> None:
        self._bloqueo = threading.RLock()
        self.maxlen = max(1, int(maxlen))
        self.ttl_observacion_seg = max(1.0, float(ttl_observacion_seg))
        self._observaciones = deque(maxlen=self.maxlen)
        self._ultimas_firmas: deque[str] = deque(maxlen=8)

    def agregar(self, observacion: ObservacionCamara) -> bool:
        if not isinstance(observacion, ObservacionCamara):
            return False
        firma = (
            observacion.resumen_breve,
            tuple(observacion.observaciones_verificables),
            round(observacion.puntuacion_cambio, 2),
        )
        firma_texto = repr(firma)
        with self._bloqueo:
            self._purgar()
            if firma_texto in self._ultimas_firmas:
                return False
            self._ultimas_firmas.append(firma_texto)
            self._observaciones.append(observacion)
        return True

    def _purgar(self) -> None:
        ahora = time.time()
        limite = ahora - self.ttl_observacion_seg
        while self._observaciones and self._observaciones[0].timestamp < limite:
            self._observaciones.popleft()

    def consultar_entorno_reciente(self, pregunta: str = "") -> dict:
        with self._bloqueo:
            self._purgar()
            observaciones = [o.a_dict() for o in self._observaciones]
        pregunta_norm = str(pregunta or "").strip().lower()
        texto = ""
        if observaciones:
            texto = "; ".join(
                o["resumen_breve"] for o in observaciones[-5:]
                if o.get("resumen_breve")
            )
        return {
            "pregunta": pregunta_norm,
            "observaciones": observaciones,
            "resumen": texto,
        }

    def generar_resumen_cerebro(self, max_caracteres=500) -> str:
        consulta = self.consultar_entorno_reciente()
        resumen = consulta["resumen"]
        if not resumen:
            return "Entorno visual: sin cambios observados."
        limite = max(20, int(max_caracteres))
        return ("Entorno visual reciente: " + resumen)[:limite]

    def limpiar(self) -> None:
        with self._bloqueo:
            self._observaciones.clear()
            self._ultimas_firmas.clear()
