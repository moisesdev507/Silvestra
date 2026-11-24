import os
import re
import time
import threading
import numpy as np

import config
import oido_deepgram
import oido_filtro
from config import MODELO_VOZ
from oido_flujo import (
    CORTESIAS_AMBIGUAS,
    FALSAS,
    FlujoMicrofono,
    cortesia_descartada,
    crear_buffer_wav,
    es_bucle_alucinacion,
    es_cortesia_corta,
    es_transcripcion_dudosa,
    preparar_audio_int16,
    validar_calidad_whisper,
)
from oido_vad import DetectorVozSilero


# Solo nombres propios neutros: las listas de comandos/preguntas inducen bucles.
PROMPT_WHISPER = "Lyris, Visual Studio Code."


def _barge_in_habilitado():
    """Permite activarlo por config o por entorno sin tocar config.py."""
    return bool(getattr(config, "BARGE_IN_ACTIVO", False)
                or os.environ.get("LYRIS_BARGE_IN") == "1")


def _barge_in(app, datos, comandos_corte, rec_vosk):
    """Interrumpe solo ante una orden clara; ignora ruido y parciales vacíos."""
    if rec_vosk is None or not (app and hasattr(app, "voz") and app.voz.ocupada()):
        return False
    try:
        rec_vosk.AcceptWaveform(datos.tobytes())
        m = re.search(r'"partial"\s*:\s*"([^"]+)"', rec_vosk.PartialResult())
        if not m:
            return False
        limpio = re.sub(r"[^a-záéíóúñü\s]", " ", m.group(1).strip().lower())
        palabras = limpio.split()
        if len("".join(palabras)) < 2 or not any(c in palabras for c in comandos_corte):
            return False
        if hasattr(app.voz, "detener"):
            app.voz.detener()
        if hasattr(app, "cola"):
            app.cola.put(("interrupcion", "comando"))
        return True
    except Exception:
        return False


def _es_eco_prompt(texto_original, texto, prompt, ultimo_dicho=""):
    return oido_filtro.debe_descartar(texto_original, texto, prompt, ultimo_dicho)


def motivo_descarte_transcripcion(texto, rms, r=None):
    t_low = " ".join(str(texto or "").lower().split())
    if es_cortesia_corta(texto):
        if cortesia_descartada(texto, rms, r):
            return f"cortesia_sin_voz_clara(rms={float(rms or 0.0):.1f})"
        return None
    for f in FALSAS + CORTESIAS_AMBIGUAS:
        if f in t_low:
            return f"alucinacion_whisper('{f}')"
    return None


