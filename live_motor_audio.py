"""Capa de audio de la sesión Live: puente WebRTC 16 kHz y respaldo PortAudio."""
import asyncio
import queue
import threading
import time

from google.genai import types

import live_audio
import live_estado
import live_webrtc
import puerta_audio_live


class CapaAudioLive:
    """Métodos de captura/reproducción compartidos por SesionKayaLive."""

    def _cola_mensajes_sistema(self):
        """Cola thread-safe de textos de Sistema 2 pendientes de voz."""
        cola = getattr(self, "_cola_sistema_propia", None)
        if cola is None:
            cola = queue.Queue()
            self._cola_sistema_propia = cola
        return cola

    async def enviar_texto_live(self, session, texto):
        """Envío seguro: text puro con turn_complete, nunca audio crudo (1007)."""
        contenido = types.Content(
            role="user", parts=[types.Part(text=str(texto))]
        )
        await session.send_client_content(turns=contenido, turn_complete=True)

    def encolar_mensaje_sistema(self, texto):
        """Encola un resultado S2 y despierta el puente si estaba en Reposo."""
        texto = str(texto or "").strip()
        if not texto or not getattr(self, "activo", False):
            return False
        self._cola_mensajes_sistema().put(texto)
        puente = getattr(self, "_puente_webrtc", None)
        if puente is not None and getattr(puente, "dormida", False):
            try:
                puente.dormida = False
                puente.despertar()
            except Exception:
                pass
        return True

    async def drenar_mensajes_sistema(self, session):
        """Entrega textos dentro del loop; reencola si la sesión se cierra."""
        cola = self._cola_mensajes_sistema()
        while getattr(self, "activo", False):
            texto = None
            try:
                texto = await asyncio.to_thread(cola.get, timeout=0.1)
                await self.enviar_texto_live(session, texto)
                texto = None
            except asyncio.CancelledError:
                if texto is not None:
                    cola.put(texto)
                raise
            except queue.Empty:
                continue
            except Exception as err:
                print(f"[LIVE] Reencolando texto S2: {err}", flush=True)
                if texto is not None:
                    cola.put(texto)
                await asyncio.sleep(0.25)

    def _paso_nivel_salida(self, energia: float) -> float:
        """Ataque rápido y caída gradual: el orbe sigue cada sílaba de Kaya."""
        actual = float(getattr(self, "_nivel_salida_suave", 0.0))
        factor = 0.45 if energia > actual else 0.18
        suave = actual + (max(0.0, min(1.0, energia)) - actual) * factor
        self._nivel_salida_suave = suave
        return suave

    def _notificar_nivel_salida(self, pcm: bytes):
        """Energía PCM16 de la voz de Kaya con decaimiento hasta el silencio."""
        live_audio.registrar_tiempo_primera_voz()
        nivel = self._paso_nivel_salida(live_audio.calcular_energia_pcm16(pcm))
        self._nivel_salida_gen = getattr(self, "_nivel_salida_gen", 0) + 1
        self._nivel_salida_t = time.monotonic()
        self._notificar_nivel(nivel, True)
        hilo = getattr(self, "_hilo_decaimiento", None)
        if hilo is None or not hilo.is_alive():
            self._hilo_decaimiento = threading.Thread(
                target=self._decaer_nivel_salida, daemon=True, name="live-nivel-decay")
            self._hilo_decaimiento.start()

    def _decaer_nivel_salida(self):
        """Un único hilo baja el nivel cuando Gemini deja de enviar PCM."""
        while getattr(self, "activo", False):
            time.sleep(0.05)
            if not getattr(self, "_nivel_salida_gen", 0):
                continue
            if time.monotonic() - getattr(self, "_nivel_salida_t", 0.0) < 0.14:
                continue
            actual = float(getattr(self, "_nivel_salida_suave", 0.0))
            if actual <= 0.004:
                self._nivel_salida_suave = 0.0
                self._nivel_salida_gen = 0
                self._notificar_nivel(0.0, True)
                continue
            self._nivel_salida_suave = actual * 0.72
            self._notificar_nivel(self._nivel_salida_suave, True)
        self._hilo_decaimiento = None

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

    def vaciar_colas_audio_entrada(self):
        """Descarta fragmentos pendientes para evitar audio viejo en vuelo."""
        try:
            with self.cola_audio_entrada.mutex:
                self.cola_audio_entrada.queue.clear()
        except Exception:
            pass
        puente = getattr(self, "_puente_webrtc", None)
        cola_p = getattr(puente, "cola_entrada", None)
        if cola_p is not None and hasattr(cola_p, "mutex"):
            try:
                with cola_p.mutex:
                    cola_p.queue.clear()
            except Exception:
                pass

    async def _tarea_envio_audio(self, session):
        puente = self._puente_webrtc
        cola = puente.cola_entrada if puente is not None else self.cola_audio_entrada
        while self.activo:
            try:
                data = await asyncio.to_thread(cola.get, timeout=0.1)
                if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
                    continue  # frames vacíos provocan cierre 1007 en Gemini
                if puente is not None:
                    if data == live_webrtc.SENAL_SLEEP:
                        if hasattr(self, "_al_dormir"):
                            self._al_dormir()
                        continue
                    if puente.dormida:
                        puente.dormida = False
                        live_estado.reanudar_escucha(self)
                        print("[LIVE][AUDIO] Audio enviado a Gemini tras despertar.", flush=True)
                if (
                    getattr(self, "_estado_actual", "") == "pensando"
                    or self.puerta.reproduciendo
                    or self.compuerta.esta_en_ventana_eco()
                ):
                    continue
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm")
                )
                live_estado.notificar_actividad_audio(self)
            except queue.Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"[LIVE][AUDIO] Error enviando audio a Gemini: {e}", flush=True)
                break
