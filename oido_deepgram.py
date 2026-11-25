"""STT principal con Deepgram Nova; devuelve None para caer a Whisper.

La clave se lee de config.py con respaldo al entorno en cada llamada: nunca se imprime ni se guarda.
"""
import os
import threading
import time

import config
import httpx

URL = "https://api.deepgram.com/v1/listen"
try:
    from identidad_kaya import KEYTERM_DEEPGRAM as KEYTERM
except Exception:
    KEYTERM = "Kaya:10,Kaia:6,Caya:5"
TIMEOUT = 6.0
CLIP_CORTO_MAX = 1.25
_bloqueo = threading.RLock()
_desactivado = False
_cliente = None


def cerrar_cliente():
    """Cierra el cliente keep-alive (solo al apagar o en pruebas)."""
    global _cliente
    with _bloqueo:
        if _cliente:
            try:
                _cliente.close()
            except Exception:
                pass
        _cliente = None


def _cliente_http():
    """Cliente httpx reutilizable: evita un handshake TLS nuevo por turno."""
    global _cliente
    with _bloqueo:
        if _cliente is None:
            try:
                _cliente = httpx.Client(limits=httpx.Limits(
                    max_keepalive_connections=8, max_connections=16))
            except Exception:
                _cliente = False
        return _cliente


def _post(url, **kwargs):
    """POST con keep-alive; respeta el seam de tests que parchean ``httpx.post``."""
    if hasattr(httpx.post, "call_args") or hasattr(httpx.post, "return_value"):
        return httpx.post(url, **kwargs)
    cliente = _cliente_http()
    if cliente:
        return cliente.post(url, **kwargs)
    return httpx.post(url, **kwargs)


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
    idioma = str(os.environ.get("LYRIS_DEEPGRAM_LANG", "es-419")).strip() or "es-419"
    parametros = {"model": modelo, "language": idioma, "smart_format": "true",
                  "keyterm": KEYTERM}
    comun = {"headers": {"Authorization": f"Token {clave}",
                         "Content-Type": "audio/wav"},
             "content": wav_bytes, "timeout": TIMEOUT}
    t0 = time.time()
    try:
        respuesta = _post(URL, params=parametros, **comun)
        if respuesta.status_code == 400:
            print("[oido] Deepgram 400 con keyterm; reintentando sin impulso", flush=True)
            parametros = {k: v for k, v in parametros.items() if k != "keyterm"}
            respuesta = _post(URL, params=parametros, **comun)
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
        alternativa = canales[0]["alternatives"][0]
        texto = alternativa.get("transcript", "")
        segundos = float(datos.get("metadata", {}).get("duration") or 0.0)
    except Exception:
        return None
    texto = " ".join(str(texto or "").split())
    if not texto:
        palabras = alternativa.get("words") or []
        texto = " ".join(str(w.get("word", "")) for w in palabras
                         if isinstance(w, dict)).strip()
    if texto:
        return (texto, segundos)
    if segundos <= CLIP_CORTO_MAX:
        # Nova-3 ya evaluó el clip: devolver ("", duración) evita el fallback
        # a Groq Whisper (~2 s) en palabras sueltas o ruido breve.
        print(f"[oido] Deepgram 200 vacío en clip corto ({segundos:.2f}s): sin Whisper",
              flush=True)
        return ("", segundos)
    print(f"[oido] Deepgram 200 sin texto ({segundos:.2f}s): usando Whisper", flush=True)
    return None
