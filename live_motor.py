"""Motor interactivo Gemini Live para Silvestra con puente WebRTC y respaldo PortAudio."""
import asyncio, queue, threading
from typing import Callable, Optional
from google import genai
from google.genai import types
import ciclo_sueno_kaya
import estado_emocional_kaya
import identidad_origen
import live_audio, live_estado, live_entrega, live_herramientas, live_prompt, live_turno, live_webrtc, memoria_contexto, puerta_audio_live
from live_entrega import registrar_sesion_activa, sesion_activa
from live_motor_audio import CapaAudioLive

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = identidad_origen.VOZ_KAYA_LIVE
from live_audio import activar_enfriamiento_cuota, es_error_cuota, esta_en_enfriamiento_cuota


class SesionKayaLive(CapaAudioLive):
    def __init__(
        self, modelo: str = MODELO_DEFECTO, voz: str = VOZ_DEFECTO,
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
        self._tareas_envio, self._bloqueo_envio = set(), threading.RLock()
        self._primer_saludo_live = live_prompt.debe_dar_primer_saludo()

    @staticmethod
    def _llamar_cb(cb, *args):
        if callable(cb):
            try:
                cb(*args)
            except Exception:
                pass

    def _notificar_estado(self, estado: str):
        with self._candado:
            self._estado_actual = estado
        self._llamar_cb(self.on_estado, estado)

    def _notificar_nivel(self, nivel: float, salida: bool = False):
        if salida or not getattr(self, "_nivel_salida_gen", 0):
            self._llamar_cb(self.on_nivel_voz, nivel)

    def _notificar_texto(self, rol: str, texto: str):
        self._llamar_cb(self.on_transcripcion, rol, texto)

    def _al_dormir(self):
        """Reposo Azul sin tocar Qt ni bloquear el hilo de audio."""
        ciclo_sueno_kaya.al_dormir(memoria_contexto.turnos_recientes())

    async def _tarea_watchdog(self):
        if self._puente_webrtc is not None:
            while self.activo:
                await asyncio.sleep(1.0)
            return
        while self.activo:
            await asyncio.sleep(0.5)
            if self.puerta.debe_cerrar():
                print(f"[LIVE] Inactividad {self.timeout_silencio:.1f}s: cierre Live.", flush=True)
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
        self._notificar_estado("conectando")
        live_herramientas.registrar_callback_reposo(self.detener)
        primer_ciclo = True
        acumulador = live_turno.AcumuladorTurnos()

        while self.activo:
            cfg = live_turno.construir_config(
                self.voz, rapido, despertar, nombre_actual,
                primer_saludo=bool(self._primer_saludo_live))
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
                    if self._primer_saludo_live:
                        self._primer_saludo_live = False
                        live_prompt.registrar_bienvenida_completada()

                    tarea_audio = asyncio.create_task(self._tarea_envio_audio(session))
                    tarea_dog = asyncio.create_task(self._tarea_watchdog())
                    turno_interrumpido = False
                    try:
                        async for resp in session.receive():
                            if not self.activo:
                                break
                            sc = resp.server_content
                            if sc:
                                it = getattr(sc, "input_audio_transcription", None)
                                if it and getattr(it, "text", None):
                                    voz = live_audio.trazar_transcripcion("USUARIO", it.text)
                                    if voz:
                                        acumulador.agregar_usuario(voz)
                                        self._notificar_texto("usuario", voz)
                                ot = getattr(sc, "output_audio_transcription", None)
                                texto_kaya = live_audio.trazar_transcripcion("KAYA", getattr(ot, "text", ""))
                                acumulador.agregar_kaya(texto_kaya)
                                if getattr(sc, "interrupted", False):
                                    turno_interrumpido = True
                                    if self._puente_webrtc is not None:
                                        self._puente_webrtc.interrumpir_salida()
                                    else:
                                        with self.cola_audio_salida.mutex:
                                            self.cola_audio_salida.queue.clear()
                                    live_estado.reanudar_escucha(self)
                                    estado_emocional_kaya.registrar_si_disponible("interrupcion_barge_in")
                                if getattr(sc, "turn_complete", False):
                                    acumulador.vaciar()
                                    live_estado.reanudar_escucha(self)
                                    if not turno_interrumpido:
                                        estado_emocional_kaya.registrar_si_disponible("charla_fluida")
                                    turno_interrumpido = False
                                mt = sc.model_turn
                                if mt:
                                    for part in mt.parts:
                                        if getattr(part, "inline_data", None) and part.inline_data.data:
                                            self._notificar_nivel_salida(part.inline_data.data)
                                            if self._puente_webrtc is not None:
                                                self._puente_webrtc.enviar_audio_salida(part.inline_data.data)
                                            else:
                                                self.compuerta.marcar_encolado_salida()
                                                self.cola_audio_salida.put(part.inline_data.data)
                                        if getattr(part, "text", None):
                                            acumulador.agregar_kaya(part.text)
                                            self._notificar_texto("kaya", part.text)
                            tc = resp.tool_call
                            if tc:
                                self._notificar_estado("pensando")
                                self.puerta.notificar_actividad()
                                self.vaciar_colas_audio_entrada()
                                resps = []
                                for call in tc.function_calls:
                                    res_call = await live_herramientas.despachar_herramienta_asincrona(call.name, call.args)
                                    resps.append(types.FunctionResponse(
                                        name=call.name, id=call.id,
                                        response={"result": res_call}))
                                if resps:
                                    self.vaciar_colas_audio_entrada()
                                    await session.send_tool_response(function_responses=resps)
                                    live_estado.reanudar_escucha(self)
                    finally:
                        acumulador.vaciar()
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
                print(f"[LIVE] Reconectando Live: {e}", flush=True)
                await asyncio.sleep(0.8)

    def iniciar(self) -> bool:
        if esta_en_enfriamiento_cuota():
            print("[LIVE] Enfriamiento de cuota activo. Omitiendo arranque de Live.", flush=True)
            return False
        if self.activo:
            return True
        self.activo = True
        registrar_sesion_activa(self)
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
                print(f"[LIVE] Error micr?fono: {e}", flush=True)
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
                print(f"[LIVE] Fin sesi?n: {e}", flush=True)
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

    def enviar_texto(self, texto: str, turn_complete: bool = True) -> bool:
        """Inyecta un turno completo en la sesión viva sin esperar otra voz."""
        return live_entrega.enviar_texto(self, texto, turn_complete=turn_complete)

    def detener(self):
        if not self.activo:
            return
        self.activo = False
        if live_entrega._sesion_registrada() is self:
            registrar_sesion_activa(None)
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
