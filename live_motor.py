"""Motor interactivo Gemini Live para Silvestra con puente WebRTC y respaldo PortAudio."""
import asyncio, queue, threading, time
from datetime import datetime
from typing import Callable, Optional
from google import genai
from google.genai import types
import despertar_local, identidad_origen, json, os
import live_audio, live_herramientas, live_webrtc, puerta_audio_live

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = identidad_origen.VOZ_KAYA_LIVE
from live_audio import activar_enfriamiento_cuota, es_error_cuota, esta_en_enfriamiento_cuota


_DIAS_ES = ("lunes", "martes", "mi?rcoles", "jueves", "viernes", "s?bado", "domingo")
_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _instruccion_con_hora_local(rapido: bool, primer_despertar: bool, nombre_usuario: str) -> str:
    base = live_audio.construir_instruccion_sistema(
        rapido=rapido, primer_despertar=primer_despertar, nombre_usuario=nombre_usuario
    )
    ahora = datetime.now()
    fecha_local = f"{_DIAS_ES[ahora.weekday()]} {ahora.day} de {_MESES_ES[ahora.month - 1]} de {ahora.year}, {ahora.strftime('%H:%M')}"
    return f"{base}\nFecha y hora local actual del usuario: {fecha_local} (usa siempre esta fecha y hora local, nunca UTC)."


def _crear_reconocedor_kaya():
    ruta = despertar_local.ruta_modelo_vosk()
    if not os.path.isdir(ruta):
        return None
    try:
        import vosk
        vosk.SetLogLevel(-1)
        gramatica = json.dumps(["kaya", "kaia", "calla", "oye kaya", "hola kaya", "[unk]"], ensure_ascii=False)
        return vosk.KaldiRecognizer(vosk.Model(ruta), 16000, gramatica)
    except Exception as e:
        print(f"[LIVE][WAKE] Aviso Vosk: {e}", flush=True)
        return None