class Oido:
    def __init__(self, cliente, vocabulario):
        self.cliente = cliente
        self.vocabulario = vocabulario
        self.bloqueo = threading.RLock()
        self.debe_avisar_respaldo = False
        self.aviso_respaldo_dicho = False
        self._modelo_vosk = None
        self._reconocedor_vosk = None
        self.ultimo_audio = None
        self.duracion_ultimo_audio = 0.0
        self.t_fin_habla = time.time()
        self.t_texto = time.time()
        self._flujo = FlujoMicrofono(rate=16000, blocksize=int(16000 * 0.05))
        self._vad = DetectorVozSilero(sample_rate=16000)
        self._escuchando_activo = False

    def liberar_microfono(self):
        with self.bloqueo:
            self._flujo.liberar()

    def cerrar(self):
        self.liberar_microfono()

    def _obtener_reconocedor_vosk(self):
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

    @staticmethod
    def _sesion_vigente(app, generacion):
        return generacion is None or getattr(app, "_generacion_escucha", generacion) == generacion

    def escuchar(self, corto=False, app=None, generacion=None):
        while generacion is not None and self._sesion_vigente(app, generacion):
            adquirido = self.bloqueo.acquire(timeout=0.2)
            if not adquirido:
                continue
            try:
                self._escuchando_activo = True
                return self._escuchar(corto, app=app, generacion=generacion)
            finally:
                self._escuchando_activo = False
                self.bloqueo.release()
                time.sleep(0.05)
        if generacion is not None:
            return None
        for intento in range(2):
            adquirido = self.bloqueo.acquire(timeout=4.0)
            if not adquirido:
                print(f"[oido] Aviso: no pude adquirir el micrófono tras 4.0s (intento {intento + 1}/2). Reintentando...", flush=True)
                time.sleep(0.2)
                continue
            try:
                self._escuchando_activo = True
                return self._escuchar(corto, app=app)
            finally:
                self._escuchando_activo = False
                self.bloqueo.release()
                time.sleep(0.05)
        print("[oido] Aviso: micrófono ocupado tras reintentar. Continuando sin colgar.", flush=True)
        return None

    def _escuchar(self, corto=False, app=None, generacion=None):
        """Captura audio usando Silero VAD neuronal a 16 kHz y transcribe con Whisper/Vosk."""
        rate = 16000
        ganancia = float(getattr(config, "GANANCIA_MICROFONO", 1.2))
        comandos_corte = ("espera", "ya", "para", "silencio", "callate", "alto", "stop")
        rec_vosk = None

        tiempo_espera_max = 8.0 if not corto else 4.0
        max_habla_segundos = 15.0

        try:
            self._flujo.asegurar_flujo()

            # Anti-eco inteligente: guarda de ~350 ms solo cuando la voz de Silvestra estuvo activa
            hablaba_ella = False
            if app is not None and hasattr(app, "voz") and hasattr(app.voz, "ocupada"):
                while app.voz.ocupada() and self._sesion_vigente(app, generacion):
                    hablaba_ella = True
                    self._flujo.drenar()
                    time.sleep(0.04)

            if hablaba_ella:
                self._flujo.aplicar_guarda_antieco(bloques=7, pausa_inicial=0.35)
            else:
                self._flujo.drenar()

            self._vad.reset()
            t_inicio = time.time()
            self.t_captura_inicio = time.monotonic()
            t_habla_inicio = None
            hablo = False
            streamer = None

            while True:
                if not self._sesion_vigente(app, generacion):
                    return None
                ambiental = getattr(app, "invocacion_ambiental", False)
                if app is not None and not ambiental and (
                        not getattr(app, "escuchando", True)
                        or not getattr(app, "conversacion", True)):
                    break

                datos = self._flujo.leer(timeout=0.08)
                ahora = time.time()

                if datos is None:
                    if not hablo and (ahora - t_inicio >= tiempo_espera_max):
                        break
                    if hablo and t_habla_inicio and (ahora - t_habla_inicio >= max_habla_segundos):
                        self._vad.flush()
                        break
                    continue

                hablando_ella = bool(app and hasattr(app, "voz") and app.voz.ocupada())

                if hablando_ella:
                    if not _barge_in_habilitado():
                        time.sleep(0.01)
                        continue
                    if rec_vosk is None:
                        try:
                            rec_vosk = self._obtener_reconocedor_vosk()
                            rec_vosk.Reset()
                        except Exception:
                            rec_vosk = None
                    if _barge_in(app, datos, comandos_corte, rec_vosk):
                        continue

                self._vad.alimentar(datos)

                if not hablo:
                    if self._vad.detectando_voz():
                        hablo = True
                        t_habla_inicio = ahora
                        self.t_fin_habla = ahora
                        try:
                            import oido_stream
                            streamer = oido_stream.crear_streamer()
                        except Exception:
                            streamer = None
                    elif (ahora - t_inicio) >= tiempo_espera_max:
                        break
                else:
                    self.t_fin_habla = ahora
                    if streamer:
                        streamer.alimentar(datos)
                    if self._vad.hay_segmento_completo():
                        break
                    if t_habla_inicio and (ahora - t_habla_inicio >= max_habla_segundos):
                        self._vad.flush()
                        break

            if hablo and not self._vad.hay_segmento_completo():
                self._vad.flush()

        except Exception as e:
            raise RuntimeError("No pude usar el micrófono: " + str(e)[:120])

        if not self._sesion_vigente(app, generacion):
            return None
        self.t_fin_escucha = time.time()

        if not self._vad.hay_segmento_completo():
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        seg_float = self._vad.extraer_segmento()
        if seg_float is None or len(seg_float) == 0:
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        duracion = len(seg_float) / float(rate)
        audio_int16 = (np.clip(seg_float, -1.0, 1.0) * 32767.0).astype(np.int16)
        rms = float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2))) if len(audio_int16) > 0 else 0.0

        if duracion < 0.30:
            print(f"[oido] silero_segmento descartado: duracion={duracion:.2f}s < 0.30s rms={rms:.1f}", flush=True)
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        if rms < 60.0:
            print(f"[oido] silero_segmento descartado: rms={rms:.1f} < 60 (silencio digital)", flush=True)
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        print(f"[oido] silero_segmento={duracion:.2f}s rms={rms:.1f}", flush=True)
        audio = preparar_audio_int16(audio_int16, ganancia=ganancia)
        self.ultimo_audio = audio
        self.duracion_ultimo_audio = len(audio) / float(rate)
        buffer = crear_buffer_wav(audio, rate=rate)

        vocab_nombres = self.vocabulario() if callable(self.vocabulario) else ""
        extras = ", ".join(n.strip() for n in vocab_nombres.split(",")[:3]
                           if n.strip() and len(n.strip()) < 25
                           and n.strip().lower() not in PROMPT_WHISPER.lower())[:40]
        prompt_whisper = f"{PROMPT_WHISPER} {extras}".strip() if extras else PROMPT_WHISPER

        inv = getattr(app, "invocacion", None)
        if inv is not None and not inv.permitir():
            return None

        r = None
        t0 = time.time()
        dg = streamer.finalizar() if streamer else None
        if dg and str(dg[0] or "").strip():
            print("[oido] Deepgram stream WS valido", flush=True)
        else:
            dg = oido_deepgram.transcribir(buffer.getvalue())
            if dg and str(dg[0] or "").strip():
                print("[oido] Deepgram valido: sin Whisper", flush=True)
        if dg:
            texto = dg[0]
        else:
            try:
                r = self.cliente.audio.transcriptions.create(
                    file=("voz.wav", buffer.getvalue()),
                    model=MODELO_VOZ,
                    language="es",
                    response_format="verbose_json",
                    temperature=0.0,
                    prompt=prompt_whisper,
                    timeout=10.0,
                )
                print(f"[tiempo] whisper={time.time() - t0:.2f}s", flush=True)
            except Exception as e:
                print(f"[oido] Whisper falló ({str(e)[:80]}). Conmutando a Vosk...", flush=True)
                texto_vosk = self._transcribir_vosk(audio.tobytes())
                if texto_vosk is not None:
                    self.t_texto = time.time()
                    print(f"[oido] transcrito='{texto_vosk}'", flush=True)
                    return texto_vosk
                raise RuntimeError("No pude entender el audio: " + str(e)[:120])
            texto = (r.text or "").strip()

        texto_original = texto
        texto = oido_filtro.normalizar_transcripcion(texto)
        self.t_texto = time.time()
        if len(texto) < 3:
            print(f"[oido] transcripcion='{texto}' descartada motivo=demasiado_corta", flush=True)
            return None
        motivo = motivo_descarte_transcripcion(texto, rms, r)
        if motivo:
            print(f"[oido] transcripcion='{texto}' descartada motivo={motivo}", flush=True)
            return None
        if _es_eco_prompt(texto_original, texto, prompt_whisper,
                          getattr(app, "ultimo_dicho", "")):
            print(f"[oido] transcripcion='{texto}' descartada motivo=eco_prompt_o_repeticion", flush=True)
            return None
        valida, motivo_whisper = validar_calidad_whisper(r, texto)
        if not valida:
            print(f"[oido] transcripcion='{texto}' descartada motivo={motivo_whisper}", flush=True)
            return None
        if es_transcripcion_dudosa(r):
            print(f"[oido] transcripcion='{texto}' descartada motivo=dudoso_alta_probabilidad_sin_voz", flush=True)
            return None
        print(f"[oido] transcrito='{texto}'", flush=True)
        return texto
