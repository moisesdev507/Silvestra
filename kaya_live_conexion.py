"""Sesión de conexión y gestión asíncrona para Gemini Live."""
import asyncio
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


async def ejecutar_sesion_live(sesion, solo_verificar: bool = False) -> bool:
    """Inicia la sesión Live conectando con Gemini Live y lanzando las tareas."""
    sesion._notificar_estado("conectando")
    key = obtener_api_key()
    if not key:
        print("[LIVE] Error: No se encontró GEMINI_API_KEY.")
        sesion._notificar_estado("error")
        return False

    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
    speech_cfg = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=sesion.voz)
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
        async with client.aio.live.connect(model=sesion.modelo, config=cfg) as _:
            print("[LIVE] Conexión validada exitosamente con Gemini Live API y herramientas!")
            sesion._notificar_estado("reposo")
            return True

    sesion._loop = asyncio.get_running_loop()
    sesion._cola_entrada = asyncio.Queue(maxsize=MAX_COLA_ENTRADA)
    sesion._evento_parada.clear()
    sesion._evento_parada_async = asyncio.Event()
    sesion.actualizar_actividad()

    sesion._hilo_audio = threading.Thread(target=sesion._hilo_reproductor, name="kaya-live-out", daemon=True)
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

    try:
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

        async with client.aio.live.connect(model=sesion.modelo, config=cfg) as session:
            sesion._session = session
            sesion._notificar_estado("escuchando")
            print(f"[LIVE] Sesión activa (modelo={sesion.modelo}, voz={sesion.voz}). Kaya te escucha...", flush=True)
            tareas = [
                asyncio.create_task(sesion._captura_microfono()),
                asyncio.create_task(sesion._recepcion_servidor()),
                asyncio.create_task(sesion._vigilante_silencio()),
            ]
            try:
                await asyncio.gather(*tareas)
            except asyncio.CancelledError:
                pass
            finally:
                sesion.detener()
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
