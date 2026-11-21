"""Clasificacion acustica local y adaptadores con privacidad explicita."""
from __future__ import annotations
import math
import re
import wave
import numpy as np
from audio_evento_modelo import CategoriaSonido, ClasificacionAcustica


class AdaptadorClasificadorAudio:
    def clasificar(self, muestras, sample_rate, ratio_voz_vad=0.0):
        raise NotImplementedError


class ClasificadorAcusticoEspectral(AdaptadorClasificadorAudio):
    def __init__(self, detector_vad=None):
        self.vad = detector_vad

    def _ratio_vad(self, pcm, sr, energia, voz_fft):
        if self.vad is None:
            try:
                from oido_vad import DetectorVozSilero
                self.vad = DetectorVozSilero()
            except Exception:
                self.vad = None
        if self.vad is not None:
            try:
                if getattr(self.vad, "disponible", False):
                    self.vad.reset()
                    paso = max(1, sr // 20)
                    for inicio in range(0, len(pcm), paso):
                        self.vad.alimentar(np.clip(pcm[inicio:inicio+paso]*32768, -32768, 32767).astype(np.int16))
                    return 1.0 if self.vad.detectando_voz() or self.vad.hay_segmento_completo() else 0.0
            except Exception:
                pass
        return min(1.0, max(0.0, voz_fft * (1.0 if energia > 0.012 else 0.0)))

    def clasificar(self, muestras, sample_rate, ratio_voz_vad=0.0):
        arr = np.asarray(muestras, dtype=np.float32).reshape(-1)
        try:
            if not len(arr) or sample_rate <= 0:
                return ClasificacionAcustica()
            if np.max(np.abs(arr)) > 1.5:
                arr = arr / 32768.0
            arr = np.clip(arr, -1.0, 1.0)
            rms = float(np.sqrt(np.mean(arr * arr)))
            frames = np.array_split(arr, min(40, max(1, len(arr)//max(1, sample_rate//50))))
            env = np.array([float(np.sqrt(np.mean(f*f))) if len(f) else 0 for f in frames])
            p = np.abs(np.fft.rfft(arr))
            hz = np.fft.rfftfreq(len(arr), 1.0/sample_rate)
            total = float(np.sum(p)) + 1e-9
            low = float(np.sum(p[hz < 500])/total)
            mid = float(np.sum(p[(hz >= 300) & (hz < 3500)])/total)
            tonal = float(np.max(p)/total)
            voiced_band = float(np.sum(p[(hz >= 250) & (hz <= 3800)])/total)
            vad = self._ratio_vad(arr, sample_rate, rms, voiced_band) if ratio_voz_vad <= 0 else float(ratio_voz_vad)
            peaks = int(np.sum(env > max(0.015, float(np.mean(env))*2.2)))
            bloques = np.array_split(arr, min(12, max(1, len(arr)//max(1, sample_rate//12))))
            frecuencias = []
            for bloque in bloques:
                if len(bloque) > 16 and np.max(np.abs(bloque)) > .01:
                    bp = np.abs(np.fft.rfft(bloque * np.hanning(len(bloque))))
                    bh = np.fft.rfftfreq(len(bloque), 1.0/sample_rate)
                    frecuencias.append(float(bh[int(np.argmax(bp))]))
            pasos_freq = np.diff(frecuencias) if len(frecuencias) >= 4 else np.array([])
            monotono = (len(pasos_freq) > 0 and
                max(np.mean(pasos_freq >= 0), np.mean(pasos_freq <= 0)) >= .75)
            barrido = (len(frecuencias) >= 4 and max(frecuencias)-min(frecuencias) > 350 and monotono)
            centroid = float(np.sum(hz*p)/total)
            picos_tonales = int(np.sum((p[1:-1] > p[:-2]) & (p[1:-1] > p[2:]) & (p[1:-1] > np.max(p)*.08)))
            if rms < 0.003:
                cat, conf = CategoriaSonido.ruido_ambiental, 0.98
            elif vad >= 0.5 and voiced_band > 0.05:
                cat, conf = CategoriaSonido.voz_humana, min(.92, .62 + vad*.3)
            elif barrido:
                cat, conf = CategoriaSonido.sirena, .68
            elif tonal > .16 and len(p) and hz[int(np.argmax(p))] > 1700:
                cat, conf = CategoriaSonido.alarma, .72
            elif tonal > .10 and rms > .025 and picos_tonales >= 2:
                cat, conf = CategoriaSonido.timbre, .65
            elif peaks >= 2 and low > .35:
                cat, conf = CategoriaSonido.golpes, .68
            elif peaks >= 2 and mid > .45 and centroid > 1800:
                cat, conf = CategoriaSonido.aplausos, .57
            elif mid > .50 and peaks >= 1 and centroid < 1800:
                cat, conf = CategoriaSonido.ladridos, .56
            else:
                cat, conf = CategoriaSonido.ruido_ambiental, .58
            relevante = cat not in (CategoriaSonido.ruido_ambiental, CategoriaSonido.eco_silvestra) and rms >= .01
            return ClasificacionAcustica(cat, "heuristica_espectral", conf,
                cat == CategoriaSonido.voz_humana, relevante, "fft_local")
        finally:
            del arr

    def clasificar_wav(self, ruta):
        with wave.open(ruta, "rb") as f:
            if f.getnchannels() != 1 or f.getsampwidth() not in (1, 2, 4):
                raise ValueError("WAV debe ser mono y PCM de 8/16/32 bits")
            raw = f.readframes(f.getnframes())
            dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[f.getsampwidth()]
            pcm = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if dtype == np.uint8:
                pcm = (pcm - 128) / 128
            else:
                pcm /= float(2 ** (8*f.getsampwidth()-1))
            return self.clasificar(pcm, f.getframerate()), len(raw), f.getnframes()/f.getframerate()


class DetectorEcoSilvestra:
    def __init__(self, voz=None, proveedor=None):
        self.voz, self.proveedor = voz, proveedor

    def hablando(self):
        try:
            return bool(self.proveedor()) if self.proveedor else bool(self.voz and self.voz.ocupada())
        except Exception:
            return False


class ClasificadorAudioRemoto(AdaptadorClasificadorAudio):
    def __init__(self, proveedor, permitir_envio_externo=False, timeout_seg=3.0):
        self.proveedor, self.permitido, self.timeout = proveedor, permitir_envio_externo, timeout_seg

    def clasificar(self, muestras, sample_rate, ratio_voz_vad=0.0):
        if not self.permitido:
            raise PermissionError("Envio externo de audio no autorizado")
        try:
            raw = self.proveedor.clasificar(muestras, sample_rate, timeout=self.timeout)
            conf = raw.get("confianza") if isinstance(raw, dict) else None
            conf = float(conf) if isinstance(conf, (int, float)) and math.isfinite(float(conf)) and 0 <= float(conf) <= 1 else None
            return ClasificacionAcustica(CategoriaSonido(raw.get("categoria", "desconocido")),
                "", conf, bool(raw.get("es_voz", False)), bool(conf and conf >= .55), "remoto")
        except Exception as exc:
            raise RuntimeError(re.sub(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*\S+", r"\1=***", str(exc))) from None
