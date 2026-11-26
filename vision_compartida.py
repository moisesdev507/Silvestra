"""Visión de pantalla compartida para Gemini Live y el motor clásico.

Captura la pantalla en memoria y la analiza con el SDK google-genai multimodal.
Reutiliza la captura, el modo privado y la limpieza de voz de vision_pantalla.
Si el SDK no responde, cae al analizador REST existente. Nunca escribe en disco.
"""
import base64
import threading
from typing import Optional

_bloqueo = threading.RLock()
PREGUNTA_DEFECTO = (
    "Describe qué hay actualmente en la pantalla y qué está haciendo el usuario"
)
MODELOS_GENAI = (
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
)


def _clave() -> str:
    try:
        import config
        return str(getattr(config, "CLAVE_GOOGLE", "") or "").strip()
    except Exception:
        return ""


def _modelos():
    """Modelos Gemini candidatos, sin audio ni generación de imágenes."""
    vistos, salida = set(), []
    for modelo in MODELOS_GENAI:
        if modelo not in vistos:
            vistos.add(modelo)
            salida.append(modelo)
    try:
        import config
        for modelo in (getattr(config, "MODELOS_VISION", None) or []):
            if not isinstance(modelo, str):
                continue
            nombre = modelo.strip()
            bajo = nombre.lower()
            if not bajo.startswith("gemini-"):
                continue
            if any(x in bajo for x in ("audio", "tts", "image", "imagen")):
                continue
            if nombre not in vistos:
                vistos.add(nombre)
                salida.append(nombre)
    except Exception:
        pass
    return salida


def _prompt(pregunta: str) -> str:
    return (
        f"Petición del usuario: {pregunta}\n"
        "Eres Kaya, asistente personal de Moisés. Observa la captura de pantalla y "
        "responde en español natural, listo para hablar, en 2 o 3 frases cortas. "
        "Di qué ventana o aplicación está abierta, qué texto o error se ve y qué parece "
        "estar haciendo el usuario. Sin markdown, sin listas, sin URLs ni código."
    )


def _analizar_genai(clave: str, b64_img: str, prompt: str, modelo: str) -> str:
    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=clave, http_options={"api_version": "v1beta"})
    datos = base64.b64decode(b64_img)
    respuesta = cliente.models.generate_content(
        model=modelo,
        contents=[
            prompt,
            types.Part.from_bytes(data=datos, mime_type="image/jpeg"),
        ],
    )
    return str(getattr(respuesta, "text", "") or "").strip()


def _con_timeout(fn, timeout: float = 14.0):
    """Ejecuta fn en un hilo daemon para no colgar el audio de Gemini Live."""
    resultado = {}

    def _correr():
        try:
            resultado["valor"] = fn()
        except Exception as exc:
            resultado["error"] = exc

    hilo = threading.Thread(target=_correr, daemon=True, name="vision-pantalla")
    hilo.start()
    hilo.join(timeout)
    if hilo.is_alive():
        raise TimeoutError("La visión de pantalla tardó demasiado.")
    if "error" in resultado:
        raise resultado["error"]
    return resultado.get("valor", "")


def revisar_pantalla(pregunta: Optional[str] = None, app=None) -> str:
    """Captura la pantalla y la analiza respondiendo a la pregunta del usuario."""
    import vision_pantalla as vp

    if vp.es_modo_privado(app):
        return "No puedo mirar la pantalla mientras el modo Privado está activo."
    pregunta = str(pregunta or "").strip() or PREGUNTA_DEFECTO
    with _bloqueo:
        b64_img = vp.capturar_pantalla_b64(ancho_max=1024, calidad=65)
    if not b64_img:
        return "No pude capturar la pantalla en este momento."

    clave = _clave()
    if clave:
        prompt = _prompt(pregunta)
        for modelo in _modelos():
            try:
                texto = _con_timeout(
                    lambda m=modelo: _analizar_genai(clave, b64_img, prompt, m)
                )
                limpio = vp._limpiar_para_voz(texto)
                if limpio:
                    return limpio
            except Exception:
                continue

    try:
        return vp.analizar_pantalla(pregunta)
    except Exception:
        return "No pude obtener una respuesta visual de la pantalla en este momento."


def detectar_peticion_vision(texto) -> bool:
    """Delega la detección de órdenes de pantalla al módulo existente."""
    import vision_pantalla as vp
    return bool(vp.detectar_peticion_vision(texto))


__all__ = [
    "PREGUNTA_DEFECTO",
    "revisar_pantalla",
    "detectar_peticion_vision",
]
