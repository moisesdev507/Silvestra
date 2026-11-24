"""STT principal con Deepgram Nova; devuelve None para caer a Whisper.

La clave se lee de config.py con respaldo al entorno en cada llamada: nunca se imprime ni se guarda.
"""
import os
import threading
import time

import config
import httpx

URL = "https://api.deepgram.com/v1/listen"
KEYTERM = "Lyris:5"
TIMEOUT = 6.0
_bloqueo = threading.RLock()
_desactivado = False


def reiniciar():
    """Rehabilita Deepgram (útil para pruebas o un nuevo arranque)."""
    global _desactivado
    with _bloqueo:
        _desactivado = False


def esta_activo():
    with _bloqueo:
        return not _desactivado


def _desactivar(codigo):
    """Desactiva Deepgram por el resto de la sesión; solo registra el código HTTP."""
    global _desactivado
    with _bloqueo:
        _desactivado = True
    print(f"[oido] Deepgram HTTP {codigo}: desactivado por el resto de la sesion", flush=True)


def transcribir(wav_bytes):
    """Devuelve (texto, duracion) o None si no hay clave, falla o está desactivado."""
    clave = str(getattr(config, "DEEPGRAM_API_KEY", "")
                or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
    if not clave or not wav_bytes or not esta_activo():
        return None
    modelo = str(getattr(config, "DEEPGRAM_MODEL", "")
                 or os.environ.get("DEEPGRAM_MODEL", "nova-3")).strip() or "nova-3"
    idioma = str(os.environ.get("LYRIS_DEEPGRAM_LANG", "es")).strip() or "es"
    parametros = {"model": modelo, "language": idioma, "smart_format": "true",
                  "keyterm": KEYTERM}
    comun = {"headers": {"Authorization": f"Token {clave}",
                         "Content-Type": "audio/wav"},
             "content": wav_bytes, "timeout": TIMEOUT}
    t0 = time.time()
    try:
        respuesta = httpx.post(URL, params=parametros, **comun)
        if respuesta.status_code == 400:
            print("[oido] Deepgram 400 con keyterm; reintentando sin impulso", flush=True)
            parametros = {k: v for k, v in parametros.items() if k != "keyterm"}
            respuesta = httpx.post(URL, params=parametros, **comun)
    except httpx.TimeoutException:
        print("[tiempo] deepgram=timeout", flush=True)
        return None
    except Exception:
        print("[tiempo] deepgram=error", flush=True)
        return None

    print(f"[tiempo] deepgram={time.time() - t0:.2f}s", flush=True)
    codigo = respuesta.status_code
    if codigo in (401, 402, 403):
        _desactivar(codigo)
        return None
    if codigo != 200:
        print(f"[oido] Deepgram HTTP {codigo}: usando Whisper", flush=True)
        return None
    try:
        datos = respuesta.json()
        canales = datos.get("results", {}).get("channels", [])
        texto = canales[0]["alternatives"][0].get("transcript", "")
        segundos = float(datos.get("metadata", {}).get("duration") or 0.0)
    except Exception:
        return None
    texto = " ".join(str(texto or "").split())
    return (texto, segundos) if texto else None
