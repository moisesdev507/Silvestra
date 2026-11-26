"""Núcleo modular de Kaya Live con Gemini Live API.

Voz oficial Achernar, audio bidireccional, soporte de tools, inyección de imágenes
y auto-reposo inteligente tras 75s de silencio para ahorro de cuota ($0).
"""
import asyncio
import os
import queue
import threading
import time
import traceback
from typing import Any, Callable, Optional
import sounddevice as sd
from google import genai
from google.genai import types
import kaya_live_tools

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = "Achernar"
RATE_ENTRADA, RATE_SALIDA, CHANNELS = 16000, 24000, 1
CHUNK_ENTRADA_MS, MAX_COLA_ENTRADA = 50, 60
TIMEOUT_SILENCIO_DEFECTO = 75.0


def obtener_api_key():
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not k:
        try:
            import config
            k = getattr(config, "GEMINI_API_KEY", "") or getattr(config, "GOOGLE_API_KEY", "")
        except Exception:
            pass
    if not k and os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for l in f:
                    if l.strip().startswith("GEMINI_API_KEY="):
                        k = l.split("=", 1)[1].strip("'\" \n")
                        break
        except Exception:
            pass
    return str(k or "").strip()


def construir_instruccion_sistema():
    base = "Eres Kaya, asistente personal panameña, cálida, ingeniosa, hablas en español natural con respuestas breves."
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    base = c
        except Exception:
            pass
    guia = (
        "\n\n[Guía de actuación vocal]\n"
        "- Hablas en español latinoamericano suave, cálido y cercano con acento panameño natural. Nunca uses acento de España ni tono de locutora formal.\n"
        "- Tu ritmo es ágil, relajado y fluido. Responde en 1 a 3 frases concisas y directas para que la charla no se vuelva monólogo.\n"
        "- Si ejecutas una herramienta (ver pantalla, buscar, etc.), confirma brevemente lo encontrado sin rodeos."
    )
    mem = ""
    try:
        import live_prompt
        mem = live_prompt.contexto_memoria()
    except Exception:
        pass
    return base + guia + mem


