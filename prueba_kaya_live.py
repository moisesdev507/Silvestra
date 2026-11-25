"""Prototipo experimental e independiente de Kaya con Gemini Live API.

Audio nativo bidireccional en tiempo real con interrupción nativa (barge-in).
Audio I/O desacoplado del bucle asyncio, filtrado de pensamientos y reconexión continua.
"""
import argparse
import asyncio
import os
import queue
import sys
import threading
import traceback
import sounddevice as sd
from google import genai
from google.genai import types

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = "Aoede"
RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50  # ~50 ms -> 800 muestras int16 = 1600 bytes
MAX_COLA_ENTRADA = 60  # ~3 segundos máximo en buffer de entrada


def _obtener_api_key():
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


def _cargar_instruccion_alma():
    base = "Eres Kaya, asistente personal panameña, cálida, ingeniosa, hablas en español natural con respuestas breves."
    ruta_alma = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta_alma):
        try:
            with open(ruta_alma, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    base = contenido
        except Exception:
            pass
    extra = (
        "\n\nInstrucción crítica de estilo: Esta es una conversación por audio en vivo en tiempo real. "
        "Habla con fluidez, calidez panameña sin exagerar, tono fresco de amiga cercana. "
        "Responde en 1 o 2 frases cortas y directas para mantener el diálogo vivo y natural. "
        "Cero listas, cero asteriscos, cero frases de chatbot como '¿En qué te puedo ayudar?'."
    )
    return base + extra


def _hilo_reproductor(cola_salida, evento_parada):
    """Hilo dedicado de salida de audio que no toca el event loop de asyncio."""
    stream = None
    try:
        try:
            import audio_lock
            with audio_lock.bloqueo_portaudio():
                stream = sd.RawOutputStream(
                    samplerate=RATE_SALIDA,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=960,
                )
                stream.start()
        except Exception:
            stream = sd.RawOutputStream(
                samplerate=RATE_SALIDA,
                channels=CHANNELS,
                dtype="int16",
                blocksize=960,
            )
            stream.start()

        while not evento_parada.is_set():
            try:
                trozo = cola_salida.get(timeout=0.04)
            except queue.Empty:
                continue

            if trozo and len(trozo) > 0 and stream is not None and not stream.closed:
                try:
                    stream.write(trozo)
                except Exception as write_err:
                    if not evento_parada.is_set():
                        print(f"[LIVE] Error escribiendo audio en stream: {write_err}", flush=True)
    except Exception as err:
        if not evento_parada.is_set():
            print(f"[LIVE] Error iniciando reproductor de audio: {err}", flush=True)
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


async def _captura_microfono(session, cola_entrada, evento_parada):
    """Lee audio del micrófono desde la cola y lo envía a Gemini Live."""
    while not evento_parada.is_set():
        try:
            bloque = await asyncio.wait_for(cola_entrada.get(), timeout=0.1)
            if bloque and len(bloque) > 0:
                await session.send_realtime_input(
                    media=types.Blob(data=bloque, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            if not evento_parada.is_set():
                print(f"\n[LIVE] Excepción en captura_microfono: {e}", flush=True)
                traceback.print_exc()
            break


async def _recepcion_servidor(session, cola_salida, evento_parada):
    """Bucle continuo de lectura de session.receive() protegiendo contra timeouts y filtrando pensamientos."""
    turno_hablando = False

    while not evento_parada.is_set():
        try:
            async for resp in session.receive():
                if evento_parada.is_set():
                    break

                sc = getattr(resp, "server_content", None)
                if not sc:
                    continue

                # Interrupción nativa (barge-in detectado por Gemini Live)
                if getattr(sc, "interrupted", False):
                    print("\n[LIVE] Interrumpida por el usuario (barge-in)", flush=True)
                    turno_hablando = False
                    # Vaciar cola de audio instantáneamente
                    while not cola_salida.empty():
                        try:
                            cola_salida.get_nowait()
                        except Exception:
                            break
                    continue

                # Transcripción del usuario
                it = getattr(sc, "input_audio_transcription", None)
                if it and getattr(it, "text", None):
                    print(f"\n[Tú]: {it.text.strip()}", flush=True)

                # Transcripción de Kaya
                ot = getattr(sc, "output_audio_transcription", None)
                if ot and getattr(ot, "text", None):
                    print(f"\n[Kaya]: {ot.text.strip()}", flush=True)

                # Trozos de audio / texto del modelo
                mt = getattr(sc, "model_turn", None)
                if mt:
                    for part in mt.parts:
                        # Filtrar pensamientos internos
                        if getattr(part, "thought", False):
                            continue

                        # Si no hay output_audio_transcription, imprimir texto limpio
                        if part.text and not ot:
                            texto_limpio = part.text.strip()
                            if texto_limpio and not texto_limpio.startswith("**"):
                                print(f"\n[Kaya]: {texto_limpio}", flush=True)

                        # Encolar audio para el reproductor
                        if part.inline_data and part.inline_data.data:
                            if not turno_hablando:
                                turno_hablando = True
                                print("[LIVE] Reproduciendo audio...", flush=True)
                            cola_salida.put_nowait(part.inline_data.data)

                if getattr(sc, "turn_complete", False):
                    turno_hablando = False

        except asyncio.CancelledError:
            break
        except Exception as e:
            if not evento_parada.is_set():
                print(f"\n[LIVE] Excepción en recepción: {e}", flush=True)
                traceback.print_exc()
                await asyncio.sleep(0.2)
            else:
                break


async def ejecutar_sesion_live(modelo=MODELO_DEFECTO, voz=VOZ_DEFECTO, solo_verificar=False):
    """Inicia la sesión Live bidireccional interactiva o valida la conexión."""
    key = _obtener_api_key()
    if not key:
        print("[LIVE] Error: No se encontró GEMINI_API_KEY en entorno, config.py ni .env")
        return False

    print(f"[LIVE] Inicializando Gemini Live con modelo '{modelo}' y voz '{voz}'...")
    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})

    # Configuración Live con thinking_budget=0 y fallback si no lo soporta
    speech_cfg = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
        )
    )
    alma_instr = types.Content(parts=[types.Part.from_text(text=_cargar_instruccion_alma())])

    cfg = None
    try:
        cfg = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=speech_cfg,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=alma_instr,
        )
    except Exception:
        cfg = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=speech_cfg,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=alma_instr,
        )

    if solo_verificar:
        print("[LIVE] Modo verificación: conectando con Gemini Live...")
        async with client.aio.live.connect(model=modelo, config=cfg) as s:
            print("[LIVE] Conexión validada exitosamente con Gemini Live API!")
            return True

    loop = asyncio.get_running_loop()
    cola_entrada = asyncio.Queue(maxsize=MAX_COLA_ENTRADA)
    cola_salida = queue.Queue(maxsize=300)
    evento_parada = threading.Event()
    evento_parada_async = asyncio.Event()

    # Hilo dedicado para reproducción de audio
    hilo_audio = threading.Thread(
        target=_hilo_reproductor,
        args=(cola_salida, evento_parada),
        name="kaya-live-audio-out",
        daemon=True,
    )
    hilo_audio.start()

    muestras_bloque = int(RATE_ENTRADA * (CHUNK_ENTRADA_MS / 1000.0))

    def callback_entrada(indata, frames, time_info, status):
        """Conversión segura de buffer CFFI a bytes sin .copy() ni bloqueos."""
        if evento_parada.is_set():
            return
        try:
            datos_bytes = bytes(indata)
            if cola_entrada.full():
                try:
                    cola_entrada.get_nowait()
                except Exception:
                    pass
            loop.call_soon_threadsafe(cola_entrada.put_nowait, datos_bytes)
        except Exception:
            pass

    print("\n" + "=" * 50)
    print("  KAYA LIVE BIDIRECCIONAL - GEMINI NATIVE AUDIO")
    print("  Habla naturalmente por tu micrófono. Presiona Ctrl+C para salir.")
    print("=" * 50 + "\n", flush=True)

    stream_entrada = None
    try:
        try:
            import audio_lock
            with audio_lock.bloqueo_portaudio():
                stream_entrada = sd.RawInputStream(
                    samplerate=RATE_ENTRADA,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=muestras_bloque,
                    callback=callback_entrada,
                )
                stream_entrada.start()
        except Exception:
            stream_entrada = sd.RawInputStream(
                samplerate=RATE_ENTRADA,
                channels=CHANNELS,
                dtype="int16",
                blocksize=muestras_bloque,
                callback=callback_entrada,
            )
            stream_entrada.start()

        async with client.aio.live.connect(model=modelo, config=cfg) as session:
            print("[LIVE] Sesión bidireccional abierta. Kaya te está escuchando...", flush=True)
            tareas = [
                asyncio.create_task(_captura_microfono(session, cola_entrada, evento_parada_async)),
                asyncio.create_task(_recepcion_servidor(session, cola_salida, evento_parada_async)),
            ]
            try:
                await asyncio.gather(*tareas)
            except asyncio.CancelledError:
                pass
            finally:
                evento_parada_async.set()
    finally:
        evento_parada.set()
        evento_parada_async.set()
        if stream_entrada is not None:
            try:
                try:
                    import audio_lock
                    with audio_lock.bloqueo_portaudio():
                        stream_entrada.stop()
                        stream_entrada.close()
                except Exception:
                    stream_entrada.stop()
                    stream_entrada.close()
            except Exception:
                pass
    return True


def main():
    parser = argparse.ArgumentParser(description="Prototipo experimental de Kaya con Gemini Live API.")
    parser.add_argument("--modelo", default=MODELO_DEFECTO, help=f"Modelo Gemini Live (defecto: {MODELO_DEFECTO})")
    parser.add_argument("--voz", default=VOZ_DEFECTO, help=f"Voz predefinida (defecto: {VOZ_DEFECTO})")
    parser.add_argument("--verificar", action="store_true", help="Solo valida la conexión con la API y sale")
    args = parser.parse_args()

    try:
        asyncio.run(ejecutar_sesion_live(modelo=args.modelo, voz=args.voz, solo_verificar=args.verificar))
    except KeyboardInterrupt:
        print("\n[LIVE] Sesión finalizada por el usuario. ¡Hasta luego!", flush=True)
    except Exception as e:
        print(f"\n[LIVE] Error en ejecución: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
