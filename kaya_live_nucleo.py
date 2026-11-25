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
RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
TIMEOUT_SILENCIO_DEFECTO = 75.0


def obtener_api_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        try:
            import config
            key = getattr(config, "GEMINI_API_KEY", "") or getattr(config, "GOOGLE_API_KEY", "")
        except Exception:
            pass
    if not key and os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if linea.startswith("GEMINI_API_KEY="):
                        key = linea.split("=", 1)[1].strip("'\" ")
                        break
        except Exception:
            pass
    return str(key or "").strip()


def construir_instruccion_sistema():
    """Construye dinámicamente la instrucción de sistema con alma, actuación vocal y memoria."""
    base = "Eres Kaya, asistente personal panameña, cálida, ingeniosa, hablas en español natural con respuestas breves."
    ruta_alma = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta_alma):
        try:
            with open(ruta_alma, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    base = c
        except Exception:
            pass

    guia_vocal = (
        "\n\n[Guía de actuación vocal]\n"
        "- Hablas en español latinoamericano suave, cálido y cercano con acento panameño natural. "
        "Nunca uses acento de España ni tono de locutora formal.\n"
        "- Tu ritmo es ágil, relajado y fluido. Responde en 1 a 3 frases concisas y directas para que la charla no se vuelva monólogo.\n"
        "- Si ejecutas una herramienta (ver pantalla, buscar, etc.), confirma brevemente lo encontrado sin rodeos."
    )

    memoria_txt = ""
    try:
        import iniciativa_kaya
        res = iniciativa_kaya.resumen_compacto_temas()
        if res:
            memoria_txt = f"\n\n[Temas abiertos en memoria]:\n{res}"
    except Exception:
        pass

    return base + guia_vocal + memoria_txt


class SesionKayaLive:
    """Gestiona el ciclo de vida de una sesión interactiva Gemini Live."""

    def __init__(
        self,
        modelo: str = MODELO_DEFECTO,
        voz: str = VOZ_DEFECTO,
        timeout_silencio: float = TIMEOUT_SILENCIO_DEFECTO,
        on_transcripcion_usuario: Optional[Callable[[str], None]] = None,
        on_transcripcion_kaya: Optional[Callable[[str], None]] = None,
        on_estado_audio: Optional[Callable[[str], None]] = None,
    ):
        self.modelo = modelo
        self.voz = voz
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
        self._hilo_audio = None
        self._stream_entrada = None
        self._loop = None

    def actualizar_actividad(self):
        """Refresca la marca temporal del auto-reposo inteligente."""
        self._ultimo_contacto = time.monotonic()

    async def enviar_imagen_jpeg(self, jpeg_bytes: bytes):
        """Inyecta un fotograma JPEG en tiempo real a la sesión Live."""
        if self._session is not None and jpeg_bytes and len(jpeg_bytes) > 0:
            try:
                await self._session.send_realtime_input(
                    media=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
                )
            except Exception as e:
                print(f"[LIVE] Error inyectando imagen JPEG: {e}", flush=True)

    def _hilo_reproductor(self):
        stream = None
        try:
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    stream = sd.RawOutputStream(samplerate=RATE_SALIDA, channels=CHANNELS, dtype="int16", blocksize=960)
                    stream.start()
            except Exception:
                stream = sd.RawOutputStream(samplerate=RATE_SALIDA, channels=CHANNELS, dtype="int16", blocksize=960)
                stream.start()

            while not self._evento_parada.is_set():
                try:
                    trozo = self._cola_salida.get(timeout=0.04)
                except queue.Empty:
                    continue

                if trozo and len(trozo) > 0 and stream is not None and not stream.closed:
                    try:
                        stream.write(trozo)
                    except Exception:
                        pass
        except Exception as e:
            if not self._evento_parada.is_set():
                print(f"[LIVE] Error en reproductor: {e}", flush=True)
        finally:
            if stream is not None:
                try:
                    try:
                        import audio_lock
                        with audio_lock.bloqueo_portaudio():
                            if not stream.closed:
                                stream.stop()
                                stream.close()
                    except Exception:
                        if not stream.closed:
                            stream.stop()
                            stream.close()
                except Exception:
                    pass

    async def _captura_microfono(self):
        while not self._evento_parada_async.is_set():
            try:
                bloque = await asyncio.wait_for(self._cola_entrada.get(), timeout=0.1)
                if bloque and len(bloque) > 0:
                    self.actualizar_actividad()
                    await self._session.send_realtime_input(
                        media=types.Blob(data=bloque, mime_type="audio/pcm;rate=16000")
                    )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if not self._evento_parada_async.is_set():
                    print(f"[LIVE] Error en captura: {e}", flush=True)
                break

    async def _vigilante_silencio(self):
        """Cierra automáticamente la sesión para ahorro de cuota ($0) tras inactividad."""
        while not self._evento_parada_async.is_set():
            await asyncio.sleep(2.0)
            inactivo = time.monotonic() - self._ultimo_contacto
            if inactivo >= self.timeout_silencio:
                print(f"\n[LIVE] Auto-reposo inteligente activado ({int(inactivo)}s sin voz). Sesión cerrada para ahorro de cuota ($0).", flush=True)
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

                    # 1. Manejo de Tool Calls
                    if tc:
                        self.actualizar_actividad()
                        llamadas = getattr(tc, "function_calls", []) or []
                        respuestas = []
                        for call in llamadas:
                            c_id = getattr(call, "id", "")
                            c_name = getattr(call, "name", "")
                            c_args = getattr(call, "args", {}) or {}
                            print(f"\n[LIVE Tool] Ejecutando: {c_name}({c_args})", flush=True)
                            resultado = await kaya_live_tools.despachar_herramienta(c_name, c_args)
                            respuestas.append(types.FunctionResponse(id=c_id, name=c_name, response=resultado))
                        if respuestas:
                            await self._session.send_tool_response(function_responses=respuestas)
                        continue

                    if not sc:
                        continue

                    # 2. Interrupción nativa (barge-in)
                    if getattr(sc, "interrupted", False):
                        print("\n[LIVE] Interrumpida por el usuario (barge-in)", flush=True)
                        turno_hablando = False
                        while not self._cola_salida.empty():
                            try:
                                self._cola_salida.get_nowait()
                            except Exception:
                                break
                        continue

                    # 3. Transcripción de entrada (Usuario)
                    it = getattr(sc, "input_audio_transcription", None)
                    if it and getattr(it, "text", None):
                        self.actualizar_actividad()
                        txt_u = it.text.strip()
                        if self.on_transcripcion_usuario:
                            self.on_transcripcion_usuario(txt_u)
                        else:
                            print(f"\n[Tú]: {txt_u}", flush=True)

                    # 4. Transcripción de salida (Kaya)
                    ot = getattr(sc, "output_audio_transcription", None)
                    if ot and getattr(ot, "text", None):
                        self.actualizar_actividad()
                        txt_k = ot.text.strip()
                        if self.on_transcripcion_kaya:
                            self.on_transcripcion_kaya(txt_k)
                        else:
                            print(f"\n[Kaya]: {txt_k}", flush=True)

                    # 5. Audio de Kaya
                    mt = getattr(sc, "model_turn", None)
                    if mt:
                        for part in mt.parts:
                            if getattr(part, "thought", False):
                                continue
                            if part.text and not ot:
                                t_limpio = part.text.strip()
                                if t_limpio and not t_limpio.startswith("**"):
                                    if self.on_transcripcion_kaya:
                                        self.on_transcripcion_kaya(t_limpio)
                                    else:
                                        print(f"\n[Kaya]: {t_limpio}", flush=True)

                            if part.inline_data and part.inline_data.data:
                                self.actualizar_actividad()
                                if not turno_hablando:
                                    turno_hablando = True
                                    if self.on_estado_audio:
                                        self.on_estado_audio("reproduciendo")
                                    else:
                                        print("[LIVE] Reproduciendo audio...", flush=True)
                                self._cola_salida.put_nowait(part.inline_data.data)

                    if getattr(sc, "turn_complete", False):
                        turno_hablando = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._evento_parada_async.is_set():
                    print(f"\n[LIVE] Excepción en recepción: {e}", flush=True)
                    traceback.print_exc()
                    await asyncio.sleep(0.2)
                else:
                    break

    def detener(self):
        """Detiene de forma limpia y ordenada la sesión Live."""
        self._evento_parada.set()
        if self._evento_parada_async:
            self._evento_parada_async.set()

    async def ejecutar(self, solo_verificar: bool = False) -> bool:
        """Inicia la sesión Live conectando con Gemini Live y lanzando las tareas."""
        key = obtener_api_key()
        if not key:
            print("[LIVE] Error: No se encontró GEMINI_API_KEY.")
            return False

        client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})

        speech_cfg = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz)
            )
        )
        sys_instr = types.Content(parts=[types.Part.from_text(text=construir_instruccion_sistema())])

        cfg_kwargs = dict(
            response_modalities=[types.Modality.AUDIO],
            speech_config=speech_cfg,
            tools=kaya_live_tools.obtener_herramientas_live(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=sys_instr,
        )

        try:
            cfg = types.LiveConnectConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                **cfg_kwargs,
            )
        except Exception:
            cfg = types.LiveConnectConfig(**cfg_kwargs)

        if solo_verificar:
            print(f"[LIVE] Modo verificación: conectando con modelo '{self.modelo}' y voz '{self.voz}'...")
            async with client.aio.live.connect(model=self.modelo, config=cfg) as _:
                print("[LIVE] Conexión validada exitosamente con Gemini Live API y herramientas!")
                return True

        self._loop = asyncio.get_running_loop()
        self._cola_entrada = asyncio.Queue(maxsize=MAX_COLA_ENTRADA)
        self._evento_parada.clear()
        self._evento_parada_async = asyncio.Event()
        self.actualizar_actividad()

        self._hilo_audio = threading.Thread(target=self._hilo_reproductor, name="kaya-live-out", daemon=True)
        self._hilo_audio.start()

        muestras_bloque = int(RATE_ENTRADA * (CHUNK_ENTRADA_MS / 1000.0))

        def callback_entrada(indata, frames, time_info, status):
            if self._evento_parada.is_set():
                return
            try:
                datos = bytes(indata)
                if self._cola_entrada.full():
                    try:
                        self._cola_entrada.get_nowait()
                    except Exception:
                        pass
                self._loop.call_soon_threadsafe(self._cola_entrada.put_nowait, datos)
            except Exception:
                pass

        try:
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    self._stream_entrada = sd.RawInputStream(
                        samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=muestras_bloque, callback=callback_entrada
                    )
                    self._stream_entrada.start()
            except Exception:
                self._stream_entrada = sd.RawInputStream(
                    samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=muestras_bloque, callback=callback_entrada
                )
                self._stream_entrada.start()

            async with client.aio.live.connect(model=self.modelo, config=cfg) as session:
                self._session = session
                print(f"[LIVE] Sesión bidireccional activa (modelo={self.modelo}, voz={self.voz}). Kaya te escucha...", flush=True)
                tareas = [
                    asyncio.create_task(self._captura_microfono()),
                    asyncio.create_task(self._recepcion_servidor()),
                    asyncio.create_task(self._vigilante_silencio()),
                ]
                try:
                    await asyncio.gather(*tareas)
                except asyncio.CancelledError:
                    pass
                finally:
                    self.detener()
        finally:
            self.detener()
            if self._stream_entrada is not None:
                try:
                    try:
                        import audio_lock
                        with audio_lock.bloqueo_portaudio():
                            self._stream_entrada.stop()
                            self._stream_entrada.close()
                    except Exception:
                        self._stream_entrada.stop()
                        self._stream_entrada.close()
                except Exception:
                    pass
        return True
