import asyncio
import io
import os
import queue
import re
import subprocess
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
VOZ_EDGE = "es-PA-MargaritaNeural"

EMOCIONES_DEFECTO = {
    "neutral": {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
    "alegre": {"rate": "+8%", "pitch": "+6Hz", "volume": "+0%"},
    "animada": {"rate": "+12%", "pitch": "+8Hz", "volume": "+0%"},
    "calida": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "seria": {"rate": "-6%", "pitch": "-6Hz", "volume": "+0%"},
    "preocupada": {"rate": "-8%", "pitch": "-4Hz", "volume": "-5%"},
}

try:
    from config import EMOCIONES_VOZ
except Exception:
    EMOCIONES_VOZ = EMOCIONES_DEFECTO

EMOCIONES_VALIDAS = set(EMOCIONES_VOZ.keys())

GUION_WINDOWS = (
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$v=$s.GetInstalledVoices()|Where-Object{$_.VoiceInfo.Culture.Name -like 'es*'}|Select-Object -First 1;"
    "if($v){$s.SelectVoice($v.VoiceInfo.Name)};$s.Rate=0;$s.Speak($env:SILVESTRA_TEXTO)"
)


def normalizar_emocion(emocion):
    if not emocion:
        return "neutral"
    e = str(emocion).strip().lower().replace("á", "a")
    return e if e in EMOCIONES_VOZ else "neutral"


def deducir_emocion(texto, contexto=None):
    if contexto:
        ctx = str(contexto).lower()
        if any(c in ctx for c in ("cuidado", "checkin", "salida")):
            return "preocupada"
        if any(c in ctx for c in ("manana", "saludo_manana", "matutino")):
            return "alegre"
        if any(c in ctx for c in ("error", "fallo", "advertencia")):
            return "seria"

    txt = (texto or "").strip().lower()
    if not txt:
        return "neutral"
    if any(p in txt for p in ("error", "fallo", "falló", "problema", "no pude", "no reconozco", "no te conozco")):
        return "seria"
    if "!" in txt or "¡" in txt:
        return "animada"
    if any(p in txt for p in ("buenos días", "buen día", "bienvenido", "qué gusto", "excelente")):
        return "alegre"
    return "neutral"


def dividir_frases(texto):
    partes = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texto.strip()) if p.strip()]
    frases = []
    for p in partes:
        if frases and len(frases[-1]) < 25:
            frases[-1] += " " + p
        else:
            frases.append(p)
    return frases or [texto]


def calcular_envolvente_rms(audio_bytes, fps=30):
    try:
        import numpy as np
        import pygame
        bio = io.BytesIO(audio_bytes)
        snd = pygame.mixer.Sound(bio)
        snd._bio = bio
        arr = pygame.sndarray.array(snd)
        if arr is None or len(arr) == 0:
            return None, snd
        mono = arr.mean(axis=1) if arr.ndim > 1 else arr
        mono = mono.astype(np.float32) / 32768.0
        frec, _, _ = pygame.mixer.get_init()
        muestras = max(1, int(frec / fps))
        num = len(mono) // muestras
        if num == 0:
            return None, snd
        recortado = mono[:num * muestras].reshape(num, muestras)
        rms = np.sqrt(np.mean(recortado**2, axis=1))
        return np.clip(rms * 4.2, 0.0, 1.0).tolist(), snd
    except Exception:
        return None, None


