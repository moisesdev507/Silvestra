"""Gate local de audio para Gemini Live: silencio sin tokens y reposo por inactividad.

El detector VAD ya existente en ``live_audio.es_voz_activa`` (RMS + energía) se
aplica aquí a cada frame PCM de 50 ms antes del WebSocket. Silero/sherpa en
``oido_vad.py`` trabaja por segmentos de activación y se reserva para la palabra
clave; en el camino caliente de Live se usa el detector ligero para no añadir
latencia ni dependencias.
"""
import queue
import threading
import time
from collections import deque
from typing import Optional

import live_audio

PRERROLL_MS = 400.0
HANGOVER_MS = 800.0
MARGEN_REPRODUCCION_MS = 350.0
ESTADO_REPOSO = "en_reposo"
ESTADO_ESCUCHANDO = "escuchando"


class PuertaAudioLive:
    """Decide qué frames PCM llegan a Gemini Live y cuándo cerrar la sesión."""

    def __init__(
        self,
        timeout_silencio: Optional[float] = None,
        frame_ms: Optional[float] = None,
        preroll_ms: Optional[float] = None,
        hangover_ms: Optional[float] = None,
        margen_cola_ms: Optional[float] = None,
        detector=None,
        reloj=None,
    ):
        self.timeout_silencio = live_audio.timeout_silencio_configurado(timeout_silencio)
        self.frame_ms = float(frame_ms or live_audio.CHUNK_ENTRADA_MS)
        self.preroll_ms = float(PRERROLL_MS if preroll_ms is None else preroll_ms)
        self.hangover_ms = float(HANGOVER_MS if hangover_ms is None else hangover_ms)
        self.margen_cola_ms = float(MARGEN_REPRODUCCION_MS if margen_cola_ms is None else margen_cola_ms)
        self._detector = detector or live_audio.es_voz_activa
        self._reloj = reloj or time.monotonic
        self._bloqueo = threading.RLock()
        self._max_preroll = max(1, int(round(self.preroll_ms / self.frame_ms)))
        self._preroll = deque(maxlen=self._max_preroll)
        self._activa = False
        self._abierta = False
        self._reproduciendo = False
        self._t_fin_reproduccion = None
        ahora = self._reloj()
        self._t_ultima_voz = ahora
        self._t_ultima_actividad = ahora
        self._frames_enviados = 0
        self._frames_descartados = 0

    @property
    def activa(self) -> bool:
        with self._bloqueo:
            return self._activa

    @property
    def estado(self) -> str:
        return ESTADO_ESCUCHANDO if self.activa else ESTADO_REPOSO

    @property
    def abierta(self) -> bool:
        with self._bloqueo:
            return self._abierta

    @property
    def reproduciendo(self) -> bool:
        with self._bloqueo:
            return self._reproduciendo or self._en_margen(self._reloj())

    def _en_margen(self, ahora: float) -> bool:
        """True mientras suena la cola acústica tras vaciarse la salida."""
        return (self._t_fin_reproduccion is not None
                and (ahora - self._t_fin_reproduccion) < (self.margen_cola_ms / 1000.0))

    @property
    def ultima_actividad(self) -> float:
        with self._bloqueo:
            return self._t_ultima_actividad

    @property
    def frames_enviados(self) -> int:
        with self._bloqueo:
            return self._frames_enviados

    @property
    def frames_descartados(self) -> int:
        with self._bloqueo:
            return self._frames_descartados

    def activar(self):
        """Abre la captura con pre-roll vacío y reloj de inactividad fresco."""
        with self._bloqueo:
            self._activa = True
            self._abierta = False
            self._reproduciendo = False
            self._t_fin_reproduccion = None
            self._preroll.clear()
            ahora = self._reloj()
            self._t_ultima_voz = ahora
            self._t_ultima_actividad = ahora

    def desactivar(self):
        """Cierra la captura: estado en_reposo y micrófono sin consumir tokens."""
        with self._bloqueo:
            self._activa = False
            self._abierta = False
            self._reproduciendo = False
            self._t_fin_reproduccion = None
            self._preroll.clear()

    def reiniciar(self):
        """Reactivación manual: nada del turno anterior sobrevive."""
        self.desactivar()
        self.activar()

    def notificar_actividad(self, instante: Optional[float] = None):
        """Refresca el reloj de inactividad (turno completado, respuesta, etc.)."""
        with self._bloqueo:
            self._t_ultima_actividad = self._reloj() if instante is None else float(instante)

    def marcar_reproduccion(self, activa: bool):
        """Inicio/fin real de reproducción: suspende y reinicia la inactividad."""
        with self._bloqueo:
            ahora = self._reloj()
            if activa:
                self._reproduciendo = True
                self._t_fin_reproduccion = None
                self._t_ultima_actividad = ahora
            elif self._reproduciendo:
                self._reproduciendo = False
                self._t_fin_reproduccion = ahora

    def debe_cerrar(self) -> bool:
        """True tras el timeout; cuenta desde el fin real de la reproducción."""
        with self._bloqueo:
            if not self._activa or self._reproduciendo:
                return False
            ahora = self._reloj()
            if self._en_margen(ahora):
                return False
            inicio = self._t_ultima_actividad
            if self._t_fin_reproduccion is not None:
                inicio = max(inicio, self._t_fin_reproduccion + self.margen_cola_ms / 1000.0)
            return (ahora - inicio) >= self.timeout_silencio

    def procesar(self, pcm_bytes: bytes) -> tuple[list[bytes], bool]:
        """Devuelve (frames autorizados, hay_voz). El silencio nunca sale del gate."""
        if not pcm_bytes:
            return [], False
        with self._bloqueo:
            if not self._activa:
                self._frames_descartados += 1
                return [], False
            ahora = self._reloj()
            if self._reproduciendo or self._en_margen(ahora):
                self._abierta = False
                self._preroll.clear()
                self._frames_descartados += 1
                return [], False
            habla, _, _ = self._detector(pcm_bytes)
            if habla:
                self._t_ultima_voz = ahora
                self._t_ultima_actividad = ahora
            hangover = self._abierta and (ahora - self._t_ultima_voz) < (self.hangover_ms / 1000.0)
            if habla or hangover:
                if self._abierta:
                    autorizados = []
                else:
                    self._abierta = True
                    autorizados = list(self._preroll)
                    self._preroll.clear()
                autorizados.append(pcm_bytes)
                self._frames_enviados += len(autorizados)
                return autorizados, habla
            self._abierta = False
            self._preroll.append(pcm_bytes)
            self._frames_descartados += 1
            return [], False


def encolar_autorizados(puerta: PuertaAudioLive, pcm_bytes: bytes, cola) -> bool:
    """Encola solo los frames que autoriza el gate; devuelve si hubo voz."""
    autorizados, habla = puerta.procesar(pcm_bytes)
    for frame in autorizados:
        try:
            cola.put_nowait(frame)
        except queue.Full:
            pass
    return habla
