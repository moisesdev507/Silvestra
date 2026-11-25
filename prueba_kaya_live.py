"""Prototipo experimental e independiente de Kaya con Gemini Live API.

Audio nativo bidireccional en tiempo real con interrupción nativa (barge-in).
No modifica ningún archivo del sistema central ni depende de servicios locales.
"""
import argparse
import asyncio
import os
import sys
import threading
import sounddevice as sd
from google import genai
from google.genai import types

MODELO_DEFECTO = "gemini-2.5-flash-native-audio-latest"
VOZ_DEFECTO = "Aoede"
RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50  # ~50 ms -> 800 muestras int16 = 1600 bytes


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


async def _captura_microfono(session, cola_entrada, evento_parada):
    """Lee audio del micrófono en streaming continuo y lo envía a Gemini Live."""
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
                print(f"[LIVE] Error en envío de audio: {e}", flush=True)
            break


async def _reproduccion_audio(cola_salida, evento_parada):
    """Reproduce audio PCM 24 kHz recibido desde Gemini Live de forma continua."""
    loop = asyncio.get_running_loop()

    def callback_salida(outdata, frames, time_info, status):
        bytes_pedidos = frames * 2  # 16-bit mono = 2 bytes/frame
        acumulado = bytearray()
        while len(acumulado) < bytes_pedidos:
            try:
                pedazo = cola_salida.get_nowait()
                acumulado.extend(pedazo)
            except Exception:
                break
        if len(acumulado) < bytes_pedidos:
            acumulado.extend(b"\x00" * (bytes_pedidos - len(acumulado)))
        elif len(acumulado) > bytes_pedidos:
            sobrante = bytes(acumulado[bytes_pedidos:])
            acumulado = acumulado[:bytes_pedidos]
            try:
                cola_salida.put_nowait(sobrante)
            except Exception:
                pass
        outdata[:] = bytes(acumulado)

    try:
        with sd.RawOutputStream(
            samplerate=RATE_SALIDA,
            channels=CHANNELS,
            dtype="int16",
            blocksize=960,
            callback=callback_salida,
        ):
            while not evento_parada.is_set():
                await asyncio.sleep(0.05)
    except Exception as err:
        if not evento_parada.is_set():
            print(f"[LIVE] Error en stream de salida: {err}", flush=True)


async def _recepcion_servidor(session, cola_salida, evento_parada):
    """Recibe audio y transcripciones desde el servidor Live de Gemini."""
    async for resp in session.receive():
        if evento_parada.is_set():
            break

        sc = resp.server_content
        if not sc:
            continue

        # Interrupción nativa (barge-in del servidor)
        if getattr(sc, "interrupted", False):
            print("\n[LIVE] Interrumpida por el usuario (barge-in)", flush=True)
            # Vaciar de inmediato la cola de salida para que Kaya se calle en < 20 ms
            while not cola_salida.empty():
                try:
                    cola_salida.get_nowait()
                except Exception:
                    break
            continue

        # Transcripción del habla del usuario
        it = getattr(sc, "input_audio_transcription", None)
        if it and getattr(it, "text", None):
            print(f"\n[Usuario]: {it.text}", end="", flush=True)

        # Transcripción o audio de la respuesta de Kaya
        ot = getattr(sc, "output_audio_transcription", None)
        if ot and getattr(ot, "text", None):
            print(f"\n[Kaya]: {ot.text}", end="", flush=True)

        mt = getattr(sc, "model_turn", None)
        if mt:
            for part in mt.parts:
                if part.text and not ot:
                    print(f"\n[Kaya]: {part.text}", end="", flush=True)
                if part.inline_data and part.inline_data.data:
                    cola_salida.put_nowait(part.inline_data.data)


async def ejecutar_sesion_live(modelo=MODELO_DEFECTO, voz=VOZ_DEFECTO, solo_verificar=False):
    """Inicia la sesión Live bidireccional interactiva o valida la conexión."""
    key = _obtener_api_key()
    if not key:
        print("[LIVE] Error: No se encontró GEMINI_API_KEY en entorno, config.py ni .env")
        return False

    print(f"[LIVE] Inicializando Gemini Live con modelo '{modelo}' y voz '{voz}'...")
    client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})

    cfg = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=_cargar_instruccion_alma())]
        ),
    )

    if solo_verificar:
        print("[LIVE] Modo verificación: conectando con Gemini Live...")
        async with client.aio.live.connect(model=modelo, config=cfg) as s:
            print("[LIVE] Conexión validada exitosamente con Gemini Live API!")
            return True

    loop = asyncio.get_running_loop()
    cola_entrada = asyncio.Queue()
    cola_salida = asyncio.Queue()
    evento_parada = asyncio.Event()

    muestras_bloque = int(RATE_ENTRADA * (CHUNK_ENTRADA_MS / 1000.0))

    def callback_entrada(indata, frames, time_info, status):
        if not evento_parada.is_set():
            loop.call_soon_threadsafe(cola_entrada.put_nowait, indata.copy())

    print("\n" + "=" * 50)
    print("  KAYA LIVE BIDIRECCIONAL - GEMINI NATIVE AUDIO")
    print("  Habla naturalmente por tu micrófono. Presiona Ctrl+C para salir.")
    print("=" * 50 + "\n", flush=True)

    stream_entrada = sd.RawInputStream(
        samplerate=RATE_ENTRADA,
        channels=CHANNELS,
        dtype="int16",
        blocksize=muestras_bloque,
        callback=callback_entrada,
    )

    with stream_entrada:
        async with client.aio.live.connect(model=modelo, config=cfg) as session:
            print("[LIVE] Sesión bidireccional abierta. Kaya te está escuchando...", flush=True)
            tareas = [
                asyncio.create_task(_captura_microfono(session, cola_entrada, evento_parada)),
                asyncio.create_task(_reproduccion_audio(cola_salida, evento_parada)),
                asyncio.create_task(_recepcion_servidor(session, cola_salida, evento_parada)),
            ]
            try:
                await asyncio.gather(*tareas)
            except asyncio.CancelledError:
                pass
            finally:
                evento_parada.set()
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
        sys.exit(1)


if __name__ == "__main__":
    main()
