import io
import re
import time
import threading
import wave
from collections import deque

import config
from config import MODELO_VOZ

# Frases que Whisper inventa a veces cuando solo hay ruido.
FALSAS = (
    "conversacion informal", "conversación informal", "gracias por ver",
    "subtítulos", "subtitulos", "suscríbete", "suscribete", "amara.org",
    "haha", "jaja", "okay, okay", "ok, ok", "ya entendí", "ya entendi",
    "reproducción automática", "descarga gratuita", "todos los derechos",
    "muchas gracias", "hasta la próxima", "transcripción por",
)


class Oido:
    """Escucha el micrófono con VAD adaptativo y transcribe a texto con Whisper y Vosk."""

    def __init__(self, cliente, vocabulario):
        self.cliente = cliente
        self.vocabulario = vocabulario
        self.bloqueo = threading.Lock()
        self.debe_avisar_respaldo = False
        self.aviso_respaldo_dicho = False
        self._modelo_vosk = None
        self._reconocedor_vosk = None
        self.ultimo_audio = None
        self.duracion_ultimo_audio = 0.0
        self.t_fin_habla = time.time()
        self.t_texto = time.time()

    def _obtener_reconocedor_vosk(self):
        """Carga perezosa del modelo Vosk sin gramática restringida."""
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

    def escuchar(self, corto=False, app=None):
        for intento in range(2):
            adquirido = self.bloqueo.acquire(timeout=4.0)
            if not adquirido:
                print(f"[oido] Aviso: no pude adquirir el micrófono tras 4.0s (intento {intento + 1}/2). Reintentando...", flush=True)
                time.sleep(0.2)
                continue
            try:
                return self._escuchar(corto, app=app)
            finally:
                self.bloqueo.release()
        print("[oido] Aviso: micrófono ocupado tras reintentar. Continuando sin colgar.", flush=True)
        return None

    def _escuchar(self, corto=False, app=None):
        """Devuelve el texto, o None si nadie habló. VAD ágil con corte optimizado y normalización."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("Me falta instalar sounddevice y numpy.")

        rate = 16000
        # Bloques de 50 ms (800 muestras) para mayor precisión temporal
        bloque = int(rate * 0.05)
        trozos = []
        previo = deque(maxlen=4)
        hablo = False
        silencio = 0
        espera = 0
        rec_vosk = None
        comandos_corte = ("espera", "ya", "para", "silencio", "callate", "alto", "stop")

        espera_silencio = float(getattr(config, "ESPERA_SILENCIO_SEGUNDOS", 0.55))
        max_silencio = max(7, int(espera_silencio / 0.05))
        ganancia = float(getattr(config, "GANANCIA_MICROFONO", 1.2))

        try:
            with sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=bloque) as flujo:
                ambiente = []
                for _ in range(6):
                    datos, _ = flujo.read(bloque)
                    ambiente.append(float(np.abs(datos).mean()))
                piso_ruido = sum(ambiente) / len(ambiente)
                umbral = max(180.0, piso_ruido * 2.6)

                idx_ultimo_habla = 0

                while True:
                    datos, _ = flujo.read(bloque)
                    nivel = float(np.abs(datos).mean())
                    barge_in_habilitado = getattr(config, "BARGE_IN_ACTIVO", False)
                    hablando_ella = bool(app and hasattr(app, "voz") and app.voz.ocupada())

                    if hablando_ella:
                        if not barge_in_habilitado:
                            previo.clear()
                            trozos.clear()
                            hablo = False
                            silencio = 0
                            time.sleep(0.01)
                            continue

                        if rec_vosk is None:
                            try:
                                rec_vosk = self._obtener_reconocedor_vosk()
                                rec_vosk.Reset()
                            except Exception:
                                rec_vosk = None

                        if rec_vosk is not None:
                            try:
                                rec_vosk.AcceptWaveform(datos.tobytes())
                                parcial_raw = rec_vosk.PartialResult()
                                m = re.search(r'"partial"\s*:\s*"([^"]+)"', parcial_raw)
                                if m:
                                    palabras = m.group(1).strip().lower()
                                    if palabras:
                                        es_cmd = any(c in palabras.split() for c in comandos_corte)
                                        if es_cmd:
                                            motivo = "comando"
                                            t0_corte = time.time()
                                            if hasattr(app.voz, "detener"):
                                                app.voz.detener()
                                            dt_corte_ms = (time.time() - t0_corte) * 1000
                                            print(f"[interrupcion] motivo={motivo} tiempo_corte={dt_corte_ms:.1f}ms", flush=True)
                                            if hasattr(app, "cola"):
                                                app.cola.put(("interrupcion", motivo))
                                            if not hablo:
                                                trozos.extend(previo)
                                            hablo = True
                                            silencio = 0
                                            self.t_fin_habla = time.time()
                                            idx_ultimo_habla = len(trozos)
                            except Exception:
                                pass
                    elif nivel > umbral:
                        if not hablo:
                            trozos.extend(previo)
                        hablo = True
                        silencio = 0
                        self.t_fin_habla = time.time()
                        idx_ultimo_habla = len(trozos)
                    elif hablo:
                        silencio += 1
                    else:
                        espera += 1
                        previo.append(datos.copy())
                        # Actualización adaptativa suave del piso de ruido en reposo
                        piso_ruido = piso_ruido * 0.95 + nivel * 0.05
                        umbral = max(180.0, piso_ruido * 2.6)

                    if hablo:
                        trozos.append(datos.copy())
                        # Detección de fin de habla optimizada con parámetro configurable
                        if silencio >= max_silencio or len(trozos) > (80 if corto else 300):
                            break
                    elif espera >= 160:
                        break
        except Exception as e:
            raise RuntimeError("No pude usar el micrófono: " + str(e)[:120])

        self.t_fin_escucha = time.time()

        if not hablo or len(trozos) < 8:
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        # Recortar silencios sobrantes finales para no enviar audio muerto a Whisper
        trozos_utiles = trozos[: min(len(trozos), idx_ultimo_habla + 4)]
        audio_raw = np.concatenate(trozos_utiles)

        # Ganancia, supresión de offset DC y normalización de volumen a -3dBFS
        audio_f = audio_raw.astype(np.float32) * ganancia
        audio_f = audio_f - np.mean(audio_f)
        max_v = float(np.max(np.abs(audio_f)))
        if max_v > 50.0:
            escala = min(3.5, 24000.0 / max_v)
            audio_f = audio_f * escala
        audio = np.clip(audio_f, -32767, 32767).astype(np.int16)

        self.ultimo_audio = audio
        self.duracion_ultimo_audio = len(audio) / float(rate)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(audio.tobytes())

        vocab_nombres = self.vocabulario() if callable(self.vocabulario) else ""
        prompt_whisper = (
            f"Conversación en español de Panamá con Silvestra y Moisés. {vocab_nombres}. "
            "Comandos y acciones: silencio, para, cancelar, recordar, recordatorio, "
            "resumen, pantalla, cámara, hora, fecha, Telegram, YouTube, PC, laptop, código, Python, tareas."
        )

        r = None
        t0 = time.time()
        try:
            r = self.cliente.audio.transcriptions.create(
                file=("voz.wav", buffer.getvalue()),
                model=MODELO_VOZ,
                language="es",
                response_format="verbose_json",
                prompt=prompt_whisper,
                timeout=10.0,
            )
            print(f"[tiempo] whisper={time.time() - t0:.2f}s", flush=True)
        except Exception as e:
            print(f"[oido] Whisper falló ({str(e)[:80]}). Conmutando a Vosk...", flush=True)
            texto_vosk = self._transcribir_vosk(audio.tobytes())
            if texto_vosk is not None:
                self.t_texto = time.time()
                return texto_vosk
            raise RuntimeError("No pude entender el audio: " + str(e)[:120])

        self.t_texto = time.time()
        texto = (r.text or "").strip()
        if len(texto) < 3:
            print(f"[oido] transcripcion='{texto}' descartada motivo=demasiado_corta", flush=True)
            return None
        t_low = texto.lower()
        for f in FALSAS:
            if f in t_low:
                print(f"[oido] transcripcion='{texto}' descartada motivo=alucinacion_whisper('{f}')", flush=True)
                return None
        if self._dudoso(r):
            print(f"[oido] transcripcion='{texto}' descartada motivo=dudoso_alta_probabilidad_sin_voz", flush=True)
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
