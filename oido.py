import io
import time
import threading
import wave
from collections import deque

from config import MODELO_VOZ

# Frases que Whisper inventa a veces cuando solo hay ruido.
FALSAS = ("conversación informal", "conversacion informal", "gracias por ver", "subtítulos", "subtitulos", "suscríbete", "amara.org")


class Oido:
    """Escucha el micrófono hasta que hables, y lo convierte en texto."""

    def __init__(self, cliente, vocabulario):
        self.cliente = cliente
        self.vocabulario = vocabulario  # función que devuelve nombres propios
        self.bloqueo = threading.Lock()  # un solo uso del micrófono a la vez
        self.debe_avisar_respaldo = False
        self.aviso_respaldo_dicho = False
        self._modelo_vosk = None
        self._reconocedor_vosk = None
        self.ultimo_audio = None
        self.duracion_ultimo_audio = 0.0

    def _obtener_reconocedor_vosk(self):
        """Carga perezosa del modelo Vosk sin gramática restringida para no subir el arranque ni la RAM."""
        if self._reconocedor_vosk is None:
            import os
            import vosk
            ruta_modelo = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "modelos",
                "vosk-model-small-es-0.42",
            )
            if not os.path.exists(ruta_modelo):
                raise RuntimeError(f"No se encontró el modelo Vosk en {ruta_modelo}")
            if self._modelo_vosk is None:
                self._modelo_vosk = vosk.Model(ruta_modelo)
            # KaldiRecognizer libre sin gramática restringida
            self._reconocedor_vosk = vosk.KaldiRecognizer(self._modelo_vosk, 16000)
        return self._reconocedor_vosk

    def _transcribir_vosk(self, audio_bytes):
        """Transcribe audio int16 16kHz usando Vosk local como respaldo cuando Whisper falla."""
        try:
            import json
            t0 = time.time()
            rec = self._obtener_reconocedor_vosk()
            rec.Reset()
            rec.AcceptWaveform(audio_bytes)
            res = json.loads(rec.FinalResult())
            texto = (res.get("text") or "").strip()
            print(f"[tiempo] vosk={time.time() - t0:.2f}s", flush=True)
            if texto and texto not in ("[unk]", "unk"):
                print("[oido] respaldo=vosk", flush=True)
                if not self.aviso_respaldo_dicho:
                    self.aviso_respaldo_dicho = True
                    self.debe_avisar_respaldo = True
                return texto
            return None
        except Exception as err:
            print(f"[oido] Fallo en Vosk de respaldo: {err}", flush=True)
            return None

    def escuchar(self, corto=False):
        for intento in range(2):
            adquirido = self.bloqueo.acquire(timeout=4.0)
            if not adquirido:
                print(f"[oido] Aviso: no pude adquirir el micrófono tras 4.0s (intento {intento + 1}/2). Reintentando...", flush=True)
                time.sleep(0.2)
                continue
            try:
                return self._escuchar(corto)
            finally:
                self.bloqueo.release()
        print("[oido] Aviso: micrófono ocupado tras reintentar. Continuando sin colgar.", flush=True)
        return None

    def _escuchar(self, corto=False):
        """Devuelve el texto, o None si nadie habló. Lanza RuntimeError si falla."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("Me falta instalar sounddevice y numpy.")

        rate = 16000
        bloque = int(rate * 0.1)
        trozos = []
        previo = deque(maxlen=3)
        hablo = False
        silencio = 0
        espera = 0
        try:
            with sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=bloque) as flujo:
                ambiente = []
                for _ in range(5):
                    datos, _ = flujo.read(bloque)
                    ambiente.append(float(np.abs(datos).mean()))
                umbral = max(200.0, (sum(ambiente) / len(ambiente)) * 3)
                while True:
                    datos, _ = flujo.read(bloque)
                    nivel = float(np.abs(datos).mean())
                    if nivel > umbral:
                        if not hablo:
                            trozos.extend(previo)
                        hablo = True
                        silencio = 0
                    elif hablo:
                        silencio += 1
                    else:
                        espera += 1
                        previo.append(datos.copy())
                    if hablo:
                        trozos.append(datos.copy())
                        if silencio >= 10 or len(trozos) > (40 if corto else 150):
                            break
                    elif espera >= 80:
                        break
        except Exception as e:
            raise RuntimeError("No pude usar el micrófono: " + str(e)[:120])

        if not hablo or len(trozos) < 5:
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        audio = np.concatenate(trozos)
        self.ultimo_audio = audio
        self.duracion_ultimo_audio = len(audio) / float(rate)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(audio.tobytes())
        r = None
        t0 = time.time()
        try:
            r = self.cliente.audio.transcriptions.create(
                file=("voz.wav", buffer.getvalue()),
                model=MODELO_VOZ,
                language="es",
                response_format="verbose_json",
                prompt=f"Conversación en español. Nombres: {self.vocabulario()}.",
                timeout=10.0,
            )
            print(f"[tiempo] whisper={time.time() - t0:.2f}s", flush=True)
        except Exception as e:
            print(f"[oido] Whisper falló ({str(e)[:80]}). Conmutando a Vosk...", flush=True)
            texto_vosk = self._transcribir_vosk(audio.tobytes())
            if texto_vosk is not None:
                return texto_vosk
            raise RuntimeError("No pude entender el audio: " + str(e)[:120])
        texto = (r.text or "").strip()
        if len(texto) < 2 or any(f in texto.lower() for f in FALSAS):
            return None
        if self._dudoso(r):
            return None
        return texto

    @staticmethod
    def _dudoso(r):
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