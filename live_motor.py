"""Motor de sesión interactiva de Gemini Live para Silvestra."""
import asyncio
import os
import queue
import threading
import time
from typing import Any, Callable, Optional
import sounddevice as sd
from google import genai
from google.genai import types
import live_audio
import live_herramientas

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = "Achernar"

from live_audio import (
    _DISYUNTOR_HASTA, _LOCK_DISYUNTOR, activar_enfriamiento_cuota,
    es_error_cuota, esta_en_enfriamiento_cuota,
)


class SesionKayaLive:
    def __init__(
        self,
        modelo: str = MODELO_DEFECTO,
        voz: str = VOZ_DEFECTO,
        timeout_silencio: float = live_audio.TIMEOUT_SILENCIO_DEFECTO,
        on_estado: Optional[Callable[[str], None]] = None,
        on_nivel_voz: Optional[Callable[[float], None]] = None,
        on_transcripcion: Optional[Callable[[str, str], None]] = None,
        on_cierre_automatico: Optional[Callable[[], None]] = None,
        orden_inicial: str = "",
    ):
        self.modelo, self.voz = modelo, voz
        self.timeout_silencio = timeout_silencio
        self.on_estado, self.on_nivel_voz = on_estado, on_nivel_voz
        self.on_transcripcion, self.on_cierre_automatico = on_transcripcion, on_cierre_automatico
        self.orden_inicial = orden_inicial

        self.cola_audio_entrada = queue.Queue(maxsize=live_audio.MAX_COLA_ENTRADA)
        self.cola_audio_salida = queue.Queue()
        self.compuerta = live_audio.CompuertaAntiEco(cola_salida=self.cola_audio_salida)

        self.activo = False
        self._loop, self._session_genai = None, None
        self._hilo_loop, self._hilo_salida = None, None
        self._stream_entrada, self._stream_salida = None, None
        self._rate_entrada = live_audio.RATE_ENTRADA
        self._t_ultimo_log_voz = 0.0
        self._en_rafaga_voz = False

        self._t_ultima_voz = time.monotonic()
        self._estado_actual = "reposo"
        self._candado = threading.RLock()

    def _notificar_estado(self, estado: str):
        with self._candado:
            self._estado_actual = estado
        if callable(self.on_estado):
            try:
                self.on_estado(estado)
            except Exception:
                pass

    def _notificar_nivel(self, nivel: float):
        if callable(self.on_nivel_voz):
            try:
                self.on_nivel_voz(nivel)
            except Exception:
                pass

    def _notificar_texto(self, rol: str, texto: str):
        if callable(self.on_transcripcion):
            try:
                self.on_transcripcion(rol, texto)
            except Exception:
                pass

    def _callback_audio_in(self, indata, frames, time_info, status):
        if not self.activo:
            return
        pcm = bytes(indata)
        if self._rate_entrada != live_audio.RATE_ENTRADA:
            pcm = live_audio.remuestrear_pcm16_a_16k(pcm, self._rate_entrada)
        chunk_filtrado, silenciado = self.compuerta.filtrar_chunk_entrada(pcm)
        if not silenciado:
            es_habla, rms, energia = live_audio.es_voz_activa(chunk_filtrado)
            if es_habla:
                self._t_ultima_voz = time.monotonic()
                if self._estado_actual != "hablando":
                    self._notificar_estado("escuchando")
                self._notificar_nivel(energia)
                ahora = time.monotonic()
                if not getattr(self, "_en_rafaga_voz", False) or (ahora - getattr(self, "_t_ultimo_log_voz", 0.0) >= 1.2):
                    self._en_rafaga_voz = True
                    self._t_ultimo_log_voz = ahora
                    print(f"[LIVE][AUDIO] Voz detectada (rms={rms:.1f}, nivel={energia:.2f}).", flush=True)
            elif getattr(self, "_en_rafaga_voz", False):
                self._en_rafaga_voz = False
        try:
            self.cola_audio_entrada.put_nowait(chunk_filtrado)
        except queue.Full:
            pass

    def _bucle_reproduccion_salida(self):
        """Hilo dedicado a reproducir chunks PCM a 24kHz en los parlantes."""
        try:
            self._stream_salida = sd.OutputStream(
                samplerate=live_audio.RATE_SALIDA,
                channels=live_audio.CHANNELS,
                dtype="int16",
            )
            self._stream_salida.start()
        except Exception as e:
            print(f"[LIVE][AUDIO] Error iniciando stream salida: {e}", flush=True)
            return

        while self.activo:
            try:
                chunk = self.cola_audio_salida.get(timeout=0.1)
            except queue.Empty:
                if self._estado_actual == "hablando" and not self.compuerta.esta_en_ventana_eco():
                    self._notificar_estado("escuchando")
                    self._t_ultima_voz = time.monotonic()
                continue

            if not chunk:
                continue

            self._notificar_estado("hablando")
            energia = live_audio.calcular_energia_pcm16(chunk)
            self._notificar_nivel(energia)

            self.compuerta.marcar_inicio_escritura()
            try:
                import numpy as np
                self._stream_salida.write(np.frombuffer(chunk, dtype=np.int16))
            except Exception as err:
                print(f"[LIVE][AUDIO] Error salida: {err}", flush=True)
            finally:
                self.compuerta.marcar_fin_escritura()

        if self._stream_salida:
            try:
                self._stream_salida.stop()
                self._stream_salida.close()
            except Exception:
                pass

    async def _tarea_envio_audio(self, session):
        while self.activo:
            try:
                data = await asyncio.to_thread(self.cola_audio_entrada.get, timeout=0.1)
                if data:
                    await session.send_realtime_input(
                        media=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
            except queue.Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"[LIVE][AUDIO] Error enviando audio a Gemini: {e}", flush=True)
                break

    async def _tarea_watchdog(self):
        """Cierra sesión si pasan timeout_silencio segundos (9s) sin voz."""
        while self.activo:
            await asyncio.sleep(0.5)
            if self._estado_actual == "hablando":
                self._t_ultima_voz = time.monotonic()
                continue
            silencio = time.monotonic() - self._t_ultima_voz
            if silencio >= self.timeout_silencio:
                print(f"[LIVE] Watchdog de silencio ({self.timeout_silencio:.1f}s) alcanzado. Cerrando sesión.", flush=True)
                self.detener()
                if callable(self.on_cierre_automatico):
                    try:
                        self.on_cierre_automatico()
                    except Exception:
                        pass
                break

    async def _ejecutar_sesion(self):
        api_key = live_audio.obtener_api_key()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY no configurada")

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        cfg = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz))
            ),
            system_instruction=types.Content(parts=[types.Part.from_text(text=live_audio.construir_instruccion_sistema())]),
            tools=live_herramientas.declarar_declaraciones_herramientas(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(silence_duration_ms=700)
            ),
        )

        self._notificar_estado("conectando")
        live_herramientas.registrar_callback_reposo(self.detener)

        async with client.aio.live.connect(model=self.modelo, config=cfg) as session:
            self._session_genai = session
            self._notificar_estado("escuchando")
            self._t_ultima_voz = time.monotonic()

            orden = (self.orden_inicial or "").strip()
            if orden and orden.lower() not in ("kaya", "kaia", "silvestra", "oye kaya"):
                texto_inicio = orden
            else:
                texto_inicio = "Hola Kaya, dime, ¿estás ahí?"

            try:
                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=texto_inicio)]
                    ),
                    turn_complete=True
                )
            except Exception as e:
                print(f"[LIVE] Error enviando orden inicial: {e}", flush=True)

            tarea_audio = asyncio.create_task(self._tarea_envio_audio(session))
            tarea_dog = asyncio.create_task(self._tarea_watchdog())

            try:
                while self.activo:
                    async for resp in session.receive():
                        if not self.activo:
                            break

                        sc = resp.server_content
                        if sc:
                            if getattr(sc, "turn_complete", False):
                                self._t_ultima_voz = time.monotonic()
                            if getattr(sc, "interrupted", False):
                                with self.cola_audio_salida.mutex:
                                    self.cola_audio_salida.queue.clear()
                                self._notificar_estado("escuchando")
                                self._t_ultima_voz = time.monotonic()

                            mt = sc.model_turn
                            if mt:
                                for part in mt.parts:
                                    if getattr(part, "inline_data", None) and part.inline_data.data:
                                        self.compuerta.marcar_encolado_salida()
                                        self.cola_audio_salida.put(part.inline_data.data)
                                    if getattr(part, "text", None):
                                        self._notificar_texto("kaya", part.text)

                        tc = resp.tool_call
                        if tc:
                            self._notificar_estado("pensando")
                            for call in tc.function_calls:
                                res_call = await live_herramientas.despachar_herramienta_asincrona(call.name, call.args)
                                await session.send(
                                    input=types.LiveClientToolResponse(
                                        function_responses=[
                                            types.FunctionResponse(name=call.name, id=call.id, response={"result": res_call})
                                        ]
                                    )
                                )
                    if not self.activo:
                        break
                    await asyncio.sleep(0.02)
            finally:
                tarea_audio.cancel()
                tarea_dog.cancel()

    def iniciar(self) -> bool:
        """Inicia la sesión Live en un hilo independiente."""
        if esta_en_enfriamiento_cuota():
            print("[LIVE] Enfriamiento de cuota activo. Omitiendo arranque de Live.", flush=True)
            return False

        if self.activo:
            return True

        self.activo = True
        self.compuerta.registrar_info_inicio()

        try:
            self._stream_entrada, self._rate_entrada = live_audio.crear_input_stream(self._callback_audio_in)
        except Exception as e:
            print(f"[LIVE][AUDIO] Error iniciando micrófono: {e}", flush=True)
            self.detener()
            return False

        self._hilo_salida = threading.Thread(target=self._bucle_reproduccion_salida, daemon=True, name="live-audio-out")
        self._hilo_salida.start()

        def _correr_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._ejecutar_sesion())
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if es_error_cuota(e):
                    activar_enfriamiento_cuota(15.0)
                print(f"[LIVE] Sesión finalizada o error: {e}", flush=True)
            finally:
                try:
                    pendientes = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
                    for t in pendientes:
                        t.cancel()
                    if pendientes:
                        self._loop.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
                    self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                except Exception:
                    pass
                finally:
                    try:
                        self._loop.close()
                    except Exception:
                        pass
                    self._loop = None
                    self._session_genai = None

        self._hilo_loop = threading.Thread(target=_correr_loop, daemon=True, name="live-ws-loop")
        self._hilo_loop.start()
        return True

    def enviar_texto(self, texto: str) -> bool:
        """Envía un mensaje de texto a la sesión Live activa."""
        if not self.activo or not self._loop or not self._session_genai:
            return False
        def _enviar():
            try:
                asyncio.create_task(
                    self._session_genai.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part.from_text(text=str(texto))]),
                        turn_complete=True,
                    )
                )
            except Exception as err:
                print(f"[LIVE] Error enviando texto: {err}", flush=True)
        try:
            self._loop.call_soon_threadsafe(_enviar)
            return True
        except Exception:
            return False

    def detener(self):
        """Detiene limpiamente la sesión y cancela tareas pendientes sin romper el loop."""
        if not self.activo:
            return
        self.activo = False
        self._notificar_estado("reposo")

        if self._stream_entrada:
            try:
                self._stream_entrada.stop()
                self._stream_entrada.close()
            except Exception:
                pass
            self._stream_entrada = None

        if self._loop and self._loop.is_running():
            try:
                def _cancelar_todas():
                    for t in asyncio.all_tasks(self._loop):
                        t.cancel()
                self._loop.call_soon_threadsafe(_cancelar_todas)
            except Exception:
                pass
