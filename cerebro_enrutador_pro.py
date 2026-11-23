"""Carril Pro: cadena de modelos verificados en vivo con fallback automático.

Los modelos de PRO_CHAIN se comprobaron con una sonda real (HTTP 200 y
streaming) antes de fijarlos. No se usan IDs muertos ni modelos de pago
sin saldo. El orden prioriza calidad de razonamiento y luego velocidad.
"""
import json
import os

import config

MAX_TOKENS_PRO = 1500
TIMEOUT_PRO = 20.0

PRO_CHAIN = (
    {
        "proveedor": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "modelo": "nvidia/nemotron-3-ultra-550b-a55b",
        "clave_attr": "CLAVE_NVIDIA",
        "env": ("NVIDIA_API_KEY",),
        "stream": True,
    },
    {
        "proveedor": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "modelo": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "clave_attr": "CLAVE_OPENROUTER",
        "env": ("OPENROUTER_API_KEY",),
        "stream": True,
    },
    {
        "proveedor": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "modelo": "openai/gpt-oss-120b",
        "clave_attr": "CLAVE",
        "env": ("GROQ_API_KEY",),
        "stream": True,
    },
    {
        "proveedor": "Google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo": "gemini-flash-lite-latest",
        "clave_attr": "CLAVE_GOOGLE",
        "env": ("GOOGLE_API_KEY",),
        "stream": True,
    },
    {
        "proveedor": "GitHub",
        "base_url": "https://models.github.ai/inference",
        "modelo": "openai/gpt-4o",
        "clave_attr": "CLAVE_GITHUB",
        "env": ("GITHUB_TOKEN",),
        "stream": False,
    },
)


def _leer_clave(entrada):
    """Clave del proveedor: variable de entorno primero, config.py después."""
    for var in entrada.get("env", ()):
        valor = os.environ.get(var)
        if valor and valor.strip():
            return valor.strip()
    attr = entrada.get("clave_attr") or ""
    return str(getattr(config, attr, "") or "").strip()


def _entrada_personalizada():
    """Permite forzar un único modelo propio vía entorno o config.py."""
    clave = str(os.environ.get("PRO_API_KEY") or getattr(config, "PRO_API_KEY", "") or "").strip()
    modelo = str(os.environ.get("PRO_MODELO") or getattr(config, "PRO_MODELO", "") or "").strip()
    base = str(os.environ.get("PRO_BASE_URL") or getattr(config, "PRO_BASE_URL", "") or "").strip()
    if not (clave and modelo and base):
        return None
    return {
        "proveedor": "Personalizado",
        "base_url": base,
        "modelo": modelo,
        "clave": clave,
        "stream": True,
    }


def obtener_cadena_pro():
    """Cadena ordenada de entradas Pro que tienen clave disponible."""
    cadena = []
    personalizada = _entrada_personalizada()
    if personalizada:
        cadena.append(personalizada)
    for entrada in PRO_CHAIN:
        clave = _leer_clave(entrada)
        if not clave:
            continue
        item = dict(entrada)
        item["clave"] = clave
        cadena.append(item)
    return cadena


def verificar_pro_disponible():
    """True si al menos un proveedor Pro de la cadena tiene clave válida."""
    return bool(obtener_cadena_pro())


def obtener_configuracion_pro():
    """Compatibilidad: primera entrada de la cadena + cadena completa."""
    cadena = obtener_cadena_pro()
    primera = cadena[0] if cadena else {}
    return {
        "proveedor": primera.get("proveedor", ""),
        "clave": primera.get("clave", ""),
        "modelo": primera.get("modelo", ""),
        "cadena": cadena,
    }


def _headers(entrada):
    headers = {
        "Authorization": f"Bearer {entrada['clave']}",
        "Content-Type": "application/json",
    }
    if "openrouter" in entrada.get("base_url", ""):
        headers["HTTP-Referer"] = "https://github.com/moises/silvestra"
        headers["X-Title"] = "Silvestra Assistant"
    return headers


def _url(entrada):
    return entrada["base_url"].rstrip("/") + "/chat/completions"


