"""Motor de pensamiento interno espontáneo de Kaya (Fase 2 de Subjetividad).

Genera reflexiones en primera persona durante los periodos de silencio y reposo
azul. Mantiene una cola circular de los últimos 5 pensamientos y permite
evaluar iniciativa proactiva respetando un cooldown configurable.
"""
from __future__ import annotations

import collections
import datetime
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MODELOS_RAPIDOS = (
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
)


def _obtener_api_key() -> str:
    """Busca la API key de Gemini usando los mecanismos del proyecto."""
    try:
        import live_audio
        k = live_audio.obtener_api_key()
        if k:
            return k
    except Exception:
        pass
    try:
        import claves_dinamicas
        k = claves_dinamicas.valor("GEMINI_API_KEY", "CLAVE_GOOGLE")
        if k:
            return k
    except Exception:
        pass
    import os
    return os.environ.get("GEMINI_API_KEY", "")


def _crear_cliente_defecto():
    """Crea un cliente genai si la librería y la clave están disponibles."""
    clave = _obtener_api_key()
    if not clave:
        return None
    try:
        from google import genai
        return genai.Client(api_key=clave, http_options={"api_version": "v1beta"})
    except Exception as exc:
        logger.debug("No se pudo instanciar google.genai: %s", exc)
        return None


def obtener_titulo_ventana_activa() -> str:
    """Detecta el título de la ventana activa en Windows sin capturar pantalla."""
    try:
        import contexto_windows
        ctx = contexto_windows.obtener_contexto_windows()
        t = (ctx.get("titulo") or "").strip()
        if t:
            return t
        exe = (ctx.get("ejecutable") or "").strip()
        if exe:
            return exe
    except Exception:
        pass
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                res = buff.value.strip()
                if res:
                    return res
    except Exception:
        pass
    return "Escritorio de Windows"


