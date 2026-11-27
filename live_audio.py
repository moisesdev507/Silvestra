"""Módulo de audio PCM, compuerta anti-eco half-duplex y configuración para Gemini Live.

Implementa la ventana de cola antieco (~150 ms) para parlantes, asegurando
que la salida de audio nunca interrumpa a Kaya a mitad de frase.
"""
import asyncio
import datetime
import math
import os
import struct
import threading
import time

import identidad_origen
import live_prompt
from live_audio_anti_eco import CompuertaAntiEco

RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
UMBRAL_RMS_VOZ = 480.0
UMBRAL_ENERGIA_VOZ = 0.08

_DISYUNTOR_HASTA = 0.0
_LOCK_DISYUNTOR = threading.RLock()


def timeout_silencio_configurado(valor=None) -> float:
    """KAYA_TIMEOUT_SILENCIO (9 s de apagado estricto) con guarda de valores inválidos."""
    if valor is None:
        valor = os.environ.get("KAYA_TIMEOUT_SILENCIO", "9")
    try:
        segundos = float(valor)
    except (TypeError, ValueError):
        segundos = 9.0
    return segundos if segundos >= 2.0 else 9.0


TIMEOUT_SILENCIO_DEFECTO = timeout_silencio_configurado()


def es_error_cuota(exc: Exception) -> bool:
    if exc is None:
        return False
    texto = str(exc).lower()
    return "429" in texto or "resource_exhausted" in texto or "quota" in texto


def esta_en_enfriamiento_cuota() -> bool:
    with _LOCK_DISYUNTOR:
        return time.monotonic() < _DISYUNTOR_HASTA


def activar_enfriamiento_cuota(minutos: float = 15.0):
    global _DISYUNTOR_HASTA
    with _LOCK_DISYUNTOR:
        _DISYUNTOR_HASTA = time.monotonic() + (minutos * 60.0)
    print(f"[LIVE] Disyuntor de cuota activado por {minutos:.0f} minutos. Conmutando a modo clásico.", flush=True)


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def calcular_rms_pcm16(pcm_bytes: bytes) -> float:
    """Calcula el valor RMS directo del audio PCM 16-bit."""
    if not pcm_bytes or len(pcm_bytes) < 2:
        return 0.0
    num_muestras = len(pcm_bytes) // 2
    try:
        valores = struct.unpack(f"<{num_muestras}h", pcm_bytes[:num_muestras * 2])
        suma_cuad = sum(v * v for v in valores)
        return float(math.sqrt(suma_cuad / num_muestras))
    except Exception:
        return 0.0


def es_voz_activa(pcm_bytes: bytes) -> tuple[bool, float, float]:
    """Discrimina habla real frente a ruido ambiente para el watchdog (rms >= 480.0 y energia >= 0.08)."""
    rms = calcular_rms_pcm16(pcm_bytes)
    energia = calcular_energia_pcm16(pcm_bytes)
    es_habla = (rms >= UMBRAL_RMS_VOZ and energia >= UMBRAL_ENERGIA_VOZ)
    return es_habla, rms, energia


def remuestrear_pcm16_a_16k(pcm_bytes: bytes, rate_origen: int) -> bytes:
    """Remuestrea linealmente audio PCM int16 mono a 16000 Hz si la tarjeta abrió a 44.1k/48k."""
    if not pcm_bytes or rate_origen == RATE_ENTRADA:
        return pcm_bytes
    try:
        import numpy as np
        audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        num_muestras_salida = int(len(audio) * (RATE_ENTRADA / float(rate_origen)))
        if num_muestras_salida <= 0:
            return b""
        indices = np.linspace(0, len(audio) - 1, num_muestras_salida)
        remuestreado = np.interp(indices, np.arange(len(audio)), audio).astype(np.int16)
        return remuestreado.tobytes()
    except Exception:
        return pcm_bytes


def crear_input_stream(callback_audio):
    """Crea e inicia el InputStream de sounddevice asegurando compatibilidad con Windows."""
    import sounddevice as sd
    # Intentar primero a 16000 Hz nativo
    for rate_candidato in (RATE_ENTRADA, 48000, 44100):
        try:
            bs = int(rate_candidato * (CHUNK_ENTRADA_MS / 1000.0))
            stream = sd.InputStream(
                samplerate=rate_candidato,
                channels=CHANNELS,
                dtype="int16",
                blocksize=bs,
                callback=callback_audio,
            )
            stream.start()
            if rate_candidato != RATE_ENTRADA:
                print(f"[LIVE][AUDIO] Micrófono abierto a {rate_candidato}Hz con remuestreo a 16000Hz.", flush=True)
            return stream, rate_candidato
        except Exception:
            continue
    raise RuntimeError("No se pudo abrir ningún InputStream de micrófono para Gemini Live.")