class SesionKayaLive:
    def __init__(self, modelo=MODELO_DEFECTO, voz=VOZ_DEFECTO, timeout_silencio=TIMEOUT_SILENCIO_DEFECTO,
                 on_transcripcion_usuario=None, on_transcripcion_kaya=None, on_estado_audio=None):
        self.modelo, self.voz = modelo, voz
        self.timeout_silencio = float(timeout_silencio)
        self.on_transcripcion_usuario = on_transcripcion_usuario
        self.on_transcripcion_kaya = on_transcripcion_kaya
        self.on_estado_audio = on_estado_audio
        self._session = None
        self._evento_parada = threading.Event()
        self._evento_parada_async = None
        self._cola_entrada = None
        self._cola_salida = queue.Queue(maxsize=300)
        self._ultimo_contacto = time.monotonic()
        self._hilo_audio, self._stream_entrada, self._loop = None, None, None

    def actualizar_actividad(self):
        self._ultimo_contacto = time.monotonic()

    async def enviar_imagen_jpeg(self, jpeg_bytes: bytes):
        if self._session and jpeg_bytes:
            try:
                await self._session.send_realtime_input(media=types.Blob(data=jpeg_bytes, mime_type="image/jpeg"))
            except Exception as e:
                print(f"[LIVE] Error imagen JPEG: {e}", flush=True)

    def _hilo_reproductor(self):
        st = None
        try:
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    st = sd.RawOutputStream(samplerate=RATE_SALIDA, channels=CHANNELS, dtype="int16", blocksize=960)
                    st.start()
            except Exception:
                st = sd.RawOutputStream(samplerate=RATE_SALIDA, channels=CHANNELS, dtype="int16", blocksize=960)
                st.start()
            while not self._evento_parada.is_set():
                try:
                    trozo = self._cola_salida.get(timeout=0.04)
                except queue.Empty:
                    continue
                if trozo and st and not st.closed:
                    try:
                        st.write(trozo)
                    except Exception:
                        pass
        except Exception as e:
            if not self._evento_parada.is_set():
                print(f"[LIVE] Error reproductor: {e}", flush=True)
        finally:
            if st:
                try:
                    import audio_lock
                    with audio_lock.bloqueo_portaudio():
                        if not st.closed:
                            st.stop()
                            st.close()
                except Exception:
                    try:
                        if not st.closed:
                            st.stop()
                            st.close()
                    except Exception:
                        pass

    async def _captura_microfono(self):
        while not self._evento_parada_async.is_set():
            try:
                b = await asyncio.wait_for(self._cola_entrada.get(), timeout=0.1)
                if b:
                    self.actualizar_actividad()
                    await self._session.send_realtime_input(media=types.Blob(data=b, mime_type="audio/pcm;rate=16000"))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if not self._evento_parada_async.is_set():
                    print(f"[LIVE] Error captura: {e}", flush=True)
                break

    async def _vigilante_silencio(self):
        while not self._evento_parada_async.is_set():
            await asyncio.sleep(2.0)
            inactivo = time.monotonic() - self._ultimo_contacto
            if inactivo >= self.timeout_silencio:
                print(f"\n[LIVE] Auto-reposo inteligente ({int(inactivo)}s sin voz). Sesión cerrada para ahorro de cuota ($0).", flush=True)
                self.detener()
                break

    async def _recepcion_servidor(self):
        turno_hablando = False
        while not self._evento_parada_async.is_set():
            try:
                async for resp in self._session.receive():
                    if self._evento_parada_async.is_set():
                        break
                    sc = getattr(resp, "server_content", None)
                    tc = getattr(resp, "tool_call", None)
                    if tc:
                        self.actualizar_actividad()
                        resps = []
                        for call in getattr(tc, "function_calls", []) or []:
                            cid, cname, cargs = getattr(call, "id", ""), getattr(call, "name", ""), getattr(call, "args", {}) or {}
                            print(f"\n[LIVE Tool] Ejecutando: {cname}({cargs})", flush=True)
                            res = await kaya_live_tools.despachar_herramienta(cname, cargs)
                            resps.append(types.FunctionResponse(id=cid, name=cname, response=res))
                        if resps:
                            await self._session.send_tool_response(function_responses=resps)
                        continue
                    if not sc:
                        continue
                    if getattr(sc, "interrupted", False):
                        print("\n[LIVE] Interrumpida por el usuario (barge-in)", flush=True)
                        turno_hablando = False
                        while not self._cola_salida.empty():
                            try:
                                self._cola_salida.get_nowait()
                            except Exception:
                                break
                        continue
                    it = getattr(sc, "input_audio_transcription", None)
                    if it and getattr(it, "text", None):
                        self.actualizar_actividad()
                        t = it.text.strip()
                        if self.on_transcripcion_usuario:
                            self.on_transcripcion_usuario(t)
                        else:
                            print(f"\n[Tú]: {t}", flush=True)
                    ot = getattr(sc, "output_audio_transcription", None)
                    if ot and getattr(ot, "text", None):
                        self.actualizar_actividad()
                        t = ot.text.strip()
                        if self.on_transcripcion_kaya:
                            self.on_transcripcion_kaya(t)
                        else:
                            print(f"\n[Kaya]: {t}", flush=True)
                    mt = getattr(sc, "model_turn", None)
                    if mt:
                        for p in mt.parts:
                            if getattr(p, "thought", False):
                                continue
                            if p.text and not ot:
                                t = p.text.strip()
                                if t and not t.startswith("**"):
                                    if self.on_transcripcion_kaya:
                                        self.on_transcripcion_kaya(t)
                                    else:
                                        print(f"\n[Kaya]: {t}", flush=True)
                            if p.inline_data and p.inline_data.data:
                                self.actualizar_actividad()
                                if not turno_hablando:
                                    turno_hablando = True
                                    if self.on_estado_audio:
                                        self.on_estado_audio("reproduciendo")
                                    else:
                                        print("[LIVE] Reproduciendo audio...", flush=True)
                                self._cola_salida.put_nowait(p.inline_data.data)
                    if getattr(sc, "turn_complete", False):
                        turno_hablando = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._evento_parada_async.is_set():
                    print(f"\n[LIVE] Error recepción: {e}", flush=True)
                    await asyncio.sleep(0.2)
                else:
                    break

    def detener(self):
        self._evento_parada.set()
        if self._evento_parada_async:
            self._evento_parada_async.set()

    async def ejecutar(self, solo_verificar=False):
        key = obtener_api_key()
        if not key:
            print("[LIVE] Error: No se encontró GEMINI_API_KEY.")
            return False
        cli = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
        sp = types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz)))
        sys_i = types.Content(parts=[types.Part.from_text(text=construir_instruccion_sistema())])
        cfg_k = dict(
            response_modalities=[types.Modality.AUDIO],
            speech_config=sp,
            tools=kaya_live_tools.obtener_herramientas_live(),
            system_instruction=sys_i,
        )
        try:
            import live_audio
            cfg_k.update(live_audio.configuracion_transcripcion())
        except Exception:
            cfg_k.update(
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            )
        try:
            cfg = types.LiveConnectConfig(thinking_config=types.ThinkingConfig(thinking_budget=0), **cfg_k)
        except Exception:
            cfg = types.LiveConnectConfig(**cfg_k)

        if solo_verificar:
            print(f"[LIVE] Modo verificación: conectando con modelo '{self.modelo}' y voz '{self.voz}'...")
            async with cli.aio.live.connect(model=self.modelo, config=cfg) as _:
                print("[LIVE] Conexión validada exitosamente con Gemini Live API y herramientas!")
                return True

        self._loop = asyncio.get_running_loop()
        self._cola_entrada = asyncio.Queue(maxsize=MAX_COLA_ENTRADA)
        self._evento_parada.clear()
        self._evento_parada_async = asyncio.Event()
        self.actualizar_actividad()
        self._hilo_audio = threading.Thread(target=self._hilo_reproductor, name="kaya-live-out", daemon=True)
        self._hilo_audio.start()
        n_m = int(RATE_ENTRADA * (CHUNK_ENTRADA_MS / 1000.0))

        def cb_in(indata, frames, ti, status):
            if self._evento_parada.is_set():
                return
            try:
                d = bytes(indata)
                if self._cola_entrada.full():
                    try:
                        self._cola_entrada.get_nowait()
                    except Exception:
                        pass
                self._loop.call_soon_threadsafe(self._cola_entrada.put_nowait, d)
            except Exception:
                pass

        try:
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    self._stream_entrada = sd.RawInputStream(samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=n_m, callback=cb_in)
                    self._stream_entrada.start()
            except Exception:
                self._stream_entrada = sd.RawInputStream(samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=n_m, callback=cb_in)
                self._stream_entrada.start()

            async with cli.aio.live.connect(model=self.modelo, config=cfg) as s:
                self._session = s
                print(f"[LIVE] Sesión bidireccional activa (modelo={self.modelo}, voz={self.voz}). Kaya te escucha...", flush=True)
                tareas = [asyncio.create_task(self._captura_microfono()), asyncio.create_task(self._recepcion_servidor()), asyncio.create_task(self._vigilante_silencio())]
                try:
                    await asyncio.gather(*tareas)
                except asyncio.CancelledError:
                    pass
                finally:
                    self.detener()
        finally:
            self.detener()
            if self._stream_entrada:
                try:
                    import audio_lock
                    with audio_lock.bloqueo_portaudio():
                        self._stream_entrada.stop()
                        self._stream_entrada.close()
                except Exception:
                    try:
                        self._stream_entrada.stop()
                        self._stream_entrada.close()
                    except Exception:
                        pass
        return True
