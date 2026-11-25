"""Manejo de audio PCM y configuración de sesión para Gemini Live."""
import math
import os
import struct

RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
TIMEOUT_SILENCIO_DEFECTO = 75.0


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


def construir_instruccion_sistema():
    base = "Eres Kaya, asistente personal panameña, cálida, ingeniosa, hablas en español natural con respuestas breves."
    ruta_alma = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    if os.path.exists(ruta_alma):
        try:
            with open(ruta_alma, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    base = c
        except Exception:
            pass

    guia_vocal = (
        "\n\n[Guía de actuación vocal]\n"
        "- Hablas en español latinoamericano suave, cálido y cercano con acento panameño natural.\n"
        "- Tu ritmo es ágil y fluido. Responde en 1 a 3 frases concisas para evitar monólogos.\n"
        "- Si ejecutas una herramienta, confirma brevemente lo encontrado sin rodeos."
    )

    memoria_txt = ""
    try:
        import iniciativa_kaya
        res = iniciativa_kaya.resumen_compacto_temas()
        if res:
            memoria_txt = f"\n\n[Temas abiertos en memoria]:\n{res}"
    except Exception:
        pass

    return base + guia_vocal + memoria_txt
