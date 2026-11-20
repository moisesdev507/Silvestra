"""Flujo de entrada de audio persistente con sounddevice y PortAudio.

Mantiene un único InputStream abierto con callback para evitar la corrupción
del heap de PortAudio en Windows (crash fatal 0xc0000374) y provee helpers
para filtrado de eco, evaluación de calidad de clips y control anti-alucinaciones.
"""
import atexit
import queue
import threading
import time
import numpy as np

# Frases que Whisper inventa a veces cuando solo hay ruido o cola de eco.
FALSAS = (
    "conversacion informal", "conversación informal", "gracias por ver",
    "subtítulos", "subtitulos", "suscríbete", "suscribete", "amara.org",
    "haha", "jaja", "okay, okay", "ok, ok", "ya entendí", "ya entendi",
    "reproducción automática", "descarga gratuita", "todos los derechos",
    "muchas gracias", "hasta la próxima", "transcripción por",
    "subtítulos realizados por", "subtitulos realizados por",
)


def es_transcripcion_dudosa(r):
    """True si Whisper no está seguro de que haya voz (ruido que inventa palabras)."""
    try:
        segs = getattr(r, "segments", None) or []

        def dato(s, k):
            return s.get(k) if isinstance(s, dict) else getattr(s, k, None)

        sin_voz = [dato(s, "no_speech_prob") for s in segs]
        logp = [dato(s, "avg_logprob") for s in segs]
        sin_voz = [x for x in sin_voz if x is not None]
        logp = [x for x in logp if x is not None]
        if sin_voz and min(sin_voz) > 0.6:
            return True
        if logp and max(logp) < -1.0:
            return True
    except Exception:
        pass
    return False


def evaluar_clip_audio(trozos_utiles, frames_voz, duracion_bloque=0.05):
    """Evalúa si el segmento capturado tiene suficiente voz y energía antes de Whisper.

    Retorna (valido: bool, duracion: float, rms_crudo: float, motivo: str).
    Descarta clips menores a 0.75s, con menos de 0.35s de frames sobre umbral VAD,
    o con energía RMS previa a normalización excesivamente baja (ruido/eco residual).
    """
    if not trozos_utiles:
        return False, 0.0, 0.0, "vacio"

    duracion = len(trozos_utiles) * duracion_bloque
    tiempo_voz = frames_voz * duracion_bloque

    audio_raw = np.concatenate(trozos_utiles)
    rms_crudo = float(np.sqrt(np.mean(audio_raw.astype(np.float32) ** 2)))

    if duracion < 0.75:
        return False, duracion, rms_crudo, f"duracion_corta_{duracion:.2f}s"

    if tiempo_voz < 0.35:
        return False, duracion, rms_crudo, f"voz_insuficiente_{tiempo_voz:.2f}s"

    if rms_crudo < 120.0:
        return False, duracion, rms_crudo, f"energia_baja_rms_{rms_crudo:.1f}"

    return True, duracion, rms_crudo, "ok"


class FlujoMicrofono:
    """Gestiona un stream de entrada persistente y thread-safe para captura de audio."""

    def __init__(self, rate=16000, blocksize=800):
        self.rate = rate
        self.blocksize = blocksize
        self._cola = queue.Queue(maxsize=120)
        self._stream = None
        self._lock = threading.Lock()
        self._activo = False
        atexit.register(self.liberar)

    def _callback(self, indata, frames, time_info, status):
        """Callback invocado por PortAudio en su propio hilo de audio de baja latencia."""
        try:
            self._cola.put_nowait(indata.copy())
        except queue.Full:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                pass
            try:
                self._cola.put_nowait(indata.copy())
            except queue.Full:
                pass

    def asegurar_flujo(self):
        """Abre e inicia el InputStream persistente si no existe o fue cerrado."""
        with self._lock:
            if self._stream is None or not getattr(self._stream, "active", False):
                try:
                    import sounddevice as sd
                    if self._stream is not None:
                        try:
                            self._stream.stop()
                            self._stream.close()
                        except Exception:
                            pass
                        self._stream = None
                    self._stream = sd.InputStream(
                        samplerate=self.rate,
                        channels=1,
                        dtype="int16",
                        blocksize=self.blocksize,
                        callback=self._callback,
                    )
                    self._stream.start()
                    self._activo = True
                except Exception as e:
                    self._stream = None
                    self._activo = False
                    raise RuntimeError(f"Error iniciando InputStream persistente: {e}")

    def drenar(self):
        """Descarta muestras viejas encoladas para empezar a escuchar en tiempo real."""
        while not self._cola.empty():
            try:
                self._cola.get_nowait()
            except queue.Empty:
                break

    def aplicar_guarda_antieco(self, bloques=9, pausa_inicial=0.40):
        """Aplica una ventana de guarda anti-eco descartando el audio residual del parlante."""
        if pausa_inicial > 0:
            time.sleep(pausa_inicial)
        self.drenar()
        # Descartar activamente los siguientes 'bloques' que lleguen del buffer acústico
        for _ in range(bloques):
            try:
                self._cola.get(timeout=0.06)
            except queue.Empty:
                break
        self.drenar()

    def leer(self, timeout=0.1):
        """Lee el siguiente bloque de audio (50 ms) de la cola, o None si agota el timeout."""
        try:
            return self._cola.get(timeout=timeout)
        except queue.Empty:
            return None

    def liberar(self):
        """Detiene y cierra el InputStream para liberar el hardware de audio."""
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
                self._activo = False
            self.drenar()

    @property
    def activo(self):
        """Indica si el stream de audio está actualmente en ejecución."""
        return self._activo and self._stream is not None and getattr(self._stream, "active", False)
