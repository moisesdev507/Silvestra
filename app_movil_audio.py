"""Puente de audio bidireccional y procesamiento conversacional móvil para Lyris.

Gestiona la transcripción de notas de voz webm/ogg con Whisper en memoria (sin archivos
residuales en disco), inyecta los turnos en el núcleo cognitivo de Lyris y sintetiza
la respuesta con Edge-TTS para reproducirla inmediatamente en el dispositivo móvil.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import threading
from typing import Any, Dict

import config

_bloqueo = threading.RLock()


def transcribir_audio_memoria(app: Any, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """Transcribe audio webm/ogg/wav en memoria usando Whisper de Groq sin tocar disco."""
    if not audio_bytes or len(audio_bytes) < 100:
        return ""

    clave_groq = getattr(config, "CLAVE", "")
    ext = "webm" if "webm" in str(mime_type).lower() else "ogg" if "ogg" in str(mime_type).lower() else "wav"
    nombre_virtual = f"audio_movil.{ext}"
    modelo_voz = getattr(config, "MODELO_VOZ", "whisper-large-v3-turbo")

    # 1. Intentar con app.cliente si existe
    if app and hasattr(app, "cliente") and hasattr(app.cliente, "audio"):
        try:
            r = app.cliente.audio.transcriptions.create(
                file=(nombre_virtual, audio_bytes),
                model=modelo_voz,
                language="es",
                prompt="Conversación en español con Lyris.",
                timeout=12.0,
            )
            txt = getattr(r, "text", "") or ""
            if txt.strip():
                return txt.strip()
        except Exception as e:
            print(f"[app_movil_audio] Groq client error: {e}", flush=True)

    # 2. Respaldo directo REST vía sesion_http
    if clave_groq:
        try:
            import sesion_http
            session = sesion_http.obtener_sesion()
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {clave_groq}"}
            files = {"file": (nombre_virtual, io.BytesIO(audio_bytes), mime_type)}
            data = {"model": modelo_voz, "language": "es"}
            r = session.post(url, headers=headers, files=files, data=data, timeout=12.0)
            if r.status_code == 200:
                txt = r.json().get("text", "")
                if txt and str(txt).strip():
                    return str(txt).strip()
        except Exception as e:
            print(f"[app_movil_audio] Groq REST error: {e}", flush=True)

    return ""


async def _crear_audio_edge(texto: str, emocion: str = "neutral") -> bytes:
    """Sintetiza la voz panameña de Lyris con prosodia emocional en memoria."""
    import edge_tts
    import cara_emociones

    pros = cara_emociones.obtener_prosodia(emocion)
    rate = pros.get("rate", "+0%")
    pitch = pros.get("pitch", "+0Hz")
    volume = pros.get("volume", "+0%")
    voz_edge = "es-PA-MargaritaNeural"

    datos = bytearray()
    async for trozo in edge_tts.Communicate(texto, voz_edge, rate=rate, pitch=pitch, volume=volume).stream():
        if trozo.get("type") == "audio" and "data" in trozo:
            datos += trozo["data"]
    return bytes(datos)


def sintetizar_respuesta_movil(texto: str, emocion: str = "neutral", timeout_seg: float = 12.0) -> str:
    """Genera audio MP3 en memoria y devuelve una cadena base64 lista para reproducir."""
    if not texto or not str(texto).strip():
        return ""
    limpio = re.sub(r"\[.*?\]", "", str(texto)).strip()
    if not limpio:
        return ""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_bytes = loop.run_until_complete(
                asyncio.wait_for(_crear_audio_edge(limpio, emocion), timeout=timeout_seg)
            )
        finally:
            loop.close()
        if audio_bytes:
            return base64.b64encode(audio_bytes).decode("ascii")
    except Exception as e:
        print(f"[app_movil_audio] Edge-TTS error: {e}", flush=True)
    return ""


def procesar_comando_texto_movil(app: Any, texto: str, sintetizar_voz: bool = True) -> Dict[str, Any]:
    """Inyecta el comando de texto en el cerebro de Lyris y retorna la respuesta procesada."""
    t = str(texto or "").strip()
    if not t:
        return {"ok": False, "error": "Texto vacío", "texto_usuario": "", "respuesta": "", "emocion": "neutral", "audio_base64": ""}

    with _bloqueo:
        cerebro = getattr(app, "cerebro", None)
        if not cerebro:
            return {"ok": False, "error": "Cerebro no disponible", "texto_usuario": t, "respuesta": "No tengo cerebro disponible en este momento.", "emocion": "seria", "audio_base64": ""}

        import respuesta_flujo
        resp, accion, emo = respuesta_flujo.responder_flujo(cerebro, t, al_frase=None)

        # Si hubo una acción reconocida, ejecutarla bajo supervisión
        if accion:
            try:
                import acciones
                acciones.ejecutar(accion, app=app)
            except Exception as e:
                print(f"[app_movil_audio] Error ejecutando acción '{accion}': {e}", flush=True)

        # Reflejar emoción y subtítulo en la PC central si la UI Qt está viva
        if app and hasattr(app, "cola") and app.cola:
            try:
                app.cola.put(("emocion", emo))
                resumen_sub = (resp[:65] + "...") if len(resp) > 65 else resp
                app.cola.put(("subtitulo", f"📱 {resumen_sub}"))
            except Exception:
                pass

        audio_b64 = ""
        if sintetizar_voz and resp:
            audio_b64 = sintetizar_respuesta_movil(resp, emo)

        return {
            "ok": True,
            "texto_usuario": t,
            "respuesta": resp,
            "accion": accion,
            "emocion": emo,
            "audio_base64": audio_b64,
        }


def procesar_audio_movil(app: Any, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
    """Flujo completo de audio: Transcribe -> Piensa en Lyris -> Sintetiza en base64."""
    if not audio_bytes:
        return {"ok": False, "error": "Audio vacío", "texto_usuario": "", "respuesta": "", "emocion": "neutral", "audio_base64": ""}

    texto_transcrito = transcribir_audio_memoria(app, audio_bytes, mime_type)
    if not texto_transcrito:
        return {
            "ok": False,
            "error": "No pude entender el audio o no se detectó voz.",
            "texto_usuario": "",
            "respuesta": "No logré escucharte con claridad. ¿Puedes repetírmelo?",
            "emocion": "preocupada",
            "audio_base64": "",
        }

    return procesar_comando_texto_movil(app, texto_transcrito, sintetizar_voz=True)


def manejar_http_voz(handler: Any, app: Any) -> tuple[int, Dict[str, Any]]:
    """Procesa la petición HTTP POST /api/movil/voz y retorna (codigo_http, cuerpo_dict)."""
    ctype = handler.headers.get("Content-Type", "")
    if "application/json" in ctype:
        try:
            size = int(handler.headers.get("Content-Length", 0))
            data = json.loads(handler.rfile.read(size).decode("utf-8")) if size > 0 else {}
        except Exception:
            data = {}
        texto = str(data.get("texto", "")).strip()
        res = procesar_comando_texto_movil(app, texto, sintetizar_voz=True)
        return 200, res

    try:
        size = int(handler.headers.get("Content-Length", 0))
        if size <= 0 or size > 8 * 1024 * 1024:
            return 400, {"ok": False, "error": "audio_size_invalid"}
        raw_audio = handler.rfile.read(size)
        if b"\r\n\r\n" in raw_audio and (b"WebKitFormBoundary" in raw_audio or b"----" in raw_audio[:80]):
            partes = raw_audio.split(b"\r\n\r\n", 1)
            if len(partes) > 1:
                raw_audio = partes[1].rsplit(b"\r\n--", 1)[0]
        res = procesar_audio_movil(app, raw_audio, mime_type=ctype)
        return 200, res
    except Exception as e:
        return 500, {"ok": False, "error": str(e)}


def manejar_http_chat(handler: Any, app: Any) -> tuple[int, Dict[str, Any]]:
    """Procesa la petición HTTP POST /api/movil/chat de forma síncrona devolviendo la respuesta."""
    try:
        size = int(handler.headers.get("Content-Length", 0))
        data = json.loads(handler.rfile.read(size).decode("utf-8")) if size > 0 else {}
    except Exception as e:
        return 400, {"ok": False, "error": f"JSON inválido: {e}"}

    texto = str(data.get("texto", "")).strip()
    if not texto:
        return 400, {"ok": False, "error": "Texto vacío"}

    hablar = bool(data.get("hablar", False))
    try:
        res = procesar_comando_texto_movil(app, texto, sintetizar_voz=hablar)
        return 200, res
    except Exception as e:
        return 500, {"ok": False, "error": f"Error procesando turno: {e}"}


def manejar_http_movil(handler: Any, app: Any, path: str) -> tuple[int, Dict[str, Any]]:
    """Despachador unificado para los endpoints móviles /api/movil/*."""
    p = path.split("?", 1)[0]
    if p == "/api/movil/chat":
        return manejar_http_chat(handler, app)
    return manejar_http_voz(handler, app)