def _detecto_kaya_en_chunk(rec, pcm: bytes) -> bool:
    if rec is None or not pcm:
        return False
    try:
        hecho = rec.AcceptWaveForm(pcm)
        raw = rec.Result() if hecho else rec.PartialResult()
        data = json.loads(raw or "{}")
        txt = data.get("text") or data.get("partial") or ""
        return despertar_local.contiene_kaya(txt)
    except Exception:
        return False


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
        t_sil = float(timeout_silencio or live_audio.TIMEOUT_SILENCIO_DEFECTO)
        self.timeout_silencio = t_sil if t_sil >= 2.0 else live_audio.TIMEOUT_SILENCIO_DEFECTO
        self.on_estado, self.on_nivel_voz = on_estado, on_nivel_voz
        self.on_transcripcion, self.on_cierre_automatico = on_transcripcion, on_cierre_automatico
        self.orden_inicial = orden_inicial

        self.cola_audio_entrada = queue.Queue(maxsize=live_audio.MAX_COLA_ENTRADA)
        self.cola_audio_salida = queue.Queue()
        self.compuerta = live_audio.CompuertaAntiEco(cola_salida=self.cola_audio_salida)
        self.puerta = puerta_audio_live.PuertaAudioLive(timeout_silencio=self.timeout_silencio)

        self.activo = False
        self._puente_webrtc: Optional[live_webrtc.PuenteWebRTC] = None
        self._loop, self._session_genai = None, None
        self._hilo_loop, self._hilo_salida = None, None
        self._stream_entrada, self._stream_salida = None, None
        self._rate_entrada = live_audio.RATE_ENTRADA
        self._t_ultimo_log_voz, self._en_rafaga_voz = 0.0, False
        self._estado_actual, self._candado = "reposo", threading.RLock()

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
        chunk, silenciado = self.compuerta.filtrar_chunk_entrada(pcm)
        if silenciado or not puerta_audio_live.encolar_autorizados(
                self.puerta, chunk, self.cola_audio_entrada):
            return
        self._notificar_estado("escuchando")
        self._notificar_nivel(live_audio.calcular_energia_pcm16(chunk))
        ahora = time.monotonic()
        if not self._en_rafaga_voz or ahora - self._t_ultimo_log_voz >= 1.5:
            self._en_rafaga_voz, self._t_ultimo_log_voz = True, ahora
            print("[LIVE][AUDIO] Gate local abierto por voz.", flush=True)

    def _bucle_reproduccion_salida(self):
        try:
            self._stream_salida = live_audio.crear_output_stream()
        except Exception as e:
            print(f"[LIVE][AUDIO] Error iniciando stream salida: {e}", flush=True)
            return

        try:
            while self.activo:
                try:
                    chunk = self.cola_audio_salida.get(timeout=0.1)
                except queue.Empty:
                    self.puerta.marcar_reproduccion(False)
                    if self._estado_actual == "hablando" and not self.compuerta.esta_en_ventana_eco():
                        self._notificar_estado("escuchando")
                    continue
                if not chunk:
                    continue
                self._notificar_estado("hablando")
                self._notificar_nivel(live_audio.calcular_energia_pcm16(chunk))
                self.puerta.marcar_reproduccion(True)
                self.compuerta.marcar_inicio_escritura()
                try:
                    import numpy as np
                    if self.activo and self._stream_salida:
                        self._stream_salida.write(np.frombuffer(chunk, dtype=np.int16))
                except Exception as err:
                    print(f"[LIVE][AUDIO] Error salida: {err}", flush=True)
                finally:
                    self.compuerta.marcar_fin_escritura()
                    if self.cola_audio_salida.empty():
                        self.puerta.marcar_reproduccion(False)
        finally:
            self._stream_salida = live_audio.cerrar_stream(self._stream_salida)

    async def _tarea_envio_audio(self, session):
        puente = self._puente_webrtc
        cola = puente.cola_entrada if puente is not None else self.cola_audio_entrada
        rec_wake = await asyncio.to_thread(_crear_reconocedor_kaya) if puente is not None else None
        while self.activo:
            try:
                data = await asyncio.to_thread(cola.get, timeout=0.1)
                if not data:
                    continue
                if puente is not None:
                    if data == live_webrtc.SENAL_SLEEP:
                        if rec_wake is not None:
                            try:
                                rec_wake.Reset()
                            except Exception:
                                pass
                        try:
                            await session.send_realtime_input(audio_stream_end=True)
                        except Exception:
                            pass
                        continue
                    if puente.dormida:
                        if rec_wake is None or _detecto_kaya_en_chunk(rec_wake, data):
                            print("[LIVE][WAKE] 'Kaya' detectada -> despertando a Amarillo.", flush=True)
                            puente.dormida = False
                            puente.despertar()
                            if rec_wake is not None:
                                try:
                                    rec_wake.Reset()
                                except Exception:
                                    pass
                        continue
                elif self.puerta.reproduciendo or self.compuerta.esta_en_ventana_eco():
                    continue
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                )
            except queue.Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"[LIVE][AUDIO] Error enviando audio a Gemini: {e}", flush=True)
                break

    async def _tarea_watchdog(self):
        if self._puente_webrtc is not None:
            while self.activo:
                await asyncio.sleep(1.0)
            return
        while self.activo:
            await asyncio.sleep(0.5)
            if self.puerta.debe_cerrar():
                print(f"[LIVE] Inactividad {self.timeout_silencio:.1f}s: cerrando micr?fono y Live.", flush=True)
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
            return
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        despertar = identidad_origen.consumir_primer_despertar()
        nombre_actual = identidad_origen.nombre_usuario()
        rapido = bool(self.orden_inicial and ("enciende" in self.orden_inicial or "encendi?" in self.orden_inicial))
        cfg = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz))
            ),
            system_instruction=types.Content(parts=[types.Part.from_text(text=_instruccion_con_hora_local(rapido, despertar, nombre_actual))]),
            tools=live_herramientas.declarar_declaraciones_herramientas(),
        )

        self._notificar_estado("conectando")
        live_herramientas.registrar_callback_reposo(self.detener)
        primer_ciclo = True

        while self.activo:
            try:
                async with client.aio.live.connect(model=self.modelo, config=cfg) as session:
                    self._session_genai = session
                    if not (self._puente_webrtc and self._puente_webrtc.dormida):
                        self._notificar_estado("escuchando")
                    self.puerta.notificar_actividad()

                    if primer_ciclo:
                        primer_ciclo = False
                        orden = (self.orden_inicial or "").strip()
                        if despertar:
                            texto_inicio = identidad_origen.instruccion_primer_despertar(nombre_actual)
                        elif orden:
                            texto_inicio = orden if orden.lower() not in ("kaya", "kaia", "silvestra", "oye kaya") else ""
                        else:
                            texto_inicio = ""
                        if texto_inicio:
                            try:
                                await session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part.from_text(text=texto_inicio)]),
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"[LIVE] Error enviando orden inicial: {e}", flush=True)

                    tarea_audio = asyncio.create_task(self._tarea_envio_audio(session))
                    tarea_dog = asyncio.create_task(self._tarea_watchdog())
                    try:
                        async for resp in session.receive():
                            if not self.activo:
                                break
                            sc = resp.server_content
                            if sc:
                                if getattr(sc, "turn_complete", False):
                                    self.puerta.notificar_actividad()
                                if getattr(sc, "interrupted", False):
                                    if self._puente_webrtc is not None:
                                        self._puente_webrtc.interrumpir_salida()
                                    else:
                                        with self.cola_audio_salida.mutex:
                                            self.cola_audio_salida.queue.clear()
                                        self._notificar_estado("escuchando")
                                    self.puerta.notificar_actividad()
                                mt = sc.model_turn
                                if mt:
                                    for part in mt.parts:
                                        if getattr(part, "inline_data", None) and part.inline_data.data:
                                            live_audio.registrar_tiempo_primera_voz()
                                            if self._puente_webrtc is not None:
                                                self._puente_webrtc.enviar_audio_salida(part.inline_data.data)
                                            else:
                                                self.compuerta.marcar_encolado_salida()
                                                self.cola_audio_salida.put(part.inline_data.data)
                                        if getattr(part, "text", None):
                                            self._notificar_texto("kaya", part.text)
                            tc = resp.tool_call
                            if tc:
                                self._notificar_estado("pensando")
                                self.puerta.notificar_actividad()
                                for call in tc.function_calls:
                                    res_call = await live_herramientas.despachar_herramienta_asincrona(call.name, call.args)
                                    resp_tool = types.LiveClientToolResponse(
                                        function_responses=[types.FunctionResponse(name=call.name, id=call.id, response={"result": res_call})]
                                    )
                                    await session.send(input=resp_tool)
                    finally:
                        tarea_audio.cancel()
                        tarea_dog.cancel()
                if not self.activo:
                    break
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.activo or es_error_cuota(e):
                    raise
                print(f"[LIVE][WEBRTC] Reconectando sesi?n Live: {e}", flush=True)
                await asyncio.sleep(0.8)

    def iniciar(self) -> bool:
        if esta_en_enfriamiento_cuota():
            print("[LIVE] Enfriamiento de cuota activo. Omitiendo arranque de Live.", flush=True)
            return False
        if self.activo:
            return True
        self.activo = True
        self.compuerta.registrar_info_inicio()
        self.puerta.reiniciar()
        with self.cola_audio_entrada.mutex:
            self.cola_audio_entrada.queue.clear()

        puente = live_webrtc.PuenteWebRTC(on_estado=self._notificar_estado, on_nivel=self._notificar_nivel)
        if puente.iniciar():
            self._puente_webrtc = puente
        else:
            try:
                self._stream_entrada, self._rate_entrada = live_audio.crear_input_stream(self._callback_audio_in)
            except Exception as e:
                print(f"[LIVE][AUDIO] Error iniciando micr?fono: {e}", flush=True)
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
                print(f"[LIVE] Sesi?n finalizada o error: {e}", flush=True)
            finally:
                self.detener()
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
        if not self.activo:
            return
        self.activo = False
        self.puerta.desactivar()
        self._notificar_estado("reposo")
        if self._puente_webrtc is not None:
            try:
                self._puente_webrtc.detener()
            except Exception:
                pass
            self._puente_webrtc = None
        self._stream_entrada = live_audio.cerrar_stream(self._stream_entrada)
        self._stream_salida = live_audio.cerrar_stream(self._stream_salida)
        if self._loop and self._loop.is_running():
            try:
                def _cancelar_todas():
                    for t in asyncio.all_tasks(self._loop):
                        t.cancel()
                self._loop.call_soon_threadsafe(_cancelar_todas)
            except Exception:
                pass
            live_audio.cerrar_sesion_live(self._session_genai, self._loop)

    def alternar_microfono(self) -> bool:
        """Cierra o abre la captura Live; devuelve True si queda abierta."""
        if self.activo:
            self.detener()
            return False
        return self.iniciar()
