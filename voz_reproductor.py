"""Módulo de reproducción de audio thread-safe con SDL/pygame para Silvestra."""
import io
import threading
import time


def calcular_envolvente_rms(audio_bytes, fps=30):
    """Calcula la envolvente RMS en hilo secundario para sincronía labial no bloqueante."""
    try:
        import numpy as np
        import pygame

        bio = io.BytesIO(audio_bytes)
        snd = pygame.mixer.Sound(bio)
        arr = pygame.sndarray.array(snd)
        if arr is None or len(arr) == 0:
            return None, snd
        mono = arr.mean(axis=1) if arr.ndim > 1 else arr
        mono = mono.astype(np.float32) / 32768.0
        init_res = pygame.mixer.get_init()
        if not init_res:
            return None, snd
        frec = init_res[0]
        muestras_por_cuadro = max(1, int(frec / fps))
        num_cuadros = len(mono) // muestras_por_cuadro
        if num_cuadros == 0:
            return None, snd
        recortado = mono[:num_cuadros * muestras_por_cuadro].reshape(num_cuadros, muestras_por_cuadro)
        rms = np.sqrt(np.mean(recortado**2, axis=1))
        rms_norm = np.clip(rms * 4.2, 0.0, 1.0).tolist()
        return rms_norm, snd
    except Exception:
        return None, None


class ReproductorAudio:
    """Controlador seguro de pygame.mixer y music con Lock y retención de buffers."""

    def __init__(self, pg_module):
        self.pg = pg_module
        self._lock = threading.RLock()
        self._buffer_actual = None
        self._snd_actual = None
        self._canal_actual = None

    def reproducir(self, audio_bytes, version_check_fn, on_nivel_fn, on_inicio_fn=None):
        """Reproduce audio_bytes de forma síncrona en el hilo llamador, actualizando nivel_volumen."""
        if not audio_bytes or self.pg is None:
            return False

        with self._lock:
            if not version_check_fn():
                return False
            self._parar_mixer()
            bio = io.BytesIO(audio_bytes)
            self._buffer_actual = bio
            rms_norm, snd = calcular_envolvente_rms(audio_bytes)
            canal = None
            if snd is not None:
                self._snd_actual = snd
                canal = snd.play()
                self._canal_actual = canal
            else:
                self._snd_actual = None
                self._canal_actual = None
                self.pg.mixer.music.load(bio)
                self.pg.mixer.music.play()

        if on_inicio_fn:
            on_inicio_fn()

        t_inicio = time.time()
        while version_check_fn():
            with self._lock:
                if canal is not None:
                    busy = canal.get_busy()
                elif self.pg is not None:
                    busy = self.pg.mixer.music.get_busy()
                else:
                    busy = False
            if not busy:
                break

            if canal is not None and rms_norm:
                idx = int((time.time() - t_inicio) * 30)
                vol = rms_norm[idx] if idx < len(rms_norm) else 0.0
                on_nivel_fn(vol)
            else:
                on_nivel_fn(-1.0)

            time.sleep(0.02)

        on_nivel_fn(0.0)

        with self._lock:
            self._parar_mixer()

        return version_check_fn()

    def reproducir_corto(self, audio_bytes, volumen=0.65):
        """Reproduce un audio corto (ej. muletilla) en un canal libre de forma no bloqueante."""
        if not audio_bytes or self.pg is None:
            return
        with self._lock:
            try:
                bio = io.BytesIO(audio_bytes)
                snd = self.pg.mixer.Sound(bio)
                self._snd_actual = snd
                self._buffer_actual = bio
                snd.set_volume(volumen)
                snd.play()
            except Exception:
                pass

    def detener(self):
        """Detiene de inmediato toda reproducción activa y libera buffers bajo Lock."""
        with self._lock:
            self._parar_mixer()

    def esta_ocupado(self):
        """Verifica si el mixer o la música están actualmente reproduciendo."""
        if self.pg is None:
            return False
        with self._lock:
            try:
                if self._canal_actual is not None and self._canal_actual.get_busy():
                    return True
                if self.pg.mixer.music.get_busy() or self.pg.mixer.get_busy():
                    return True
            except Exception:
                pass
        return False

    def _parar_mixer(self):
        """Detiene canales y música, descarga buffers. Debe llamarse dentro de self._lock."""
        if self.pg is None:
            return
        if self._canal_actual is not None:
            try:
                self._canal_actual.stop()
            except Exception:
                pass
            self._canal_actual = None
        try:
            self.pg.mixer.stop()
        except Exception:
            pass
        try:
            self.pg.mixer.music.stop()
            if hasattr(self.pg.mixer.music, "unload"):
                self.pg.mixer.music.unload()
        except Exception:
            pass
        self._snd_actual = None
        self._buffer_actual = None
