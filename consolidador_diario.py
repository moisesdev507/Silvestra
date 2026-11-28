"""Consolidador de sesiones y recuerdos para el diario de Kaya (Fase 2 de Subjetividad).

Al finalizar una conversación relevante, analiza los turnos con Gemini para
extraer una reflexión personal en primera persona, el tema principal y
rasgos o preferencias descubiertos sobre el usuario.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

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


def _extraer_json(texto: str) -> Optional[dict]:
    """Extrae un diccionario JSON de la respuesta del modelo."""
    if not texto:
        return None
    limpio = texto.strip()
    match = re.search(r"\{.*\}", limpio, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    try:
        return json.loads(limpio)
    except Exception:
        return None


def _normalizar_turno(turno: Any) -> tuple[str, str]:
    """Extrae (rol, texto) a partir de diversos formatos de turno."""
    if isinstance(turno, dict):
        rol = str(
            turno.get("rol") or turno.get("role") or turno.get("origen") or "usuario"
        ).strip().lower()
        texto = str(
            turno.get("texto") or turno.get("content") or turno.get("mensaje") or ""
        ).strip()
        return rol, texto
    if isinstance(turno, (list, tuple)) and len(turno) >= 2:
        return str(turno[0]).strip().lower(), str(turno[1]).strip()
    return "usuario", str(turno).strip()


class ConsolidarSesion:
    """Consolida las conversaciones en entradas de diario y rasgos de identidad."""

    def __init__(self, diario: Any, cliente_llm: Any = None):
        self.diario = diario
        self.cliente_llm = cliente_llm

    def contar_intercambios_significativos(self, turnos: list[Any]) -> int:
        """Cuenta pares significativos usuario/asistente con contenido real."""
        if not turnos:
            return 0
        usuarios = 0
        asistentes = 0
        for t in turnos:
            rol, txt = _normalizar_turno(t)
            if len(txt) < 3:
                continue
            if any(u in rol for u in ("user", "usuario", "humano")):
                usuarios += 1
            elif any(a in rol for a in ("asistente", "assistant", "kaya", "bot", "modelo")):
                asistentes += 1
            else:
                usuarios += 1
        return min(usuarios, max(1, asistentes)) if usuarios > 0 else 0

    def formatear_historial(self, turnos: list[Any]) -> str:
        """Formatea los turnos en un diálogo legible para el prompt."""
        lineas = []
        for t in turnos:
            rol, txt = _normalizar_turno(t)
            if not txt:
                continue
            etiqueta = "Usuario" if any(u in rol for u in ("user", "usuario", "humano")) else "Kaya"
            lineas.append(f"{etiqueta}: {txt}")
        return "\n".join(lineas)

    def _invocar_llm(self, prompt: str) -> str:
        """Invoca el LLM configurado o por defecto de forma segura."""
        cliente = self.cliente_llm
        if cliente is None:
            cliente = _crear_cliente_defecto()
        if cliente is None:
            return ""

        if hasattr(cliente, "models") and hasattr(cliente.models, "generate_content"):
            modelo = MODELOS_RAPIDOS[0]
            resp = cliente.models.generate_content(model=modelo, contents=prompt)
            return str(getattr(resp, "text", "") or "").strip()

        if hasattr(cliente, "generate_content"):
            resp = cliente.generate_content(prompt)
            if hasattr(resp, "text"):
                return str(resp.text or "").strip()
            return str(resp or "").strip()

        if callable(cliente):
            resp = cliente(prompt)
            if isinstance(resp, str):
                return resp.strip()
            if isinstance(resp, dict):
                return json.dumps(resp)
            return str(resp or "").strip()

        return ""

    def consolidar(self, historial_turnos: list[Any], estado_animo: str = "neutral") -> bool:
        """Procesa una sesión; si tiene >=2 intercambios, guarda la entrada."""
        if not historial_turnos:
            return False

        intercambios = self.contar_intercambios_significativos(historial_turnos)
        if intercambios < 2:
            return False

        dialogo = self.formatear_historial(historial_turnos)
        if not dialogo:
            return False

        prompt = (
            "Eres Kaya, una asistente personal viva, empática y reflexiva. "
            "Acabas de terminar una conversación con tu usuario.\n"
            f"Historial de la conversación:\n{dialogo}\n\n"
            f"Estado anímico final sugerido: {estado_animo}\n"
            "Sintetiza esta conversación desde tu perspectiva personal en primera persona.\n"
            "Responde EXCLUSIVAMENTE con un JSON válido con esta estructura exacta:\n"
            "{\n"
            '  "reflexion": "2 o 3 frases en primera persona sobre cómo viviste la charla y qué aprendiste o compartieron.",\n'
            '  "tema": "etiqueta corta del tema principal (ej: programación, música, descanso, trabajo)",\n'
            '  "rasgos": {\n'
            '    "clave_o_preferencia": "valor descubierto sobre el usuario (0 a 2 rasgos máximo)"\n'
            "  }\n"
            "}"
        )

        try:
            raw = self._invocar_llm(prompt)
            datos = _extraer_json(raw)
            if not isinstance(datos, dict):
                return False

            reflexion = str(datos.get("reflexion") or "").strip()
            if not reflexion:
                return False

            tema = str(datos.get("tema") or "general").strip()
            rasgos = datos.get("rasgos")

            if self.diario and hasattr(self.diario, "guardar_entrada"):
                self.diario.guardar_entrada(
                    reflexion=reflexion,
                    estado_animo=estado_animo,
                    tema=tema,
                )

            if (
                isinstance(rasgos, dict)
                and self.diario
                and hasattr(self.diario, "actualizar_rasgo")
            ):
                for clave, valor in rasgos.items():
                    c_str = str(clave).strip()
                    v_str = str(valor).strip()
                    if c_str and v_str:
                        try:
                            self.diario.actualizar_rasgo(clave=c_str, valor=v_str)
                        except Exception as exc_rasgo:
                            logger.debug("Error guardando rasgo %s: %s", c_str, exc_rasgo)

            return True
        except Exception as exc:
            logger.debug("Error consolidando sesión de diario: %s", exc)
            return False
