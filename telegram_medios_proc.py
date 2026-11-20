"""Procesamiento de visión multimodal, audio y sanitización para Telegram en Silvestra."""
from __future__ import annotations

import base64
import io
import re
from typing import Any, Optional
from PIL import Image
import requests

import config


def sanitizar_privacidad(texto: str) -> str:
    """Elimina tokens, claves de API, rutas locales y archivos de configuración."""
    if not texto:
        return ""
    s = str(texto)
    s = re.sub(r"gsk_[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-or-v1-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"AQ\.[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"\d{8,12}:[A-Za-z0-9_-]{25,50}", "[TOKEN_PROTEGIDO]", s)
    s = re.sub(r"[A-Za-z]:\\[^\s\"'\n<>*|?]+", "[RUTA_LOCAL]", s)
    s = re.sub(r"/(?:[\w.-]+/)+[\w.-]+", "[RUTA_LOCAL]", s)
    s = re.sub(r"(?i)\bconfig\.py\b", "[configuración]", s)
    s = re.sub(r"(?i)\.env\b", "[configuración]", s)
    return s


def transcribir_audio(app: Any, audio_bytes: bytes, nombre: str = "nota.ogg") -> Optional[str]:
    """Transcribe un archivo de voz/audio en memoria usando Whisper de Groq."""
    try:
        r = app.cliente.audio.transcriptions.create(
            file=(nombre, audio_bytes),
            model=getattr(config, "MODELO_VOZ", "whisper-large-v3-turbo"),
            language="es",
            prompt="Conversación en español.",
            timeout=15.0,
        )
        return (r.text or "").strip()
    except Exception as e:
        print(f"[telegram_medios] Whisper falló: {e}", flush=True)
        return None


def _post_vision(url: str, clave: str, modelo: str, data_url: str, sistema: str, consulta: str, timeout: int = 20) -> Optional[str]:
    """Llamada a endpoints compatibles OpenAI para visión multimodal."""
    try:
        headers = {"Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
        cuerpo = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": consulta},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": 300,
            "temperature": 0.6,
        }
        r = requests.post(url, headers=headers, json=cuerpo, timeout=timeout)
        if r.status_code == 200:
            txt = r.json()["choices"][0]["message"].get("content")
            if txt:
                return txt.strip()
    except Exception as e:
        print(f"[telegram_medios] Visión en {modelo} falló: {e}", flush=True)
    return None


def _consultar_vision_multillm(app: Any, data_url: str, sistema: str, consulta: str) -> Optional[str]:
    """Consulta modelos de visión con failover: Groq -> Google Gemini -> OpenRouter."""
    modelos_groq = [config.MODELO_VISION] + [m for m in getattr(config, "MODELOS_VISION", []) if m != config.MODELO_VISION]
    for m in modelos_groq:
        try:
            r = app.cliente.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": sistema},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": consulta},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                max_tokens=300,
                temperature=0.6,
                timeout=20.0,
            )
            if r.choices and r.choices[0].message.content:
                print(f"[tiempo] telegram_vision proveedor=Groq modelo={m}", flush=True)
                return r.choices[0].message.content.strip()
        except Exception as e:
            print(f"[telegram_medios] Groq vision {m} falló: {e}", flush=True)

    clave_g = getattr(config, "CLAVE_GOOGLE", "").strip()
    if clave_g:
        url_g = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        for mod in ["gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-flash-latest"]:
            txt = _post_vision(url_g, clave_g, mod, data_url, sistema, consulta, 20)
            if txt:
                print(f"[tiempo] telegram_vision proveedor=Google modelo={mod}", flush=True)
                return txt

    clave_or = getattr(config, "CLAVE_OPENROUTER", "").strip()
    if clave_or:
        url_or = "https://openrouter.ai/api/v1/chat/completions"
        txt = _post_vision(url_or, clave_or, "nvidia/nemotron-3.5-super-vl:free", data_url, sistema, consulta, 25)
        if txt:
            print("[tiempo] telegram_vision proveedor=OpenRouter", flush=True)
            return txt
    return None


def analizar_imagen_vision(app: Any, foto_bytes: bytes, pregunta: Optional[str] = None) -> str:
    """Reduce la imagen en memoria y consulta al modelo de visión."""
    try:
        img = Image.open(io.BytesIO(foto_bytes))
        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            esc = min(max_dim / img.width, max_dim / img.height)
            img = img.resize((max(1, int(img.width * esc)), max(1, int(img.height * esc))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        data_url = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    except Exception as e:
        print(f"[telegram_medios] Error procesando imagen en memoria: {e}", flush=True)
        return "No pude abrir o procesar la imagen enviada."

    consulta = (pregunta or "").strip() or "describe esta imagen y dime si ves algún problema"
    nombre = getattr(app.memoria, "nombre", "Silvestra")
    creador = getattr(app.memoria, "creador", "Moisés")
    sistema = (
        f"Eres {nombre}, asistente creada por {creador} en Panamá.\n"
        "Estás viendo una imagen que te enviaron por Telegram.\n"
        "Responde de forma concisa, cálida y natural en español de Panamá (1 a 3 frases).\n"
        "Regla de privacidad: jamás leas ni repitas contraseñas, claves, tokens ni números de tarjetas visibles en la foto."
    )
    resp = _consultar_vision_multillm(app, data_url, sistema, consulta)
    if not resp:
        return "No pude analizar la imagen en este momento, por favor intenta de nuevo."
    return resp.replace("*", "").replace("- ", "").replace("\n", " ").strip("\"' ")


def verificar_privacidad_pantalla(app: Any, b64_jpeg: str) -> tuple[bool, str]:
    """Comprueba si una captura de pantalla contiene claves o contraseñas visibles."""
    sistema = (
        "Eres un analizador estricto de seguridad informática y privacidad.\n"
        "Revisa la captura de pantalla y determina si muestra contraseñas, claves secretas, "
        "tokens de autenticación (gsk_, sk-, etc.) o datos confidenciales expuestos en texto claro.\n"
        "Regla obligatoria: si detectas contraseñas o claves secretas visibles, responde exactamente: PRIVADO: <motivo breve>.\n"
        "Si NO hay datos confidenciales expuestos, responde exactamente: SEGURO."
    )
    data_url = f"data:image/jpeg;base64,{b64_jpeg}"
    resp = _consultar_vision_multillm(app, data_url, sistema, "analiza si es seguro enviar esta captura")
    if not resp:
        return False, "No se pudo verificar la privacidad de la pantalla con el modelo de visión."
    if resp.strip().upper().startswith("PRIVADO"):
        return False, resp.strip()
    return True, "Captura verificada y segura."