def _extraer_texto(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    mensaje = choices[0].get("message") or {}
    return str(mensaje.get("content") or "")


def _completar_entrada(entrada, mensajes, timeout, max_tokens):
    from sesion_http import obtener_sesion
    payload = {
        "model": entrada["modelo"],
        "messages": mensajes,
        "temperature": 0.5,
        "max_tokens": max_tokens,
    }
    resp = obtener_sesion().post(
        _url(entrada), headers=_headers(entrada), json=payload, timeout=timeout
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    contenido = _extraer_texto(resp.json())
    if not contenido.strip():
        raise RuntimeError("respuesta vacía")
    return contenido


def completar_pro(mensajes, tarea="charla", timeout=TIMEOUT_PRO, max_tokens=None):
    """Intenta la cadena Pro en orden y devuelve la primera respuesta válida."""
    cadena = obtener_cadena_pro()
    if not cadena:
        raise RuntimeError("No hay proveedor Pro configurado.")
    limite_tokens = MAX_TOKENS_PRO if max_tokens is None else max_tokens
    errores = []
    for entrada in cadena:
        try:
            return _completar_entrada(entrada, mensajes, timeout, limite_tokens)
        except Exception as exc:
            errores.append(f"{entrada['proveedor']}/{entrada['modelo']}: {exc}")
    raise RuntimeError("Carril Pro agotado -> " + " | ".join(errores[-3:]))


def _flujo_entrada(entrada, mensajes, al_frase, on_primer_token, on_emocion, timeout, max_tokens):
    from sesion_http import obtener_sesion
    from cerebro_parser import _cortar, _respuesta_parcial, extraer_emocion_parcial

    payload = {
        "model": entrada["modelo"],
        "messages": mensajes,
        "temperature": 0.5,
        "max_tokens": max_tokens,
        "stream": True,
    }
    resp = obtener_sesion().post(
        _url(entrada),
        headers=_headers(entrada),
        json=payload,
        stream=True,
        timeout=(6.0, timeout),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")

    crudo = ""
    emitido = 0
    primer_token = False
    emocion = None
    try:
        for linea_raw in resp.iter_lines(decode_unicode=False):
            if not linea_raw:
                continue
            linea = linea_raw.decode("utf-8", errors="replace").strip()
            if not linea.startswith("data:"):
                continue
            data_str = linea[5:].strip()
            if not data_str or data_str == "[DONE]":
                break
            try:
                evento = json.loads(data_str)
            except Exception:
                continue
            choices = evento.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {}).get("content") or ""
            if not delta:
                continue
            if not primer_token:
                primer_token = True
                if callable(on_primer_token):
                    on_primer_token()
            crudo += delta
            if emocion is None:
                emocion = extraer_emocion_parcial(crudo)
                if emocion and callable(on_emocion):
                    on_emocion(emocion)
            parcial = _respuesta_parcial(crudo)
            if parcial is not None and callable(al_frase):
                frases, emitido = _cortar(parcial, emitido)
                for frase in frases:
                    if frase.strip():
                        al_frase((frase.strip(), emocion) if emocion else frase.strip())
    except Exception:
        if not crudo:
            raise

    if not crudo.strip():
        raise RuntimeError("stream sin contenido")

    if callable(al_frase):
        parcial = _respuesta_parcial(crudo)
        if parcial is not None and len(parcial) > emitido:
            resto = parcial[emitido:].strip()
            if resto:
                al_frase(resto)
    return crudo


def completar_pro_flujo(mensajes, al_frase=None, on_primer_token=None, on_emocion=None,
                        timeout=TIMEOUT_PRO, max_tokens=None):
    """Streaming con fallback entre los proveedores Pro que soportan SSE."""
    cadena = [e for e in obtener_cadena_pro() if e.get("stream", True)]
    if not cadena:
        raise RuntimeError("No hay proveedor Pro con streaming configurado.")
    limite_tokens = MAX_TOKENS_PRO if max_tokens is None else max_tokens
    errores = []
    for entrada in cadena:
        try:
            return _flujo_entrada(
                entrada, mensajes, al_frase, on_primer_token, on_emocion,
                timeout, limite_tokens,
            )
        except Exception as exc:
            errores.append(f"{entrada['proveedor']}/{entrada['modelo']}: {exc}")
    raise RuntimeError("Carril Pro streaming agotado -> " + " | ".join(errores[-3:]))