class Voz:
    def __init__(self):
        self.version = 0
        self._activos = 0
        self.proceso = None
        self.pg = None
        self.nivel_volumen = 0.0
        self.ult_primera_palabra = None
        self._lock_mixer = threading.RLock()
        self._buffer_actual = None
        self._snd_actual = None
        try:
            import pygame
            pygame.mixer.init()
            self.pg = pygame
            import voz_cache
            voz_cache.precargar_audios_frecuentes(self._audio)
        except Exception:
            self.pg = None

    def ocupada(self):
        if self._activos > 0:
            return True
        if self.pg is not None:
            try:
                with self._lock_mixer:
                    return bool(self.pg.mixer.music.get_busy() or self.pg.mixer.get_busy())
            except Exception:
                pass
        return False

    def detener(self, motivo="detener()"):
        print(f"[voz] cancelada motivo={motivo}", flush=True)
        self.version += 1
        self._parar()
        self._activos = 0
        self.nivel_volumen = 0.0

    def hablar(self, texto, al_terminar=None, emocion=None):
        emo_base = normalizar_emocion(emocion) if emocion else deducir_emocion(texto)
        flujo = self.flujo(al_terminar, emocion=emo_base)
        for frase in dividir_frases(texto):
            frase_emo = normalizar_emocion(emocion) if emocion else deducir_emocion(frase)
            flujo.agregar(frase, emocion=frase_emo)
        flujo.cerrar()

    def flujo(self, al_terminar=None, emocion="neutral", t_fin_habla=None, metricas=None):
        self.version += 1
        self._activos += 1
        emo = normalizar_emocion(emocion)
        flujo = Flujo(emocion=emo)
        threading.Thread(target=self._hablar, args=(flujo, al_terminar, self.version, emo, t_fin_habla, metricas), daemon=True).start()
        return flujo

    def _parar(self):
        self.nivel_volumen = 0.0
        with self._lock_mixer:
            if self.pg is not None:
                try:
                    self.pg.mixer.music.stop()
                    if hasattr(self.pg.mixer.music, "unload"):
                        self.pg.mixer.music.unload()
                except Exception:
                    pass
                try:
                    self.pg.mixer.stop()
                except Exception:
                    pass
            self._snd_actual = None
            self._buffer_actual = None
        if self.proceso is not None and self.proceso.poll() is None:
            try:
                self.proceso.terminate()
            except Exception:
                pass

    @staticmethod
    def _audio(frase, emocion="neutral"):
        import voz_cache
        en_cache = voz_cache.obtener_audio_cache(frase, emocion)
        if en_cache:
            return en_cache

        import edge_tts
        emo = normalizar_emocion(emocion)
        ajustes = EMOCIONES_VOZ.get(emo) or EMOCIONES_VOZ.get("neutral", {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
        rate, pitch, volume = ajustes.get("rate", "+0%"), ajustes.get("pitch", "+0Hz"), ajustes.get("volume", "+0%")
        print(f"[voz] emocion={emo} rate={rate} pitch={pitch}", flush=True)

        async def crear():
            datos = bytearray()
            async for trozo in edge_tts.Communicate(frase, VOZ_EDGE, rate=rate, pitch=pitch, volume=volume).stream():
                if trozo["type"] == "audio":
                    datos += trozo["data"]
            return bytes(datos)

        audio_generado = asyncio.run(asyncio.wait_for(crear(), 10))
        voz_cache.guardar_audio_cache(frase, audio_generado, emocion)
        return audio_generado

    def soltar_espera(self):
        import config
        if not getattr(config, "MULETILLAS_ACTIVAS", False) or self.ocupada() or self.pg is None:
            return
        import voz_cache
        muletilla = voz_cache.obtener_siguiente_muletilla()
        audio = voz_cache.obtener_audio_cache(muletilla, "neutral")
        if not audio:
            try:
                audio = self._audio(muletilla, "neutral")
            except Exception:
                return
        if audio and self.pg is not None:
            try:
                with self._lock_mixer:
                    bio = io.BytesIO(audio)
                    self._buffer_actual = bio
                    snd = self.pg.mixer.Sound(bio)
                    snd._bio = bio
                    self._snd_actual = snd
                    snd.set_volume(0.65)
                    snd.play()
                    print(f"[voz] muletilla_espera='{muletilla}'", flush=True)
            except Exception:
                pass

    def _voz_windows(self, texto, version, emocion="neutral"):
        entorno = os.environ.copy()
        entorno["SILVESTRA_TEXTO"] = texto
        try:
            proc = subprocess.Popen(["powershell", "-NoProfile", "-Command", GUION_WINDOWS], env=entorno, creationflags=0x08000000)
        except Exception:
            return
        self.proceso = proc
        while proc.poll() is None and version == self.version:
            time.sleep(0.05)

    def _esperar(self, canal, rms_norm, t_inicio, version):
        while version == self.version:
            with self._lock_mixer:
                busy = canal.get_busy() if canal else (self.pg.mixer.music.get_busy() if self.pg else False)
            if not busy:
                break
            if canal and rms_norm:
                idx = int((time.time() - t_inicio) * 30)
                self.nivel_volumen = rms_norm[idx] if idx < len(rms_norm) else 0.0
            time.sleep(0.025)

    def _hablar(self, flujo, al_terminar, version, emocion_defecto="neutral", t_fin_habla=None, metricas=None):
        try:
            self._parar()
            buzon = queue.Queue()
            primera_reportada = False

            def _reportar():
                nonlocal primera_reportada
                if not primera_reportada:
                    primera_reportada = True
                    t_audio = time.time()
                    if metricas and isinstance(metricas, dict):
                        tf, tx, tt = metricas.get("t_fin_habla"), metricas.get("t_texto"), metricas.get("t_primer_token")
                        if tf and tx and tt:
                            print(f"[latencia] fin_habla->texto={tx-tf:.2f}s, texto->primer_token={tt-tx:.2f}s, primer_token->audio={t_audio-tt:.2f}s, total={t_audio-tf:.2f}s", flush=True)
                    if t_fin_habla is not None:
                        dt = t_audio - t_fin_habla
                        ant = getattr(self, "ult_primera_palabra", None)
                        diff = f" (anterior={ant:.2f}s, diff={dt-ant:+.2f}s)" if ant is not None else ""
                        print(f"[tiempo] primera_palabra={dt:.2f}s desde que terminé de hablar{diff}", flush=True)
                        self.ult_primera_palabra = dt

            def productor():
                while True:
                    item = flujo.entrada.get()
                    if item is None or version != self.version:
                        break
                    frase, emo = item if isinstance(item, tuple) else (item, getattr(flujo, "emocion", emocion_defecto))
                    try:
                        audio = self._audio(frase, emo)
                        buzon.put((frase, audio, emo))
                    except Exception:
                        buzon.put((frase, None, emo))
                buzon.put(None)

            threading.Thread(target=productor, daemon=True).start()

            while True:
                item = buzon.get()
                if item is None:
                    break
                if version != self.version:
                    print(f"[voz] cancelada motivo=version_obsoleta ({version}!={self.version})", flush=True)
                    return
                frase, audio, emo = item
                if audio and self.pg is not None:
                    try:
                        canal = None
                        with self._lock_mixer:
                            if version != self.version:
                                return
                            bio = io.BytesIO(audio)
                            self._buffer_actual = bio
                            rms_norm, snd = calcular_envolvente_rms(audio)
                            if snd is not None:
                                snd._bio = bio
                                self._snd_actual = snd
                                canal = snd.play()
                            else:
                                self._snd_actual = None
                                self.pg.mixer.music.load(bio)
                                self.pg.mixer.music.play()

                        print(f"[voz] reproduciendo='{frase}'", flush=True)
                        _reportar()
                        self._esperar(canal, rms_norm if canal else None, time.time(), version)
                        self.nivel_volumen = 0.0

                        with self._lock_mixer:
                            if canal is not None:
                                try:
                                    canal.stop()
                                except Exception:
                                    pass
                            elif self.pg is not None:
                                try:
                                    self.pg.mixer.music.stop()
                                    if hasattr(self.pg.mixer.music, "unload"):
                                        self.pg.mixer.music.unload()
                                except Exception:
                                    pass
                            self._snd_actual = None
                            self._buffer_actual = None

                        if version != self.version:
                            print(f"[voz] cancelada motivo=interrupcion_en_reproduccion frase='{frase}'", flush=True)
                            return
                        print(f"[voz] terminó='{frase}'", flush=True)
                        continue
                    except Exception as e:
                        print(f"[voz] fallo en reproductor ({e}), usando respaldo...", flush=True)
                        with self._lock_mixer:
                            self._snd_actual = None
                            self._buffer_actual = None

                self.nivel_volumen = -1.0
                _reportar()
                print(f"[voz] reproduciendo='{frase}'", flush=True)
                self._voz_windows(frase, version, emocion=emo)
                self.nivel_volumen = 0.0
                if version == self.version:
                    print(f"[voz] terminó='{frase}'", flush=True)

            if version == self.version and al_terminar:
                al_terminar()
        finally:
            self.nivel_volumen = 0.0
            with self._lock_mixer:
                self._snd_actual = None
                self._buffer_actual = None
            self._activos = max(0, self._activos - 1)


class Flujo:
    """Cola de frases que Voz va diciendo en orden con soporte para modulación emocional."""

    def __init__(self, emocion="neutral"):
        self.entrada = queue.Queue()
        self.emocion = normalizar_emocion(emocion)

    def agregar(self, frase, emocion=None):
        if frase and frase.strip():
            emo = normalizar_emocion(emocion) if emocion else (self.emocion if self.emocion != "neutral" else deducir_emocion(frase))
            self.entrada.put((frase.strip(), emo))

    def cerrar(self):
        self.entrada.put(None)
