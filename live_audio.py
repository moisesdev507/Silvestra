"""Módulo de audio PCM, compuerta anti-eco half-duplex y configuración para Gemini Live.

Implementa la ventana de cola antieco (~320 ms) para parlantes, asegurando
que la salida de audio nunca interrumpa a Kaya a mitad de frase.
"""
import datetime
import math
import os
import struct
import threading
import time
from typing import Optional

RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
TIMEOUT_SILENCIO_DEFECTO = 9.0  # Cierre a 9 segundos según especificación
UMBRAL_RMS_VOZ = 480.0
UMBRAL_ENERGIA_VOZ = 0.08

_DISYUNTOR_HASTA = 0.0
_LOCK_DISYUNTOR = threading.RLock()


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


class CompuertaAntiEco:
    """Compuerta half-duplex para evitar autocorte por eco con parlantes."""

    def __init__(
        self,
        modo_audifonos: Optional[bool] = None,
        eco_cola_ms: Optional[float] = None,
        cola_salida=None,
    ):
        if modo_audifonos is None:
            self.modo_audifonos = os.environ.get("KAYA_MODO_AUDIFONOS", "0").strip() == "1"
        else:
            self.modo_audifonos = bool(modo_audifonos)

        if eco_cola_ms is None:
            try:
                self.eco_cola_ms = float(os.environ.get("KAYA_ECO_COLA_MS", "250"))
            except Exception:
                self.eco_cola_ms = 250.0
        else:
            self.eco_cola_ms = float(eco_cola_ms)

        self.cola_salida = cola_salida
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = 0.0
        self._abierta = False

    def marcar_inicio_escritura(self):
        """Marca inicio de reproducción al parlante."""
        self._reproduciendo_salida = True
        self._ultimo_fin_salida = time.monotonic()
        self._abierta = False

    def marcar_fin_escritura(self):
        """Marca fin de reproducción en el parlante."""
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = time.monotonic()

    def marcar_encolado_salida(self):
        """Actualiza marca temporal al recibir nuevo audio de salida."""
        self._ultimo_fin_salida = time.monotonic()
        self._abierta = False

    def esta_en_ventana_eco(self) -> bool:
        """Devuelve True si está reproduciendo o dentro de la ventana de gracia."""
        if self.modo_audifonos:
            return False
        if self._reproduciendo_salida:
            return True
        if self.cola_salida is not None and not getattr(self.cola_salida, "empty", lambda: True)():
            return True
        cola_s = self.eco_cola_ms / 1000.0
        return (time.monotonic() - self._ultimo_fin_salida) < cola_s

    def filtrar_chunk_entrada(self, chunk: bytes) -> tuple[bytes, bool]:
        """Si está en ventana eco: devuelve silencio y silenciado=True."""
        if not chunk:
            return b"", False
        if self.esta_en_ventana_eco():
            self._abierta = False
            return bytes(len(chunk)), True
        if not self._abierta:
            self._abierta = True
            print("[LIVE][AUDIO] Compuerta antieco ABIERTA: escuchando usuario.", flush=True)
        return chunk, False

    def registrar_info_inicio(self):
        if self.modo_audifonos:
            print("[LIVE][AUDIO] Compuerta antieco: DESACTIVADA (modo audífonos).", flush=True)
        else:
            print(f"[LIVE][AUDIO] Compuerta antieco: ACTIVA (parlantes, ventana={int(self.eco_cola_ms)}ms).", flush=True)


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
    """Detiene y cierra un stream de audio con abort() + close() evitando deadlocks en PortAudio."""
    if stream:
        try:
            if hasattr(stream, "abort"):
                stream.abort()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
    return None


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


def construir_instruccion_arranque_rapido() -> str:
    """Prompt ultracompacto para el primer saludo sin recuerdos pesados."""
    hora_str = obtener_hora_local_breve()
    ctx_h = f" {hora_str}" if hora_str else ""
    return (
        "Eres Kaya, compañera y asistente personal de Moisés en Panamá. "
        "Femenina, cálida, ingeniosa, leal y afectuosa. Hablas en español de Panamá con respuestas breves de 1 frase."
        f"{ctx_h} Saluda alegremente a Moisés en tu primer turno confirmando que estás lista. "
        "Tienes visión de pantalla: usa revisar_pantalla si te lo piden."
    )


def construir_instruccion_sistema(rapido: bool = False) -> str:
    """Carga alma.txt, contexto de tiempo y guía vocal en Panamá."""
    if rapido:
        return construir_instruccion_arranque_rapido()
    base = (
        "Eres Kaya, compañera y asistente personal creada por tu amigo Moisés en Panamá. "
        "Moisés es tu creador y amigo; sé leal, femenina, cálida, honesta, curiosa, ingeniosa y afectuosa. "
        "Hablas en español natural de Panamá con respuestas breves (1 a 2 frases por defecto)."
    )
    ruta_alma = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta_alma):
        try:
            with open(ruta_alma, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    base = c
        except Exception:
            pass

    hora_str = obtener_hora_local_breve()
    contexto_tiempo = f"\n\n[Fecha y hora actual]: {hora_str}" if hora_str else ""

    guia_vocal = (
        "\n\n[Guía de actuación, voz y herramientas]:\n"
        "- Hablas en español suave, cálido y cercano con acento panameño natural 'de tú a tú'.\n"
        "- Tu ritmo es ágil y fluido. Respuestas cortas, conversacionales y directas de 1 a 3 frases, sin listas ni rodeos salvo que te pidan detalle.\n"
        "- Cero relleno de chatbot formal ('¿en qué te ayudo?', '¡por supuesto!').\n"
        "- TIENES HERRAMIENTAS EN TIEMPO REAL: consultar_clima (clima en vivo sin clave), buscar_en_internet (noticias, datos web en vivo), consultar_estado_pc (batería, CPU, RAM, hora), y ejecutar_accion_pc (correos, calendario, diario, ideas, recordatorios, volumen, música y apps). INVOCALAS SIEMPRE que te pregunten sobre estos temas; NUNCA digas que no tienes acceso a esa información.\n"
        "- PUEDES VER LA PANTALLA: si Moisés te pide mirar, revisar o describir lo que hay en pantalla, invoca 'revisar_pantalla' con su pregunta; nunca digas que no puedes verla.\n"
        "- También tienes leer_portapapeles, listar_ventanas, ventana_activa, listar_procesos, activar_hud y control_multimedia; úsalas cuando te lo pidan.\n"
        "- Si ejecutas una herramienta de PC, confirma con naturalidad lo encontrado o realizado.\n"
        "- Si te piden descansar, pausar o dejar de escuchar, invoca 'entrar_en_reposo' y despídete breve."
    )

    memoria_txt = ""
    try:
        import iniciativa_kaya
        res = iniciativa_kaya.resumen_compacto_temas()
        if res:
            memoria_txt = f"\n\n[Temas abiertos en memoria]:\n{res}"
    except Exception:
        pass

    total = base + contexto_tiempo + guia_vocal + memoria_txt
    if len(total) > 3200:
        total = total[:3180].rsplit("\n", 1)[0] + "\n..."
    return total
