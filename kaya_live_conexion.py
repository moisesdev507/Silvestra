"""Sesión de conexión y gestión asíncrona para Gemini Live."""
import asyncio
import datetime
import queue
import threading
import time
import sounddevice as sd
from google import genai
from google.genai import types

import kaya_live_audio
from kaya_live_audio import (
    obtener_api_key,
    construir_instruccion_sistema,
    RATE_ENTRADA,
    CHANNELS,
    CHUNK_ENTRADA_MS,
    MAX_COLA_ENTRADA,
)
import kaya_live_tools


def crear_configuracion_live(sesion):
    speech_cfg = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=sesion.voz)
        )
    )
    instr = construir_instruccion_sistema()
    if len(instr) > 1500:
        instr = instr[:1490].rsplit("\n", 1)[0] + "\n..."
    sys_instr = types.Content(parts=[types.Part.from_text(text=instr)])

    cfg_kwargs = dict(
        response_modalities=[types.Modality.AUDIO],
        speech_config=speech_cfg,
        tools=kaya_live_tools.obtener_herramientas_live(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=sys_instr,
    )
    try:
        return types.LiveConnectConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            **cfg_kwargs,
        )
    except Exception:
        return types.LiveConnectConfig(**cfg_kwargs)


async def verificar_conexion_real(client, modelo: str, config) -> bool:
    """Verifica conexión enviando 3 chunks PCM 16kHz silenciosos sin error 1011."""
    async with client.aio.live.connect(model=modelo, config=config) as session:
        silencio = b"\x00\x00" * 800  # 50 ms a 16 kHz 16-bit mono
        for _ in range(3):
            await session.send_realtime_input(media=types.Blob(data=silencio, mime_type="audio/pcm;rate=16000"))
            await asyncio.sleep(0.05)
        it = session.receive().__aiter__()
        try:
            await asyncio.wait_for(it.__anext__(), timeout=1.5)
        except asyncio.TimeoutError:
            pass
        return True


async def enviar_saludo_inicial_si_aplica(session, sesion):
    """Envía un prompt de sistema silencioso para que Kaya salude naturalmente al conectar."""
    if not getattr(sesion, "saludar_al_iniciar", False) or getattr(sesion, "_saludo_inicial_enviado", False):
        return
    try:
        now = datetime.datetime.now()
        h_str = now.strftime("%H:%M")
        prompt_saludo = (
            f"[Sistema: acaba de abrirse la sesión. Son las {h_str}. "
            "Saluda breve, natural y cercana en 1 frase según la hora y, si hay un tema pendiente reciente, menciónalo con naturalidad.]"
        )
        await session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part.from_text(text=prompt_saludo)])],
            turn_complete=True,
        )
        sesion._saludo_inicial_enviado = True
    except Exception as e:
        print(f"[LIVE] Error enviando saludo inicial: {e}", flush=True)


