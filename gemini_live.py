"""Gemini Live (WebSocket): clave, sesión, herramientas y enfriamiento por 429.

Nunca imprime la clave ni propaga errores al flujo de voz.
"""
import asyncio
import json
import os
import threading
import time

import acciones

_MODELO = "models/gemini-2.0-flash-live-001"
_URL = ("wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
_ENFRIAMIENTO_SEG = 90.0
_LOCK = threading.RLock()
_HASTA = 0.0
_MOTIVO = ""


def declarar_herramientas(limite=40):
    """Declara solo acciones del catálogo conocido (ACCIONES + VIVAS)."""
    func = []
    for nombre in (list(acciones.ACCIONES) + list(acciones.VIVAS))[:limite]:
        desc = acciones.ACCIONES.get(nombre, (None, None, ""))[2] or \
            acciones.VIVAS.get(nombre, (None, ""))[1]
        func.append({
            "name": nombre,
            "description": str(desc)[:180],
            "parameters": {"type": "OBJECT",
                           "properties": {"arg": {"type": "STRING"}}},
        })
    return [{"function_declarations": func}]


def _clave():
    """Lee la clave sin registrarla en logs ni exponerla en mensajes."""
    import config
    for nombre in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        valor = os.environ.get(nombre) or getattr(config, nombre, None)
        if valor and str(valor).strip():
            return str(valor).strip()
    return ""


def activo():
    """Flag de activación: entorno LYRIS_LIVE_CHAT o config.GEMINI_LIVE_ACTIVO."""
    import config
    return bool(os.environ.get("LYRIS_LIVE_CHAT") == "1"
                or getattr(config, "GEMINI_LIVE_ACTIVO", False))


def enfriado():
    with _LOCK:
        return time.time() < _HASTA


def motivo_enfriamiento():
    with _LOCK:
        return _MOTIVO if time.time() < _HASTA else ""


def marcar_enfriamiento(motivo="429"):
    """Pausa el modo Live para caer al flujo estándar sin repetir errores."""
    global _HASTA, _MOTIVO
    with _LOCK:
        _HASTA = time.time() + _ENFRIAMIENTO_SEG
        _MOTIVO = str(motivo)[:120]
    print(f"[gemini_live] enfriamiento {int(_ENFRIAMIENTO_SEG)}s: {_MOTIVO}", flush=True)


def reiniciar():
    """Reinicia el enfriamiento (pruebas y reconexión explícita)."""
    global _HASTA, _MOTIVO
    with _LOCK:
        _HASTA = 0.0
        _MOTIVO = ""


def _es_cuota(error):
    txt = str(error).lower()
    return any(k in txt for k in ("429", "resource_exhausted", "quota",
                                  "rate limit", "too many requests",
                                  "cuota", "exhausted"))


def _seguro(texto, clave):
    """Recorta el motivo y sustituye la clave si apareciera en la excepción."""
    resultado = str(texto)
    if clave:
        resultado = resultado.replace(clave, "***")
    return resultado[:120]


def ejecutar_herramienta_live(nombre, arg=None):
    """Delega en acciones.ejecutar solo nombres permitidos; devuelve (ok, msg)."""
    nombre = str(nombre or "").strip().lower().replace(" ", "_")
    if nombre not in acciones.ACCIONES and nombre not in acciones.VIVAS:
        return False, "Acción no permitida."
    try:
        ok, mensaje = acciones.ejecutar(nombre, arg)
        return bool(ok), str(mensaje)[:300]
    except Exception as e:
        return False, "No pude hacerlo: " + str(e)[:100]


async def _enviar(ws, objeto):
    await ws.send(json.dumps(objeto, ensure_ascii=False))


async def _leer(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=30))


async def _ciclo(ws, texto, al_frase, cancelar):
    await _enviar(ws, {"setup": {
        "model": _MODELO,
        "generation_config": {"response_modalities": ["TEXT"]},
        "tools": declarar_herramientas(),
    }})
    await _enviar(ws, {"client_content": {
        "turns": [{"role": "user", "parts": [{"text": str(texto or "Hola")}]}],
        "turn_complete": True,
    }})
    piezas = []
    for _ in range(40):
        if cancelar and cancelar():
            return None
        mensaje = await _leer(ws)
        if mensaje.get("error"):
            raise RuntimeError(str(mensaje["error"]))
        contenido = mensaje.get("server_content") or {}
        partes = (contenido.get("model_turn") or {}).get("parts", [])
        for parte in partes:
            texto_parte = parte.get("text") or parte.get("texto")
            if texto_parte:
                piezas.append(str(texto_parte))
                if callable(al_frase):
                    try:
                        al_frase(str(texto_parte))
                    except Exception:
                        pass
        for parte in partes:
            llamada = parte.get("function_call") or parte.get("functionCall")
            if llamada:
                await _responder_tool(
                    ws, llamada, llamada.get("name") or llamada.get("nombre"))
        if contenido.get("turn_complete") or mensaje.get("generation_complete") or \
                mensaje.get("turnComplete"):
            break
    respuesta = " ".join(" ".join(piezas).split())
    # La herramienta ya se ejecutó aquí: no devolver acción para evitar duplicarla.
    return (respuesta, None, "neutral") if respuesta else None


async def _responder_tool(ws, llamada, nombre):
    args = llamada.get("args") or llamada.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    ok, mensaje = ejecutar_herramienta_live(nombre, args.get("arg"))
    print(f"[gemini_live] herramienta={nombre} ok={ok}", flush=True)
    await _enviar(ws, {"tool_response": {"function_responses": [{
        "id": llamada.get("id", "1"), "name": nombre,
        "response": {"ok": ok, "mensaje": mensaje},
    }]}})


async def enviar_turno_live(mensajes=None, texto=None, al_frase=None, cancelar=None):
    """Turno Live asíncrono; None significa 'caer al flujo estándar'."""
    if not activo() or enfriado():
        return None
    clave = _clave()
    if not clave:
        return None
    try:
        import websockets
    except Exception:
        return None
    try:
        async with websockets.connect(_URL + "?key=" + clave,
                                      open_timeout=8, ping_interval=None) as ws:
            return await _ciclo(ws, texto, al_frase, cancelar)
    except asyncio.CancelledError:
        return None
    except Exception as e:
        if _es_cuota(e):
            marcar_enfriamiento(_seguro(e, clave))
        else:
            print(f"[gemini_live] sin respuesta: {_seguro(e, clave)}", flush=True)
        return None


def turno_live(mensajes=None, texto=None, al_frase=None, cancelar=None):
    """Entrada síncrona usada por respuesta_flujo; nunca lanza excepciones."""
    if not activo() or enfriado() or not _clave():
        return None
    try:
        return asyncio.run(enviar_turno_live(mensajes, texto, al_frase, cancelar))
    except asyncio.CancelledError:
        return None
    except RuntimeError:
        return None  # Ya hay un event loop en este hilo: no bloquear.
    except Exception as e:
        if _es_cuota(e):
            marcar_enfriamiento(_seguro(e, _clave()))
        return None
