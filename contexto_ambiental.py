"""Contexto ambiental ligero y cacheado: ventana activa y portapapeles reciente.

Nunca hace E/S en el hilo de audio ni en Qt: un único hilo daemon actualiza
una instantánea protegida con RLock. Los lectores solo copian esa caché.
"""
import hashlib
import re
import threading
import time

_MAX_CLIP = 180
_MAX_VENTANA = 120
_EDAD_VENTANA_SEG = 30.0
_EDAD_CLIP_SEG = 300.0
_INTERVALO_SEG = 3.0

_SECRETO = re.compile(
    r"(?i)(contraseña|password|passwd|clave|token|api[_\s-]?key|secret|bearer)\s*[:=]?\s*\S+"
)
_OPACO = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")

_bloqueo = threading.RLock()
_hilo = None
_cache = {"ventana": "", "clipboard": "", "hash": "", "cambio": 0.0, "ts": 0.0}


def _limpiar(texto, limite):
    limpio = " ".join(str(texto or "").split())
    limpio = _SECRETO.sub("[oculto]", limpio)
    limpio = _OPACO.sub("[oculto]", limpio)
    return limpio[:limite].strip()


def _leer_ventana():
    try:
        import capacidades_extra
        return _limpiar(capacidades_extra.ventana_activa(), _MAX_VENTANA)
    except Exception:
        return ""


def _leer_portapapeles():
    """None = bloqueado/indisponible; '' = vacío; str = contenido."""
    try:
        import portapapeles_win
        texto = portapapeles_win.leer_portapapeles_windows(max_chars=_MAX_CLIP)
        if texto is None:
            return None
        return _limpiar(texto, _MAX_CLIP)
    except Exception:
        return None


def capturar(ventana=None, portapapeles=None):
    """Actualiza la caché; los parámetros permiten inyectar lecturas en pruebas."""
    global _cache
    ahora = time.time()
    titulo = _limpiar(ventana if ventana is not None else _leer_ventana(), _MAX_VENTANA)
    lectura = portapapeles if portapapeles is not None else _leer_portapapeles()
    with _bloqueo:
        cambio = _cache["cambio"]
        if lectura is None:  # bloqueado: conserva la última lectura válida
            texto, huella = _cache["clipboard"], _cache["hash"]
        else:
            texto = _limpiar(lectura, _MAX_CLIP)
            huella = hashlib.sha1(texto.encode("utf-8")).hexdigest() if texto else ""
            if huella and huella != _cache["hash"]:
                cambio = ahora
            if not huella:
                cambio = 0.0
        _cache = {"ventana": titulo, "clipboard": texto, "hash": huella,
                  "cambio": cambio, "ts": ahora}
        return dict(_cache)


def _bucle():
    while True:
        try:
            capturar()
        except Exception:
            pass
        time.sleep(_INTERVALO_SEG)


def iniciar():
    """Arranca el muestreo en segundo plano una sola vez; no bloquea."""
    global _hilo
    with _bloqueo:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_bucle, daemon=True, name="contexto-ambiental")
            _hilo.start()
    return True


def snapshot():
    """Copia de la última lectura sin ninguna E/S."""
    with _bloqueo:
        return dict(_cache)


def resumen_para_prompt():
    """Bloque compacto y fresco para Live y Celeste; nunca inventa datos."""
    iniciar()
    with _bloqueo:
        datos = dict(_cache)
    ahora = time.time()
    partes = []
    if datos["ventana"] and ahora - datos["ts"] <= _EDAD_VENTANA_SEG:
        partes.append("Ventana activa detectada: " + datos["ventana"])
    if (datos["clipboard"] and datos["cambio"]
            and ahora - datos["cambio"] <= _EDAD_CLIP_SEG):
        partes.append("Portapapeles recién cambiado: " + datos["clipboard"])
    if not partes:
        return ""
    return ("[CONTEXTO AMBIENTAL] " + ". ".join(partes)
            + ". Sirve para referencias como «esto» o «este correo; pregunta si no basta; nunca lo inventes.")


def añadir(contexto=""):
    """Añade el bloque al prompt clásico sin duplicarlo."""
    base = str(contexto or "")
    extra = resumen_para_prompt()
    return (base + "\n" + extra).strip() if extra else base


def resolver_referencias(texto=""):
    """Aclara 'esto/este correo' con la caché ambiental; sin inventar nada."""
    t = str(texto or "")
    if not re.search(r"(?i)\b(esto|esta|este|esa|ese|eso|este correo|esta ventana)\b", t):
        return t
    extra = resumen_para_prompt()
    return (t + "\n" + extra).strip() if extra else t


def limpiar():
    """Invalida la caché (cambio de motor o pruebas)."""
    global _cache
    with _bloqueo:
        _cache = {"ventana": "", "clipboard": "", "hash": "", "cambio": 0.0, "ts": 0.0}
    return True


__all__ = ["capturar", "iniciar", "snapshot", "resumen_para_prompt",
           "resolver_referencias", "añadir", "limpiar"]
