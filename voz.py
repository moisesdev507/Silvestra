import asyncio
import io
import os
import queue
import re
import subprocess
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Voz natural de Microsoft Edge (gratis, necesita internet).
# Si falla o no hay internet, usa la voz de Windows.
VOZ_EDGE = "es-PA-MargaritaNeural"

# Diccionario de respaldo por si config no define EMOCIONES_VOZ
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
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1;"
    "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
    "$s.Rate = 0;"
    "$s.Speak($env:SILVESTRA_TEXTO)"
)


def normalizar_emocion(emocion):
    """Devuelve un nombre de emoción válido o 'neutral' si no se reconoce."""
    if not emocion:
        return "neutral"
    e = str(emocion).strip().lower().replace("á", "a")
    if e in EMOCIONES_VOZ:
        return e
    return "neutral"


def deducir_emocion(texto, contexto=None):
    """Deduce una emoción sutil según el contexto o el contenido del texto."""
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

    # Errores o fallos técnicos -> seria
    if any(p in txt for p in ("error", "falló", "fallo", "problema", "no pude", "no reconozco", "no te conozco")):
        return "seria"

    # Exclamaciones -> animada
    if "!" in txt or "¡" in txt:
        return "animada"

    # Saludos matutinos o entusiasmo
    if any(p in txt for p in ("buenos días", "buen día", "bienvenido", "qué gusto", "excelente")):
        return "alegre"

    return "neutral"


def dividir_frases(texto):
    """Parte el texto en frases para empezar a hablar con la primera."""
    partes = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texto.strip()) if p.strip()]
    frases = []
    for p in partes:
        if frases and len(frases[-1]) < 25:  # une frases muy cortas
            frases[-1] += " " + p
        else:
            frases.append(p)
    return frases or [texto]


def calcular_envolvente_rms(audio_bytes, fps=30):
    """Calcula la envolvente RMS en hilo secundario para sincronía labial no bloqueante."""
    try:
        import numpy as np
        import pygame
        snd = pygame.mixer.Sound(io.BytesIO(audio_bytes))
        arr = pygame.sndarray.array(snd)
        if arr is None or len(arr) == 0:
            return None, snd
        mono = arr.mean(axis=1) if arr.ndim > 1 else arr
        mono = mono.astype(np.float32) / 32768.0
        frec, _, _ = pygame.mixer.get_init()
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


