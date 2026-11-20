"""Flujo de entrada de audio persistente con sounddevice y PortAudio.

Mantiene un único InputStream abierto con callback para evitar la corrupción
del heap de PortAudio en Windows (crash fatal 0xc0000374) causada por abrir
y cerrar streams repetidamente en cada turno de escucha.
"""
import atexit
import queue
import threading


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