async def ejecutar_sesion_live(sesion, solo_verificar: bool = False) -> bool:
    """Inicia la sesión Live con reconexión controlada y manejo robusto de excepciones."""
    sesion._notificar_estado("conectando")
    key = obtener_api_key()
    if not key:
        print("[LIVE] Error: No se encontró GEMINI_API_KEY.")
        sesion._notificar_estado("error")
        return False

    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    cfg = crear_configuracion_live(sesion)

    if solo_verificar:
        try:
            ok = await verificar_conexion_real(client, sesion.modelo, cfg)
            if ok:
                print("[LIVE] Conexión validada exitosamente con Gemini Live API y herramientas!")
                sesion._notificar_estado("reposo")
                return True
        except Exception as e:
            print(f"[LIVE] Error en verificación: {e}", flush=True)
            sesion._notificar_estado("error")
            return False

    sesion._loop = asyncio.get_running_loop()
    sesion._cola_entrada = asyncio.Queue(maxsize=MAX_COLA_ENTRADA)
    sesion._evento_parada.clear()
    sesion._evento_parada_async = asyncio.Event()
    sesion.actualizar_actividad()

    if getattr(sesion, "audio_local", True):
        sesion._hilo_audio = threading.Thread(target=sesion._hilo_reproductor, name="kaya-live-out", daemon=True)
        sesion._hilo_audio.start()
    else:
        # En modo transporte remoto, el reproductor solo despacha a on_audio_salida sin abrir PortAudio
        def _hilo_despachador_remoto():
            while not sesion._evento_parada.is_set():
                try:
                    trozo = sesion._cola_salida.get(timeout=0.04)
                except queue.Empty:
                    continue
                if trozo and sesion.on_audio_salida:
                    try:
                        nivel = kaya_live_audio.calcular_energia_pcm16(trozo)
                        sesion._notificar_nivel_voz(nivel)
                        sesion.on_audio_salida(trozo)
                    except Exception:
                        pass
        sesion._hilo_audio = threading.Thread(target=_hilo_despachador_remoto, name="kaya-live-out-remote", daemon=True)
        sesion._hilo_audio.start()

    muestras_bloque = int(RATE_ENTRADA * (CHUNK_ENTRADA_MS / 1000.0))

    def callback_entrada(indata, frames, time_info, status):
        if sesion._evento_parada.is_set():
            return
        try:
            datos = bytes(indata)
            if sesion._cola_entrada.full():
                try:
                    sesion._cola_entrada.get_nowait()
                except Exception:
                    pass
            sesion._loop.call_soon_threadsafe(sesion._cola_entrada.put_nowait, datos)
        except Exception:
            pass

    reintentos = 0
    max_reintentos = 3
    delays = [2.0, 4.0, 8.0]

    try:
        if getattr(sesion, "audio_local", True):
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    sesion._stream_entrada = sd.RawInputStream(
                        samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=muestras_bloque, callback=callback_entrada
                    )
                    sesion._stream_entrada.start()
            except Exception:
                sesion._stream_entrada = sd.RawInputStream(
                    samplerate=RATE_ENTRADA, channels=CHANNELS, dtype="int16", blocksize=muestras_bloque, callback=callback_entrada
                )
                sesion._stream_entrada.start()

        while not sesion._evento_parada.is_set():
            try:
                sesion._notificar_estado("conectando")
                async with client.aio.live.connect(model=sesion.modelo, config=cfg) as session:
                    sesion._session = session
                    sesion._notificar_estado("escuchando")
                    reintentos = 0
                    print(f"[LIVE] Sesión activa (modelo={sesion.modelo}, voz={sesion.voz}). Kaya te escucha...", flush=True)

                    await enviar_saludo_inicial_si_aplica(session, sesion)

                    t_mic = asyncio.create_task(sesion._captura_microfono())
                    t_rec = asyncio.create_task(sesion._recepcion_servidor())
                    t_vig = asyncio.create_task(sesion._vigilante_silencio())

                    done, pending = await asyncio.wait(
                        [t_mic, t_rec, t_vig],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

            except Exception as e:
                sesion._session = None
                if sesion._evento_parada.is_set():
                    break
                reintentos += 1
                if reintentos <= max_reintentos:
                    espera = delays[reintentos - 1]
                    print(f"\n[LIVE] Conexión interrumpida ({e}). Reconectando intento {reintentos}/{max_reintentos} en {espera}s...", flush=True)
                    sesion._notificar_estado("conectando")
                    await asyncio.sleep(espera)
                else:
                    print(f"\n[LIVE] Máximo de intentos alcanzado ({e}). Pasando a reposo.", flush=True)
                    sesion._notificar_estado("error")
                    sesion._notificar_estado("reposo")
                    sesion.detener()
                    break
    finally:
        sesion.detener()
        if sesion._stream_entrada is not None:
            try:
                import audio_lock
                with audio_lock.bloqueo_portaudio():
                    sesion._stream_entrada.stop()
                    sesion._stream_entrada.close()
            except Exception:
                try:
                    sesion._stream_entrada.stop()
                    sesion._stream_entrada.close()
                except Exception:
                    pass
        sesion._notificar_estado("reposo")
    return True