class Voz:
    def __init__(self):
        self.version = 0
        self._activos = 0
        self.proceso = None
        self.pg = None
        self.nivel_volumen = 0.0
        self.ult_primera_palabra = None
        try:
            import pygame

            pygame.mixer.init()
            self.pg = pygame
            import voz_cache
            voz_cache.precargar_audios_frecuentes(self._audio)
        except Exception:
            self.pg = None

    def ocupada(self):
        """Devuelve True si hay un flujo de voz activo o el mixer está reproduciendo."""
        if self._activos > 0:
            return True
        if self.pg is not None:
            try:
                if self.pg.mixer.music.get_busy() or self.pg.mixer.get_busy():
                    return True
            except Exception:
                pass
        return False

    def detener(self, motivo="detener()"):
        """Detiene de inmediato cualquier reproducción o síntesis de voz en curso (barge-in)."""
        print(f"[voz] cancelada motivo={motivo}", flush=True)
        self.version += 1
        self._parar()
        self._activos = 0
        self.nivel_volumen = 0.0

    def hablar(self, texto, al_terminar=None, emocion=None):
        """Dice el texto completo frase por frase con la emoción indicada o deducida."""
        emo_base = normalizar_emocion(emocion) if emocion else deducir_emocion(texto)
        flujo = self.flujo(al_terminar, emocion=emo_base)
        for frase in dividir_frases(texto):
            frase_emo = normalizar_emocion(emocion) if emocion else deducir_emocion(frase)
            flujo.agregar(frase, emocion=frase_emo)
        flujo.cerrar()

    def flujo(self, al_terminar=None, emocion="neutral", t_fin_habla=None, metricas=None):
        """Empieza a hablar frase por frase conforme van llegando. Usa .agregar(frase) y al final .cerrar()."""
        self.version += 1
        self._activos += 1
        emo = normalizar_emocion(emocion)
        flujo = Flujo(emocion=emo)
        threading.Thread(target=self._hablar, args=(flujo, al_terminar, self.version, emo, t_fin_habla, metricas), daemon=True).start()
        return flujo

    def _parar(self):
        self.nivel_volumen = 0.0
        if self.pg is not None:
            try:
                self.pg.mixer.music.stop()
                self.pg.mixer.stop()
            except Exception:
                pass
        if self.proceso is not None and self.proceso.poll() is None:
            self.proceso.terminate()

    @staticmethod
    def _audio(frase, emocion="neutral"):
        import voz_cache
        en_cache = voz_cache.obtener_audio_cache(frase, emocion)
        if en_cache:
            return en_cache

        import edge_tts

        emo = normalizar_emocion(emocion)
        ajustes = EMOCIONES_VOZ.get(emo) or EMOCIONES_VOZ.get("neutral", {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
        rate = ajustes.get("rate", "+0%")
        pitch = ajustes.get("pitch", "+0Hz")
        volume = ajustes.get("volume", "+0%")

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
        """Reproduce inmediatamente una muletilla o sonido natural en caché si la respuesta demora."""
        import config
        if not getattr(config, "MULETILLAS_ACTIVAS", False):
            return
        if self.ocupada() or self.pg is None:
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
                snd = self.pg.mixer.Sound(io.BytesIO(audio))
                snd.set_volume(0.65)
                snd.play()
                print(f"[voz] muletilla_espera='{muletilla}'", flush=True)
            except Exception:
                pass

    def _voz_windows(self, texto, version, emocion="neutral"):
        """Voz de respaldo local (Windows SAPI). Ignora la emoción limpiamente sin dar error."""
        entorno = os.environ.copy()
        entorno["SILVESTRA_TEXTO"] = texto
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", GUION_WINDOWS],
                env=entorno,
                creationflags=0x08000000,
            )
        except Exception:
            return
        self.proceso = proc
        while proc.poll() is None and version == self.version:
            time.sleep(0.05)

    def _hablar(self, flujo, al_terminar, version, emocion_defecto="neutral", t_fin_habla=None, metricas=None):
        try:
            self._parar()
            buzon = queue.Queue()
            primera_reportada = False

            def _reportar_primera_palabra():
                nonlocal primera_reportada
                if not primera_reportada:
                    primera_reportada = True
                    t_audio = time.time()
                    if metricas and isinstance(metricas, dict):
                        t_fin = metricas.get("t_fin_habla")
                        t_txt = metricas.get("t_texto")
                        t_tok = metricas.get("t_primer_token")
                        if t_fin and t_txt and t_tok:
                            d_trans = max(0.0, t_txt - t_fin)
                            d_token = max(0.0, t_tok - t_txt)
                            d_audio = max(0.0, t_audio - t_tok)
                            d_total = max(0.0, t_audio - t_fin)
                            print(f"[latencia] fin_habla->texto={d_trans:.2f}s, texto->primer_token={d_token:.2f}s, primer_token->audio={d_audio:.2f}s, total={d_total:.2f}s", flush=True)
                    if t_fin_habla is not None:
                        dt = t_audio - t_fin_habla
                        ant = getattr(self, "ult_primera_palabra", None)
                        if ant is not None:
                            diff = dt - ant
                            print(f"[tiempo] primera_palabra={dt:.2f}s desde que terminé de hablar (anterior={ant:.2f}s, diff={diff:+.2f}s)", flush=True)
                        else:
                            print(f"[tiempo] primera_palabra={dt:.2f}s desde que terminé de hablar", flush=True)
                        self.ult_primera_palabra = dt

            def productor():
                while True:
                    item = flujo.entrada.get()
                    if item is None or version != self.version:
                        break
                    if isinstance(item, tuple):
                        frase, emo = item
                    else:
                        frase = item
                        emo = getattr(flujo, "emocion", emocion_defecto)
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
                        rms_norm, snd = calcular_envolvente_rms(audio)
                        canal = snd.play() if snd is not None else None
                        print(f"[voz] reproduciendo='{frase}'", flush=True)
                        _reportar_primera_palabra()
                        if canal is not None:
                            t_inicio = time.time()
                            while canal.get_busy() and version == self.version:
                                if rms_norm:
                                    dt = time.time() - t_inicio
                                    idx = int(dt * 30)
                                    self.nivel_volumen = rms_norm[idx] if idx < len(rms_norm) else 0.0
                                else:
                                    self.nivel_volumen = -1.0
                                time.sleep(0.025)
                        else:
                            self.pg.mixer.music.load(io.BytesIO(audio))
                            self.pg.mixer.music.play()
                            self.nivel_volumen = -1.0
                            while self.pg.mixer.music.get_busy() and version == self.version:
                                time.sleep(0.04)
                        self.nivel_volumen = 0.0
                        if version != self.version:
                            print(f"[voz] cancelada motivo=interrupcion_en_reproduccion frase='{frase}'", flush=True)
                            return
                        print(f"[voz] terminó='{frase}'", flush=True)
                        continue
                    except Exception as e:
                        print(f"[voz] fallo en reproductor ({e}), usando respaldo...", flush=True)
                self.nivel_volumen = -1.0
                _reportar_primera_palabra()
                print(f"[voz] reproduciendo='{frase}'", flush=True)
                self._voz_windows(frase, version, emocion=emo)
                self.nivel_volumen = 0.0
                if version == self.version:
                    print(f"[voz] terminó='{frase}'", flush=True)

            if version == self.version and al_terminar:
                al_terminar()
        finally:
            self.nivel_volumen = 0.0
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
