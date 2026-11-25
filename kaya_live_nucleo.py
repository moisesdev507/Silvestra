"""Núcleo modular de Kaya Live con Gemini Live API.

Voz oficial Achernar, audio bidireccional, soporte de tools, inyección de imágenes
y auto-reposo inteligente tras 75s de silencio para ahorro de cuota ($0).
"""
import asyncio
import queue
import threading
import time
import traceback
from typing import Any, Callable, List, Optional
import sounddevice as sd
from google.genai import types

import kaya_live_audio
from kaya_live_audio import (
    calcular_energia_pcm16,
    obtener_api_key,
    construir_instruccion_sistema,
    RATE_ENTRADA,
    RATE_SALIDA,
    CHANNELS,
    CHUNK_ENTRADA_MS,
    MAX_COLA_ENTRADA,
    TIMEOUT_SILENCIO_DEFECTO,
)
import kaya_live_conexion
import kaya_live_puente
import kaya_live_tools

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = "Achernar"


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
        on_estado: Optional[Callable[[str], None]] = None,
        on_nivel_voz: Optional[Callable[[float], None]] = None,
        on_transcripcion: Optional[Callable[[str, str], None]] = None,
        saludar_al_iniciar: bool = True,
    ):
        self.modelo = modelo
        self.voz = voz
        self.timeout_silencio = float(timeout_silencio)
        self.saludar_al_iniciar = bool(saludar_al_iniciar)
        self._saludo_inicial_enviado = False
        self.on_transcripcion_usuario = on_transcripcion_usuario
        self.on_transcripcion_kaya = on_transcripcion_kaya
        self.on_estado_audio = on_estado_audio
        self.on_estado = on_estado
        self.on_nivel_voz = on_nivel_voz
        self.on_transcripcion = on_transcripcion

        self._session = None
        self._evento_parada = threading.Event()
        self._evento_parada_async = None
        self._cola_entrada = None
        self._cola_salida = queue.Queue(maxsize=300)
        self._ultimo_contacto = time.monotonic()
        self._hilo_audio = None
        self._stream_entrada = None
        self._loop = None
        self._pausado = False
        self._estado_actual = "reposo"
        self._historial_turnos: List[dict] = []
        self._bloqueo_turnos = threading.RLock()

    def _notificar_estado(self, nuevo_estado: str):
        self._estado_actual = nuevo_estado
        if self.on_estado:
            try:
                self.on_estado(nuevo_estado)
            except Exception:
                pass
        if nuevo_estado in ("reposo", "error"):
            self._guardar_memoria_persistente()

    def _notificar_transcripcion(self, rol: str, texto: str):
        t = str(texto or "").strip()
        if t:
            with self._bloqueo_turnos:
                self._historial_turnos.append({"role": rol, "content": t})

        if self.on_transcripcion:
            try:
                self.on_transcripcion(rol, texto)
            except Exception:
                pass
        if rol == "usuario" and self.on_transcripcion_usuario:
            try:
                self.on_transcripcion_usuario(texto)
            except Exception:
                pass
        elif rol == "kaya" and self.on_transcripcion_kaya:
            try:
                self.on_transcripcion_kaya(texto)
            except Exception:
                pass

    def _notificar_nivel_voz(self, nivel: float):
        if self.on_nivel_voz:
            try:
                self.on_nivel_voz(nivel)
            except Exception:
                pass

    def _guardar_memoria_persistente(self):
        with self._bloqueo_turnos:
            turnos_copia = list(self._historial_turnos)
        if turnos_copia:
            kaya_live_puente.guardar_turno_o_resumen_memoria(turnos_copia)

    def pausar(self):
        """Pausa temporalmente la captura/envío de audio sin cerrar sesión."""
        self._pausado = True
        self._notificar_estado("reposo")

    def reanudar(self):
        """Reanuda la interacción tras haber sido pausada."""
        self._pausado = False
        self.actualizar_actividad()
        self._notificar_estado("escuchando")

    def actualizar_actividad(self):
        """Refresca la marca temporal del auto-reposo inteligente."""
        self._ultimo_contacto = time.monotonic()

    async def enviar_imagen_jpeg(self, jpeg_bytes: bytes):
        """Inyecta un fotograma JPEG en tiempo real a la sesión Live."""
        if self._session is not None and jpeg_bytes:
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

                if trozo and stream is not None and not stream.closed:
                    try:
                        nivel = calcular_energia_pcm16(trozo)
                        self._notificar_nivel_voz(nivel)
                        stream.write(trozo)
                    except Exception:
                        pass
        except Exception as e:
            if not self._evento_parada.is_set():
                print(f"[LIVE] Error en reproductor: {e}", flush=True)
        finally:
            if stream is not None:
                try:
                    import audio_lock
                    with audio_lock.bloqueo_portaudio():
                        if not stream.closed:
                            stream.stop()
                            stream.close()
                except Exception:
                    try:
                        if not stream.closed:
                            stream.stop()
                            stream.close()
                    except Exception:
                        pass

    async def _captura_microfono(self):
        while not self._evento_parada_async.is_set() and self._session is not None:
            try:
                bloque = await asyncio.wait_for(self._cola_entrada.get(), timeout=0.1)
                if bloque and not self._pausado:
                    self.actualizar_actividad()
                    if self._estado_actual != "hablando":
                        nivel_in = calcular_energia_pcm16(bloque)
                        if nivel_in > 0.05:
                            self._notificar_nivel_voz(nivel_in)
                    await self._session.send_realtime_input(
                        media=types.Blob(data=bloque, mime_type="audio/pcm;rate=16000")
                    )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._evento_parada_async.is_set():
                    print(f"[LIVE] Error en captura/envío (saliendo): {e}", flush=True)
                break

    async def _vigilante_silencio(self):
        while not self._evento_parada_async.is_set():
            await asyncio.sleep(2.0)
            inactivo = time.monotonic() - self._ultimo_contacto
            if inactivo >= self.timeout_silencio:
                print(f"\n[LIVE] Auto-reposo inteligente ({int(inactivo)}s sin voz). Ahorro de cuota.", flush=True)
                self._notificar_estado("reposo")
                self.detener()
                break

    async def _recepcion_servidor(self):
        turno_hablando = False
        try:
            if self._session is None:
                return
            async for resp in self._session.receive():
                if self._evento_parada_async.is_set():
                    break

                tc = getattr(resp, "tool_call", None)
                if tc:
                    self.actualizar_actividad()
                    self._notificar_estado("pensando")
                    llamadas = getattr(tc, "function_calls", []) or []
                    respuestas = []
                    for call in llamadas:
                        c_id = getattr(call, "id", "")
                        c_name = getattr(call, "name", "")
                        c_args = getattr(call, "args", {}) or {}
                        resultado = await kaya_live_tools.despachar_herramienta(c_name, c_args)
                        respuestas.append(types.FunctionResponse(id=c_id, name=c_name, response=resultado))
                    if respuestas and self._session is not None:
                        await self._session.send_tool_response(function_responses=respuestas)
                    self._notificar_estado("escuchando")
                    continue

                sc = getattr(resp, "server_content", None)
                if not sc:
                    continue

                if getattr(sc, "interrupted", False):
                    print("\n[LIVE] Interrupción (barge-in)", flush=True)
                    turno_hablando = False
                    self._notificar_estado("escuchando")
                    self._notificar_nivel_voz(0.0)
                    while not self._cola_salida.empty():
                        try:
                            self._cola_salida.get_nowait()
                        except Exception:
                            break
                    continue

                it = getattr(sc, "input_audio_transcription", None)
                if it and getattr(it, "text", None):
                    self.actualizar_actividad()
                    txt_u = it.text.strip()
                    self._notificar_transcripcion("usuario", txt_u)

                ot = getattr(sc, "output_audio_transcription", None)
                if ot and getattr(ot, "text", None):
                    self.actualizar_actividad()
                    txt_k = ot.text.strip()
                    self._notificar_transcripcion("kaya", txt_k)

                mt = getattr(sc, "model_turn", None)
                if mt:
                    for part in mt.parts:
                        if getattr(part, "thought", False):
                            continue
                        if part.text and not ot:
                            t_limpio = part.text.strip()
                            if t_limpio and not t_limpio.startswith("**"):
                                self._notificar_transcripcion("kaya", t_limpio)

                        if part.inline_data and part.inline_data.data:
                            self.actualizar_actividad()
                            if not turno_hablando:
                                turno_hablando = True
                                self._notificar_estado("hablando")
                                if self.on_estado_audio:
                                    self.on_estado_audio("reproduciendo")
                            self._cola_salida.put_nowait(part.inline_data.data)

                if getattr(sc, "turn_complete", False):
                    turno_hablando = False
                    self._notificar_estado("escuchando")
                    self._notificar_nivel_voz(0.0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._evento_parada_async.is_set():
                print(f"\n[LIVE] Excepción en recepción (saliendo de sesión): {e}", flush=True)
                raise e

    def detener(self):
        """Detiene de forma limpia y ordenada la sesión Live."""
        self._guardar_memoria_persistente()
        self._evento_parada.set()
        if self._evento_parada_async:
            self._evento_parada_async.set()

    async def ejecutar(self, solo_verificar: bool = False) -> bool:
        return await kaya_live_conexion.ejecutar_sesion_live(self, solo_verificar=solo_verificar)
