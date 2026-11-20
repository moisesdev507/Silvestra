"""Detector de actividad vocal (VAD) neuronal basado en Silero VAD y sherpa-onnx.

Procesa audio a 16 kHz en ventanas de 512 muestras (32 ms), detecta habla humana real
y entrega segmentos limpios con soporte de fallback por energía RMS.
"""
import os
import numpy as np


class DetectorVozSilero:
    """Encapsula VoiceActivityDetector de sherpa-onnx con Silero VAD a 16 kHz."""

    def __init__(
        self,
        ruta_modelo=None,
        sample_rate=16000,
        threshold=0.5,
        min_silence_duration=1.0,
        min_speech_duration=0.25,
        max_speech_duration=15.0,
        buffer_size=20.0,
    ):
        if ruta_modelo is None:
            ruta_modelo = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "modelos",
                "silero_vad.onnx",
            )
        self.ruta_modelo = ruta_modelo
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_silence_duration = min_silence_duration
        self.min_speech_duration = min_speech_duration
        self.max_speech_duration = max_speech_duration
        self.buffer_size = buffer_size

        self._detector = None
        self._disponible = False
        self._residuo = np.array([], dtype=np.float32)

        # Variables de fallback RMS si el modelo ONNX no está presente
        self._fb_audio = []
        self._fb_hablando = False
        self._fb_silencio_count = 0
        self._fb_segmento_listo = False

        self._iniciar_detector()

    def _iniciar_detector(self):
        """Inicializa sherpa_onnx.VoiceActivityDetector si el modelo existe."""
        if not os.path.exists(self.ruta_modelo):
            print(f"[oido_vad] Modelo no encontrado en {self.ruta_modelo}. Modo fallback RMS activo.", flush=True)
            self._disponible = False
            return

        try:
            import sherpa_onnx

            sc = sherpa_onnx.SileroVadModelConfig(
                model=self.ruta_modelo,
                threshold=self.threshold,
                min_silence_duration=self.min_silence_duration,
                min_speech_duration=self.min_speech_duration,
                window_size=512,
                max_speech_duration=self.max_speech_duration,
            )
            vc = sherpa_onnx.VadModelConfig(
                silero_vad=sc,
                sample_rate=self.sample_rate,
                num_threads=1,
                provider="cpu",
                debug=False,
            )
            self._detector = sherpa_onnx.VoiceActivityDetector(
                vc,
                buffer_size_in_seconds=self.buffer_size,
            )
            self._disponible = True
            print("[oido_vad] Silero VAD neuronal inicializado a 16 kHz.", flush=True)
        except Exception as e:
            print(f"[oido_vad] Error cargando sherpa-onnx Silero VAD: {e}. Fallback RMS.", flush=True)
            self._detector = None
            self._disponible = False

    @property
    def disponible(self):
        """True si Silero VAD neuronal está cargado y operativo."""
        return self._disponible and self._detector is not None

    def reset(self):
        """Reinicia el detector para un nuevo turno de escucha."""
        self._residuo = np.array([], dtype=np.float32)
        if self.disponible:
            try:
                self._detector.reset()
            except Exception:
                pass
        self._fb_audio.clear()
        self._fb_hablando = False
        self._fb_silencio_count = 0
        self._fb_segmento_listo = False

    def alimentar(self, datos_int16):
        """Alimenta un bloque de audio int16 en trozos exactos de 512 muestras."""
        if datos_int16 is None:
            return

        arr_1d = np.asarray(datos_int16, dtype=np.float32).reshape(-1)
        if len(arr_1d) == 0:
            return

        muestras = arr_1d / np.float32(32768.0)

        if self.disponible:
            if len(self._residuo) > 0:
                muestras = np.concatenate([self._residuo, muestras])
                self._residuo = np.array([], dtype=np.float32)

            total = len(muestras)
            paso = 512
            limite = (total // paso) * paso
            if limite > 0:
                chunk = np.ascontiguousarray(muestras[:limite], dtype=np.float32)
                self._detector.accept_waveform(chunk)
            if limite < total:
                self._residuo = np.ascontiguousarray(muestras[limite:], dtype=np.float32)
            else:
                self._residuo = np.array([], dtype=np.float32)
        else:
            # Fallback RMS sencillo
            self._fb_audio.append(muestras)
            nivel = float(np.mean(np.abs(muestras))) * 32768.0
            if nivel > 160.0:
                self._fb_hablando = True
                self._fb_silencio_count = 0
            elif self._fb_hablando:
                self._fb_silencio_count += 1
                if self._fb_silencio_count >= 20:  # ~1.0s de silencio
                    self._fb_segmento_listo = True

    def detectando_voz(self):
        """True si actualmente se detecta actividad de voz humana."""
        if self.disponible:
            try:
                return bool(self._detector.is_speech_detected())
            except Exception:
                return False
        return self._fb_hablando

    def hay_segmento_completo(self):
        """True si hay al menos un segmento completo de habla listo para extraer."""
        if self.disponible:
            try:
                return not self._detector.empty()
            except Exception:
                return False
        return self._fb_segmento_listo

    def extraer_segmento(self):
        """Extrae el primer segmento disponible como array 1D float32 en [-1.0, 1.0]."""
        if self.disponible:
            try:
                if self._detector.empty():
                    return None
                seg = self._detector.front
                muestras = np.ascontiguousarray(seg.samples, dtype=np.float32).reshape(-1)
                self._detector.pop()
                return muestras
            except Exception as e:
                print(f"[oido_vad] Error extrayendo segmento Silero: {e}", flush=True)
                return None
        else:
            if not self._fb_audio:
                return None
            res = np.ascontiguousarray(np.concatenate(self._fb_audio), dtype=np.float32).reshape(-1)
            self._fb_audio.clear()
            self._fb_hablando = False
            self._fb_silencio_count = 0
            self._fb_segmento_listo = False
            return res

    def flush(self):
        """Fuerza el cierre del segmento en curso (útil al alcanzar tiempo máximo)."""
        if self.disponible:
            try:
                if len(self._residuo) > 0:
                    faltan = 512 - len(self._residuo)
                    if faltan > 0:
                        bloque = np.pad(self._residuo, (0, faltan), mode="constant")
                    else:
                        bloque = self._residuo[:512]
                    chunk = np.ascontiguousarray(bloque, dtype=np.float32).reshape(-1)
                    self._detector.accept_waveform(chunk)
                    self._residuo = np.array([], dtype=np.float32)
                self._detector.flush()
            except Exception as e:
                print(f"[oido_vad] Error en flush Silero: {e}", flush=True)
        else:
            if self._fb_audio:
                self._fb_segmento_listo = True