def crear_output_stream():
    """Crea e inicia OutputStream PCM 24kHz para reproducción."""
    import sounddevice as sd
    stream = sd.OutputStream(
        samplerate=RATE_SALIDA,
        channels=CHANNELS,
        dtype="int16",
    )
    stream.start()
    return stream


def cerrar_stream(stream):
    """Cierra el stream bajo el bloqueo PortAudio (evita 0xc0000374 al conmutar)."""
    if stream:
        try:
            import audio_lock
            with audio_lock.bloqueo_portaudio():
                try:
                    if hasattr(stream, "abort"):
                        stream.abort()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass
        except Exception:
            pass
    return None


def cerrar_sesion_live(session, loop):
    """Cierra el WebSocket de Gemini Live sin bloquear el hilo que llama."""
    cierre = getattr(session, "close", None)
    if not callable(cierre) or loop is None:
        return
    try:
        def _hacer():
            try:
                asyncio.create_task(cierre())
            except Exception:
                pass
        if getattr(loop, "is_running", lambda: False)():
            loop.call_soon_threadsafe(_hacer)
        else:
            loop.run_until_complete(cierre())
    except Exception:
        pass


def calcular_energia_pcm16(pcm_bytes: bytes) -> float:
    """Calcula nivel de volumen normalizado (0.0 a 1.0) para el orbe."""
    if not pcm_bytes or len(pcm_bytes) < 2:
        return 0.0
    num_muestras = len(pcm_bytes) // 2
    try:
        valores = struct.unpack(f"<{num_muestras}h", pcm_bytes[:num_muestras * 2])
        suma_cuad = sum(v * v for v in valores)
        rms = math.sqrt(suma_cuad / num_muestras)
        return round(min(1.0, max(0.0, (rms - 100.0) / 4500.0)), 3)
    except Exception:
        return 0.0


def obtener_api_key() -> str:
    """Obtiene la clave de Gemini desde el entorno o config.py."""
    try:
        import claves_dinamicas
        return claves_dinamicas.valor("GEMINI_API_KEY", "GOOGLE_API_KEY")
    except Exception:
        return str(os.environ.get("GEMINI_API_KEY")
                   or os.environ.get("GOOGLE_API_KEY") or "").strip()


def obtener_hora_local_breve() -> str:
    """Genera fecha y hora amigable para el contexto."""
    try:
        now = datetime.datetime.now().astimezone()
        dia_sem = DIAS[now.weekday()]
        h12 = now.hour % 12 or 12
        minu = f"{now.minute:02d}"
        meridiano = "p. m." if now.hour >= 12 else "a. m."
        return f"Hoy es {dia_sem} {now.day} de {MESES[now.month-1]} de {now.year}, {h12}:{minu} {meridiano} (hora local)."
    except Exception:
        return ""


T_INICIO_PROCESO = time.time()
_PRIMERA_VOZ_REGISTRADA = False
_LOCK_TELEMETRIA_ARRANQUE = threading.RLock()


def registrar_tiempo_primera_voz():
    """Registra en silvestra.log el tiempo desde el arranque hasta el primer chunk de audio de bienvenida."""
    global _PRIMERA_VOZ_REGISTRADA
    with _LOCK_TELEMETRIA_ARRANQUE:
        if _PRIMERA_VOZ_REGISTRADA:
            return
        _PRIMERA_VOZ_REGISTRADA = True
        ms = round((time.time() - T_INICIO_PROCESO) * 1000.0)
        print(f"[tiempo] arranque_primera_voz={ms}ms", flush=True)