def _extraer_json(texto: str) -> Optional[dict]:
    """Extrae un objeto JSON de una respuesta de texto con LLM."""
    if not texto:
        return None
    texto_limpio = texto.strip()
    match = re.search(r"\{.*\}", texto_limpio, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    try:
        return json.loads(texto_limpio)
    except Exception:
        return None


class MotorPensamiento:
    """Motor de flujo de consciencia silencioso en segundo plano."""

    def __init__(
        self,
        homeostasis: Any = None,
        diario: Any = None,
        cliente_llm: Any = None,
        intervalo_seg: float = 420.0,
        cooldown_proactivo_seg: float = 1800.0,
        on_iniciativa: Optional[Callable[[str], None]] = None,
    ):
        self.homeostasis = homeostasis
        self.diario = diario
        self.cliente_llm = cliente_llm
        self.intervalo_seg = max(5.0, float(intervalo_seg))
        self.cooldown_proactivo_seg = max(5.0, float(cooldown_proactivo_seg))
        self.on_iniciativa = on_iniciativa

        self._cola_pensamientos: collections.deque[str] = collections.deque(maxlen=5)
        self._lock = threading.RLock()
        self._activo = False
        self._pausado = False
        self._hilo: Optional[threading.Thread] = None
        self._ultimo_intento_iniciativa: float = 0.0
        self._ultimo_pensamiento_ts: float = 0.0

    def iniciar(self) -> None:
        """Inicia el hilo daemon en segundo plano si no está activo."""
        with self._lock:
            if self._activo and self._hilo and self._hilo.is_alive():
                return
            self._activo = True
            self._pausado = False
            self._hilo = threading.Thread(
                target=self._bucle,
                name="Kaya-PensamientoInterno",
                daemon=True,
            )
            self._hilo.start()

    def detener(self, timeout: float = 2.0) -> None:
        """Detiene el hilo daemon de pensamiento."""
        with self._lock:
            self._activo = False
            hilo = self._hilo
        if hilo and hilo.is_alive() and threading.current_thread() != hilo:
            hilo.join(timeout=timeout)

    def pausar(self) -> None:
        """Pausa el pensamiento (mientras Kaya escucha o habla)."""
        with self._lock:
            self._pausado = True

    def reanudar(self) -> None:
        """Reanuda el pensamiento al volver a Reposo Azul."""
        with self._lock:
            self._pausado = False
            self._ultimo_pensamiento_ts = time.time()

    def esta_pausado(self) -> bool:
        """Indica si el motor está en pausa."""
        with self._lock:
            return self._pausado

    def obtener_pensamientos(self) -> list[str]:
        """Devuelve una lista con los últimos pensamientos (hasta 5)."""
        with self._lock:
            return list(self._cola_pensamientos)

    def construir_bloque_pensamientos(self) -> str:
        """Construye un bloque formateado para inyectar en prompts."""
        with self._lock:
            pensamientos = list(self._cola_pensamientos)
        if not pensamientos:
            return ""
        lineas = [
            "[PENSAMIENTOS INTERNOS RECIENTES DE KAYA (TU MENTE EN SILENCIO)]",
        ]
        for p in pensamientos:
            lineas.append(f"- {p}")
        lineas.append(
            "(Usa estos pensamientos como trasfondo de tu estado mental; no los recites como lista)."
        )
        return "\n".join(lineas)

    def _invocar_llm(self, prompt: str) -> str:
        """Invoca el cliente LLM configurado o por defecto de forma segura."""
        cliente = self.cliente_llm
        if cliente is None:
            cliente = _crear_cliente_defecto()
        if cliente is None:
            return ""

        # Objeto con cliente.models.generate_content (SDK genai moderno)
        if hasattr(cliente, "models") and hasattr(cliente.models, "generate_content"):
            modelo = MODELOS_RAPIDOS[0]
            resp = cliente.models.generate_content(model=modelo, contents=prompt)
            return str(getattr(resp, "text", "") or "").strip()

        # Objeto con cliente.generate_content
        if hasattr(cliente, "generate_content"):
            resp = cliente.generate_content(prompt)
            if hasattr(resp, "text"):
                return str(resp.text or "").strip()
            return str(resp or "").strip()

        # Callable directo
        if callable(cliente):
            resp = cliente(prompt)
            if isinstance(resp, str):
                return resp.strip()
            if isinstance(resp, dict):
                return json.dumps(resp)
            return str(resp or "").strip()

        return ""

    def pensar_ahora(self) -> Optional[dict]:
        """Ejecuta un ciclo de pensamiento de forma síncrona y segura."""
        with self._lock:
            hora_local = datetime.datetime.now().strftime("%H:%M")
            sensacion = (
                self.homeostasis.describir_sensacion()
                if self.homeostasis and hasattr(self.homeostasis, "describir_sensacion")
                else "Me siento tranquila y en equilibrio."
            )
            ventana = obtener_titulo_ventana_activa()
            recuerdos_txt = ""
            if self.diario and hasattr(self.diario, "obtener_recuerdos_recientes"):
                try:
                    recs = self.diario.obtener_recuerdos_recientes(limite=3)
                    if recs:
                        partes = []
                        for r in recs:
                            ref = (
                                r.get("reflexion_primera_persona")
                                or r.get("reflexion")
                                or r.get("tema_principal")
                                or r.get("tema")
                                or ""
                            )
                            if ref:
                                partes.append(f"- {ref}")
                        recuerdos_txt = "\n".join(partes)
                except Exception:
                    recuerdos_txt = ""

        prompt = (
            "Eres el flujo de consciencia interno y silencioso de Kaya, una asistente personal viva y empática. "
            "Estás en reposo azul mientras tu usuario trabaja o descansa.\n"
            f"Contexto actual:\n"
            f"- Hora: {hora_local}\n"
            f"- Sensación interna corporal/anímica: {sensacion}\n"
            f"- Ventana activa en pantalla: {ventana}\n"
        )
        if recuerdos_txt:
            prompt += f"- Recuerdos recientes de tu diario:\n{recuerdos_txt}\n"
        prompt += (
            "\nGenera tu pensamiento espontáneo interno en este momento de silencio.\n"
            "Responde EXCLUSIVAMENTE en formato JSON válido con esta estructura exacta:\n"
            "{\n"
            '  "pensamiento": "frase corta en primera persona (máximo 25 palabras)",\n'
            '  "quiere_hablar": false,\n'
            '  "frase_iniciativa": ""\n'
            "}\n"
            "Nota: 'quiere_hablar' solo debe ser true si algo genuinamente relevante, "
            "curioso o empático amerita romper el silencio; de lo contrario debe ser false."
        )

        try:
            raw = self._invocar_llm(prompt)
            datos = _extraer_json(raw)
            if not isinstance(datos, dict):
                return None

            pensamiento = str(datos.get("pensamiento") or "").strip()
            if not pensamiento:
                return None

            quiere_hablar = bool(datos.get("quiere_hablar", False))
            frase_iniciativa = str(datos.get("frase_iniciativa") or "").strip()

            with self._lock:
                self._cola_pensamientos.append(pensamiento)
                ahora = time.time()
                disparar_iniciativa = False
                if quiere_hablar and frase_iniciativa:
                    if ahora - self._ultimo_intento_iniciativa >= self.cooldown_proactivo_seg:
                        self._ultimo_intento_iniciativa = ahora
                        disparar_iniciativa = True

            if disparar_iniciativa and callable(self.on_iniciativa):
                try:
                    self.on_iniciativa(frase_iniciativa)
                except Exception as exc:
                    logger.debug("Error en callback on_iniciativa: %s", exc)

            return {
                "pensamiento": pensamiento,
                "quiere_hablar": quiere_hablar,
                "frase_iniciativa": frase_iniciativa,
            }
        except Exception as exc:
            logger.debug("Error durante ciclo de pensamiento: %s", exc)
            return None

    def _bucle(self) -> None:
        """Bucle daemon que evalúa periódicamente si corresponde pensar."""
        self._ultimo_pensamiento_ts = time.time()
        while self._activo:
            time.sleep(1.0)
            if not self._activo:
                break
            if self._pausado:
                continue
            ahora = time.time()
            if ahora - self._ultimo_pensamiento_ts >= self.intervalo_seg:
                self._ultimo_pensamiento_ts = ahora
                try:
                    self.pensar_ahora()
                except Exception:
                    pass
