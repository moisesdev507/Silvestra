import io
import re
import time
import threading
import wave
from collections import deque

import config
from config import MODELO_VOZ
from oido_flujo import FALSAS, FlujoMicrofono, es_transcripcion_dudosa, evaluar_clip_audio


class Oido:
    """Escucha el micrófono con VAD adaptativo y transcribe a texto con Whisper y Vosk."""

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
        self._escuchando_activo = False

    def liberar_microfono(self):
        """Pausa y libera el flujo persistente para procesos exclusivos (ej. calibración de voz)."""
        with self.bloqueo:
            self._flujo.liberar()

    def cerrar(self):
        """Cierre definitivo del flujo al apagar Silvestra."""
        self.liberar_microfono()

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
        if self._escuchando_activo:
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

    def _escuchar(self, corto=False, app=None):
        """Devuelve el texto, o None si nadie habló. VAD ágil con corte optimizado y flujo persistente."""
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("Me falta instalar numpy.")

        rate = 16000
        trozos = []
        previo = deque(maxlen=4)
        hablo = False
        silencio = 0
        espera = 0
        frames_voz = 0
        rec_vosk = None
        comandos_corte = ("espera", "ya", "para", "silencio", "callate", "alto", "stop")

        espera_silencio = float(getattr(config, "ESPERA_SILENCIO_SEGUNDOS", 0.55))
        max_silencio = max(7, int(espera_silencio / 0.05))
        vad_adaptativo = getattr(config, "VAD_ADAPTATIVO", True)
        max_silencio_adaptativo = max(8, int(0.45 / 0.05))
        ganancia = float(getattr(config, "GANANCIA_MICROFONO", 1.2))

        try:
            self._flujo.asegurar_flujo()

            # Esperar si la voz de Silvestra aún está sonando y drenar
            if app is not None and hasattr(app, "voz") and hasattr(app.voz, "ocupada"):
                while app.voz.ocupada():
                    self._flujo.drenar()
                    time.sleep(0.05)

            # Ventana de guarda anti-eco: descarta la reverberación y tail del parlante
            self._flujo.aplicar_guarda_antieco(bloques=9, pausa_inicial=0.40)

            ambiente = []
            intentos_amb = 0
            while len(ambiente) < 6 and intentos_amb < 20:
                intentos_amb += 1
                datos = self._flujo.leer(timeout=0.08)
                if datos is None:
                    continue
                ambiente.append(float(np.abs(datos).mean()))
            piso_ruido = sum(ambiente) / len(ambiente) if ambiente else 100.0
            umbral = max(180.0, piso_ruido * 2.6)

            idx_ultimo_habla = 0

            while True:
                if app is not None and (not getattr(app, "escuchando", True) or not getattr(app, "conversacion", True)):
                    break
                datos = self._flujo.leer(timeout=0.1)
                if datos is None:
                    espera += 1
                    if espera >= 160:
                        break
                    continue
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
                    frames_voz += 1
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
                    # Detección de fin de habla optimizada con VAD adaptativo
                    terminado = False
                    if silencio >= max_silencio:
                        terminado = True
                    elif (
                        vad_adaptativo
                        and len(trozos) >= 16
                        and silencio >= max_silencio_adaptativo
                        and nivel < (piso_ruido * 1.35)
                    ):
                        terminado = True
                    elif len(trozos) > (80 if corto else 300):
                        terminado = True
                    if terminado:
                        break
                elif espera >= 160:
                    break
        except Exception as e:
            raise RuntimeError("No pude usar el micrófono: " + str(e)[:120])

        self.t_fin_escucha = time.time()

        if not hablo:
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

        # Recortar silencios sobrantes finales
        trozos_utiles = trozos[: min(len(trozos), idx_ultimo_habla + 4)]

        # Filtro estricto anti-clips basura / eco antes de llamar a Whisper
        valido, dur_clip, rms_crudo, motivo = evaluar_clip_audio(trozos_utiles, frames_voz)
        if not valido:
            print(f"[oido] Clip descartado por corto/eco: {dur_clip:.2f}s rms={rms_crudo:.1f} ({motivo})", flush=True)
            self.ultimo_audio = None
            self.duracion_ultimo_audio = 0.0
            return None

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
                print(f"[oido] transcrito='{texto_vosk}'", flush=True)
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
        if es_transcripcion_dudosa(r):
            print(f"[oido] transcripcion='{texto}' descartada motivo=dudoso_alta_probabilidad_sin_voz", flush=True)
            return None
        print(f"[oido] transcrito='{texto}'", flush=True)
        return texto
