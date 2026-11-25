"""Manejo de audio PCM y configuración de sesión para Gemini Live."""
import datetime
import math
import os
import struct

RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
TIMEOUT_SILENCIO_DEFECTO = 75.0

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def calcular_energia_pcm16(pcm_bytes: bytes) -> float:
    """Calcula nivel de volumen normalizado (0.0 a 1.0) a partir de PCM 16-bit mono."""
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


def obtener_api_key():
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


def obtener_hora_local_breve():
    try:
        now = datetime.datetime.now().astimezone()
        dia_sem = DIAS[now.weekday()]
        h12 = now.hour % 12 or 12
        minu = f"{now.minute:02d}"
        meridiano = "p. m." if now.hour >= 12 else "a. m."
        return f"Hoy es {dia_sem} {now.day} de {MESES[now.month-1]} de {now.year}, {h12}:{minu} {meridiano} (hora local)."
    except Exception:
        return ""


def construir_instruccion_sistema():
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
        "\n\n[Guía de actuación y voz]:\n"
        "- Hablas en español latinoamericano suave, cálido y cercano con acento panameño natural.\n"
        "- Tu ritmo es ágil y fluido. Respuestas directas de 1 a 2 frases para evitar monólogos.\n"
        "- Cero relleno de chatbot formal ('¿en qué te ayudo?', '¡por supuesto!').\n"
        "- Si ejecutas una herramienta de PC, confirma con naturalidad lo encontrado o realizado."
    )

    memoria_txt = ""
    try:
        import kaya_live_puente
        memoria_txt = kaya_live_puente.cargar_contexto_memoria_live()
    except Exception:
        try:
            import iniciativa_kaya
            res = iniciativa_kaya.resumen_compacto_temas()
            if res:
                memoria_txt = f"\n\n[Temas abiertos en memoria]:\n{res}"
        except Exception:
            pass

    total = base + contexto_tiempo + guia_vocal + memoria_txt
    if len(total) > 2200:
        total = total[:2180].rsplit("\n", 1)[0] + "\n..."
    return total
