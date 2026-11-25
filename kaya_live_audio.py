"""Manejo de audio PCM y configuración de sesión para Gemini Live."""
import datetime
import math
import os
import struct
import time
from typing import Optional

RATE_ENTRADA = 16000
RATE_SALIDA = 24000
CHANNELS = 1
CHUNK_ENTRADA_MS = 50
MAX_COLA_ENTRADA = 60
TIMEOUT_SILENCIO_DEFECTO = 75.0

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
                self.eco_cola_ms = float(os.environ.get("KAYA_ECO_COLA_MS", "450"))
            except Exception:
                self.eco_cola_ms = 450.0
        else:
            self.eco_cola_ms = float(eco_cola_ms)

        self.cola_salida = cola_salida
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = 0.0

    def marcar_inicio_escritura(self):
        """Marca inicio de extracción o escritura al parlante."""
        self._reproduciendo_salida = True
        self._ultimo_fin_salida = time.monotonic()

    def marcar_fin_escritura(self):
        """Marca fin exacto de escritura al parlante tras el write()."""
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = time.monotonic()

    def marcar_encolado_salida(self):
        """Actualiza marca temporal al recibir audio nuevo para cubrir la brecha inicial."""
        self._ultimo_fin_salida = time.monotonic()

    def esta_en_ventana_eco(self) -> bool:
        """Devuelve True si está reproduciendo o dentro de la ventana de cola antieco."""
        if self.modo_audifonos:
            return False
        if self._reproduciendo_salida:
            return True
        if self.cola_salida is not None and not getattr(self.cola_salida, "empty", lambda: True)():
            return True
        cola_s = self.eco_cola_ms / 1000.0
        return (time.monotonic() - self._ultimo_fin_salida) < cola_s

    def filtrar_chunk_entrada(self, chunk: bytes) -> tuple[bytes, bool]:
        """Devuelve (chunk_resultado, silenciado).
        Si está en ventana eco: sustituye por silencio del mismo tamaño y silenciado=True."""
        if not chunk:
            return b"", False
        if self.esta_en_ventana_eco():
            return bytes(len(chunk)), True
        return chunk, False

    def registrar_info_inicio(self):
        """Emite una línea informativa al iniciar audio."""
        if self.modo_audifonos:
            print("[LIVE][AUDIO] Compuerta antieco: DESACTIVADA (modo audífonos).", flush=True)
        else:
            print(f"[LIVE][AUDIO] Compuerta antieco: ACTIVA (parlantes, ventana={int(self.eco_cola_ms)}ms).", flush=True)


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
