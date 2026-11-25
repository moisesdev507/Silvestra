import asyncio
import io
import os
import queue
import re
import subprocess
import threading
import time

from voz_reproductor import ReproductorAudio, calcular_envolvente_rms
from cara_sincronia import SincroniaLabial

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

VOZ_EDGE = "es-CO-SalomeNeural"

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
    "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select -First 1;"
    "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; $s.Speak($env:SILVESTRA_TEXTO)"
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


class Voz:
    def __init__(self):
        self.version = 0
        self._activos = 0
        self._estado_lock = threading.RLock()
        self._generacion_audio = 0
        self.sincronia_labial = SincroniaLabial()
        self.proceso = None
        self.pg = None
        self.reproductor = None
        self.nivel_volumen = 0.0
        self.ult_primera_palabra = None
        try:
            import pygame

            pygame.mixer.init()
            self.pg = pygame
            self.reproductor = ReproductorAudio(self.pg)
            import voz_cache

            voz_cache.precargar_audios_frecuentes(self._audio)
            try:
                import tts_aura_stream
                tts_aura_stream.precalentar_conexion()
            except Exception:
                pass
        except Exception:
            self.pg = None
            self.reproductor = None

    def ocupada(self):
        """Devuelve True si hay un flujo de voz activo o el mixer está reproduciendo."""
        with self._estado_lock:
            activos = self._activos
        if activos > 0:
            return True
        if self.reproductor is not None:
            return self.reproductor.esta_ocupado()
        return False

    def detener(self, motivo="detener()"):
        """Detiene de inmediato cualquier reproducción o síntesis de voz en curso (barge-in)."""
        print(f"[voz] cancelada motivo={motivo}", flush=True)
        with self._estado_lock:
            self.version += 1
            self._activos = 0
            self.sincronia_labial.cancelar()
        self.nivel_volumen = 0.0
        try:
            import tts_aura_stream
            tts_aura_stream.detener_reproduccion_activa()
        except Exception:
            pass
        self._parar()

    def hablar(self, texto, al_terminar=None, emocion=None):
        emo_base = normalizar_emocion(emocion) if emocion else deducir_emocion(texto)
        flujo = self.flujo(al_terminar, emocion=emo_base)
        for frase in dividir_frases(texto):
            frase_emo = normalizar_emocion(emocion) if emocion else deducir_emocion(frase)
            flujo.agregar(frase, emocion=frase_emo)
        flujo.cerrar()

    def flujo(self, al_terminar=None, emocion="neutral", t_fin_habla=None, metricas=None, t_inicio_texto=None):
        with self._estado_lock:
            self.version += 1
            version = self.version
            self._activos = 1
        emo = normalizar_emocion(emocion)
        flujo = Flujo(emocion=emo)
        threading.Thread(target=self._hablar, args=(flujo, al_terminar, version, emo, t_fin_habla, metricas, t_inicio_texto), daemon=True).start()
        return flujo

    def _parar(self):
        self.nivel_volumen = 0.0
        if self.reproductor is not None:
            self.reproductor.detener()
        if self.proceso is not None and self.proceso.poll() is None:
            try:
                self.proceso.terminate()
            except Exception:
                pass

    @staticmethod
    def _audio(frase, emocion="neutral"):
        import voz_rapida
        return voz_rapida.sintetizar_cadena(frase, emocion)

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
        if audio and self.reproductor is not None:
            self.reproductor.reproducir_corto(audio, volumen=0.65)
            print(f"[voz] muletilla_espera='{muletilla}'", flush=True)

    def _voz_windows(self, texto, version, emocion="neutral"):
        """Voz de respaldo local (Windows SAPI). Ignora la emoción limpiamente sin dar error."""
        if version != self.version:
            return
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
        if version != self.version and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _hablar(self, flujo, al_terminar, version, emocion_defecto="neutral", t_fin_habla=None, metricas=None, t_inicio_texto=None):
        if not hasattr(self, "_generacion_audio"):
            self._generacion_audio = 0
        if not hasattr(self, "sincronia_labial"):
            self.sincronia_labial = SincroniaLabial()
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
                        if dt <= 30.0:
                            ant = getattr(self, "ult_primera_palabra", None)
                            if ant is not None:
                                diff = dt - ant
                                print(f"[tiempo] primera_palabra={dt:.2f}s desde que terminé de hablar (anterior={ant:.2f}s, diff={diff:+.2f}s)", flush=True)
                            else:
                                print(f"[tiempo] primera_palabra={dt:.2f}s desde que terminé de hablar", flush=True)
                            self.ult_primera_palabra = dt
                    elif t_inicio_texto is not None:
                        dt = max(0.0, t_audio - t_inicio_texto)
                        print(f"[tiempo] primera_palabra={dt:.2f}s (turno de texto/HUD)", flush=True)

            def productor():
                while True:
                    item = flujo.entrada.get()
                    if item is None or version != self.version:
                        break
                    frase, emo = item if isinstance(item, tuple) else (item, getattr(flujo, "emocion", emocion_defecto))
                    try:
                        import tts_aura_stream
                        audio = tts_aura_stream.procesar_frase_productor(self, frase, emo)
                    except Exception:
                        try: audio = self._audio(frase, emo)
                        except Exception: audio = None
                    buzon.put((frase, audio, emo))
                buzon.put(None)

            threading.Thread(target=productor, daemon=True).start()

            while True:
                if version != self.version:
                    print(f"[voz] cancelada motivo=version_obsoleta ({version}!={self.version})", flush=True)
                    return
                item = buzon.get()
                if item is None:
                    break
                if version != self.version:
                    print(f"[voz] cancelada motivo=version_obsoleta ({version}!={self.version})", flush=True)
                    return
                frase, audio, emo = item
                with self._estado_lock:
                    self._generacion_audio += 1
                    generacion = self._generacion_audio
                    self.sincronia_labial.preparar(generacion, frase)

                inicio_audio, set_nivel = self.sincronia_labial.callbacks(
                    self, generacion, version, _reportar_primera_palabra)

                # Intentar Aura streaming; si no aplica o falla, obtiene audio fallback
                try:
                    import tts_aura_stream
                    ok_stream, audio = tts_aura_stream.procesar_frase_consumidor(
                        self, frase, audio, emo, generacion, version, inicio_audio, set_nivel)
                    if ok_stream:
                        if version != self.version: return
                        continue
                except Exception: pass

                if audio and self.reproductor is not None:
                    try:
                        print(f"[voz] reproduciendo='{frase}'", flush=True)
                        exito = self.reproductor.reproducir(
                            audio,
                            version_check_fn=lambda: version == self.version,
                            on_nivel_fn=set_nivel,
                            on_inicio_fn=inicio_audio,
                        )
                        if version != self.version:
                            print(f"[voz] cancelada motivo=interrupcion_en_reproduccion frase='{frase}'", flush=True)
                            return
                        self.sincronia_labial.finalizar(generacion)
                        if exito:
                            print(f"[voz] terminó='{frase}'", flush=True)
                            continue
                    except Exception as e:
                        print(f"[voz] fallo en reproductor ({e}), usando respaldo...", flush=True)

                if version != self.version:
                    return
                self.nivel_volumen = -1.0
                inicio_audio()
                _reportar_primera_palabra()
                print(f"[voz] reproduciendo='{frase}'", flush=True)
                self._voz_windows(frase, version, emocion=emo)
                self.nivel_volumen = 0.0
                self.sincronia_labial.finalizar(generacion, inmediata=version != self.version)
                if version == self.version:
                    print(f"[voz] terminó='{frase}'", flush=True)

        finally:
            with self._estado_lock:
                if version == self.version:
                    self.nivel_volumen = 0.0
                    self._activos = max(0, self._activos - 1)
            if version == self.version and al_terminar:
                al_terminar()


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