def construir_instruccion_arranque_rapido(
    primer_despertar: bool = False, nombre_usuario: str = "", incluir_fecha: bool = True,
    primer_saludo: bool = None,
) -> str:
    """Prompt compacto con identidad y usuario separado."""
    hora_str = obtener_hora_local_breve() if incluir_fecha else ""
    ctx_h = f" {hora_str}" if hora_str else ""
    quien = str(nombre_usuario or "").strip() or identidad_origen.USUARIO_SIN_NOMBRE
    if primer_despertar:
        turno = f" Primer turno: saluda a {quien} presentándote como Kaya y dale la bienvenida."
    else:
        turno = f" Primer turno: saluda alegremente a {quien} y confirma que estás lista."
    bloque_version = live_prompt._bloque_version_compartida(
        bool(primer_saludo) if primer_saludo is not None else bool(primer_despertar))
    return (
        identidad_origen.prompt_identidad(quien)
        + " Femenina, cálida, ingeniosa. Español panameño, 1 frase."
        + ctx_h + turno
        + " Usa revisar_pantalla si piden ver pantalla."
        + " Audio con ruido o incompleto: pregunta '¿Qué dijiste?' o calla; nunca adivines."
        + " CERO INVENCIONES; si el usuario da datos reales, usa recordar_dato en silencio."
        + " " + live_prompt.contexto_ambiental()
        + bloque_version
    )


def configuracion_transcripcion():
    """STT/TTS y detección automática de actividad, con hasattr seguro."""
    try:
        from google.genai import types
        if not hasattr(types, "AudioTranscriptionConfig"):
            return {}
        nombres = ("input_audio_transcription", "output_audio_transcription")
        cfg = types.LiveConnectConfig
        campos = getattr(cfg, "model_fields", None)
        if not isinstance(campos, dict):
            campos = getattr(cfg, "__fields__", None)
        if isinstance(campos, dict):
            salida = {n: types.AudioTranscriptionConfig() for n in nombres if n in campos}
        if "enable_affective_dialog" in campos:
            salida["enable_affective_dialog"] = True
        else:  # Config sustituida en pruebas.
            salida = {n: types.AudioTranscriptionConfig() for n in nombres}
        if hasattr(types, "AutomaticActivityDetection") and hasattr(types, "RealtimeInputConfig"):
            ric = types.RealtimeInputConfig
            campos_ric = getattr(ric, "model_fields", None)
            if not isinstance(campos_ric, dict):
                campos_ric = getattr(ric, "__fields__", None)
            if not isinstance(campos_ric, dict) or "automatic_activity_detection" in campos_ric:
                salida["realtime_input_config"] = ric(
                    automatic_activity_detection=types.AutomaticActivityDetection(
                        silence_duration_ms=1100, prefix_padding_ms=300))
        return salida
    except Exception:
        return {}


def trazar_transcripcion(rol: str, texto: str) -> str:
    """Escribe en silvestra.log (stdout redirigido) lo oído y lo dicho por Live."""
    limpio = str(texto or "").strip()
    if limpio:
        print(f"[LIVE][{rol}] {limpio}", flush=True)
    return limpio


def construir_instruccion_sistema(
    rapido: bool = False, primer_despertar: bool = False, nombre_usuario: str = "",
    incluir_fecha: bool = True, incluir_memoria: bool = True, max_chars=None,
    primer_saludo: bool = True,
) -> str:
    """Carga identidad, guía y, si se pide, fecha y memoria; max_chars acota la base."""
    if rapido:
        return construir_instruccion_arranque_rapido(
            primer_despertar, nombre_usuario, incluir_fecha=incluir_fecha, primer_saludo=primer_saludo)
    estilo = (
        "Eres Kaya, asistente personal con carácter propio. "
        "Hablas en español natural de Panamá con respuestas breves (1 a 2 frases por defecto)."
    )
    ruta_alma = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta_alma):
        try:
            with open(ruta_alma, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    estilo = c
        except Exception:
            pass
    base = identidad_origen.bloque_identidad(nombre_usuario) + "\n" + estilo

    hora_str = obtener_hora_local_breve() if incluir_fecha else ""
    contexto_tiempo = f"\n\n[Fecha y hora actual]: {hora_str}" if hora_str else ""

    guia_vocal = live_prompt.guia_vocal(primer_saludo=primer_saludo)
    memoria_txt = live_prompt.contexto_memoria() if incluir_memoria else ""

    limite = 4200 if max_chars is None else max(600, int(max_chars))
    margen = limite - len(base) - len(contexto_tiempo) - len(memoria_txt) - 4
    if len(guia_vocal) > margen:
        guia_vocal = guia_vocal[:max(0, margen)].rsplit("\n", 1)[0] + "\n..."
    return base + contexto_tiempo + guia_vocal + memoria_txt
