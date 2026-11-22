"""Módulo de visión de pantalla real bajo demanda para Silvestra / Lyris.

Captura la pantalla en memoria (mss / Pillow), comprime a JPEG base64 (sin archivos en disco),
respeta el modo Privado y consulta a proveedores multimodales configurados.
"""
import base64
import io
import json
import os
import re
import threading
import time

_bloqueo = threading.RLock()


def es_modo_privado(app=None):
    """Verifica si el modo privado está activo en app, ecosistema o estado.json."""
    if app:
        if getattr(app, "modo_privado", False):
            return True
        eco = getattr(app, "ecosistema_gestor", None)
        if eco and hasattr(eco, "modo_privado"):
            try:
                if eco.modo_privado():
                    return True
            except Exception:
                pass
    try:
        import estado
        est = estado.cargar()
        if est.get("modo_privado", False) or est.get("preferencias", {}).get("modo_privado", False):
            return True
    except Exception:
        pass
    return False


def capturar_pantalla_b64(ancho_max=1280, calidad=75):
    """Captura el monitor principal en memoria y lo devuelve como cadena JPEG base64 (cero archivos en disco)."""
    with _bloqueo:
        img = None
        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
            except Exception as e:
                print(f"[vision_pantalla] Error en captura: {e}", flush=True)
                return None

        if not img:
            return None

        from PIL import Image
        if img.width > ancho_max:
            ratio = float(ancho_max) / float(img.width)
            nuevo_alto = max(1, int(img.height * ratio))
            img = img.resize((ancho_max, nuevo_alto), Image.LANCZOS)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=calidad)
        return base64.b64encode(buf.getvalue()).decode("ascii")


def obtener_ventana_activa(app=None):
    """Obtiene el título real de la ventana activa en primer plano de Windows."""
    # 1. Telemetría de puente multimodal en app
    if app:
        try:
            mm = getattr(app, "sistema_multimodal", None) or getattr(app, "multimodal", None)
            if mm and hasattr(mm, "estado_salud"):
                v = mm.estado_salud().get("ultima_ventana_externa")
                if v and isinstance(v, dict) and v.get("titulo"):
                    return str(v["titulo"]).strip()
        except Exception:
            pass

    # 2. Memoria de trabajo corta (cerebro_trabajo)
    try:
        import cerebro_trabajo
        mem = cerebro_trabajo.obtener_memoria_trabajo()
        ult_v = mem.get("ultima_ventana")
        if ult_v and isinstance(ult_v, dict) and ult_v.get("titulo"):
            return str(ult_v["titulo"]).strip()
    except Exception:
        pass

    # 3. Enumeración de ventana externa win32 (excluye el proceso de la app)
    try:
        from multimodal_ventana_win32 import enumerar_ventana_externa
        v_ext = enumerar_ventana_externa()
        if v_ext and isinstance(v_ext, dict) and v_ext.get("titulo"):
            return str(v_ext["titulo"]).strip()
    except Exception:
        pass

    # 4. Sensor nativo de contexto de Windows
    try:
        import contexto_windows
        ctx = contexto_windows.obtener_contexto_windows()
        if ctx and isinstance(ctx, dict) and ctx.get("titulo"):
            return str(ctx["titulo"]).strip()
    except Exception:
        pass

    # 5. Fallback win32gui
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            tit = win32gui.GetWindowText(hwnd)
            if tit and str(tit).strip():
                return str(tit).strip()
    except Exception:
        pass

    return "Escritorio de Windows"


def analizar_imagen_multimodal(b64_img, pregunta, titulo_ventana="", timeout_seg=15.0):
    """Envía la imagen base64 y el contexto de ventana al proveedor multimodal configurado."""
    if not b64_img:
        return "No pude capturar la pantalla para analizarla."

    import config
    import sesion_http

    session = sesion_http.obtener_sesion()

    prompt_texto = (
        f"Contexto: El usuario está viendo la ventana activa: '{titulo_ventana}'.\n"
        f"Pregunta/Petición: {pregunta}\n"
        "Instrucción: Eres Lyris, asistente inteligente personal. Responde en español de forma directa, "
        "concisa, natural y útil sobre lo que ves en la pantalla."
    )

    # 1. Candidato Principal: Google Gemini con API nativa generateContent (inline_data)
    clave_google = getattr(config, "CLAVE_GOOGLE", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if clave_google:
        modelos_gemini = ("gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash-latest")
        for mod in modelos_gemini:
            try:
                url_gem = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={clave_google}"
                payload_gem = {
                    "contents": [{
                        "parts": [
                            {"text": prompt_texto},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": b64_img,
                                }
                            },
                        ]
                    }],
                    "generationConfig": {"maxOutputTokens": 600},
                }
                r = session.post(url_gem, headers={"Content-Type": "application/json"}, json=payload_gem, timeout=timeout_seg)
                if r.status_code == 200:
                    datos = r.json()
                    cands = datos.get("candidates", [])
                    if cands:
                        partes = cands[0].get("content", {}).get("parts", [])
                        if partes and "text" in partes[0] and partes[0]["text"].strip():
                            return str(partes[0]["text"]).strip()
            except Exception as e:
                print(f"[vision_pantalla] Fallo Gemini REST ({mod}): {e}", flush=True)

            try:
                url_oa = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                headers_oa = {"Authorization": f"Bearer {clave_google}", "Content-Type": "application/json"}
                payload_oa = {
                    "model": mod,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_texto},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                        ],
                    }],
                    "max_tokens": 500,
                }
                r = session.post(url_oa, headers=headers_oa, json=payload_oa, timeout=timeout_seg)
                if r.status_code == 200:
                    datos = r.json()
                    contenido = datos.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if contenido and str(contenido).strip():
                        return str(contenido).strip()
            except Exception:
                pass

    # 2. Candidato Groq Vision
    clave_groq = getattr(config, "CLAVE", "") or os.environ.get("GROQ_API_KEY", "")
    if clave_groq:
        modelos_groq = getattr(config, "MODELOS_VISION", ["qwen/qwen3.8-27b"])
        for mod in modelos_groq:
            try:
                headers = {"Authorization": f"Bearer {clave_groq}", "Content-Type": "application/json"}
                payload = {
                    "model": mod,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_texto},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                        ],
                    }],
                    "max_tokens": 500,
                }
                r = session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout_seg,
                )
                if r.status_code == 200:
                    datos = r.json()
                    contenido = datos.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if contenido and str(contenido).strip():
                        return str(contenido).strip()
            except Exception as e:
                print(f"[vision_pantalla] Fallo Groq ({mod}): {e}", flush=True)

    # 3. Candidato OpenRouter Vision
    clave_or = getattr(config, "CLAVE_OPENROUTER", "")
    if clave_or:
        try:
            headers = {"Authorization": f"Bearer {clave_or}", "Content-Type": "application/json"}
            payload = {
                "model": "google/gemini-flash-1.5",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_texto},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                    ],
                }],
                "max_tokens": 500,
            }
            r = session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=timeout_seg)
            if r.status_code == 200:
                datos = r.json()
                contenido = datos.get("choices", [{}])[0].get("message", {}).get("content", "")
                if contenido and str(contenido).strip():
                    return str(contenido).strip()
        except Exception as e:
            print(f"[vision_pantalla] Fallo OpenRouter: {e}", flush=True)

    return f"He capturado la pantalla de '{titulo_ventana}', pero los proveedores de visión multimodales no están disponibles en este momento."


def capturar_y_analizar_pantalla(pregunta, app=None):
    """Punto de entrada principal para análisis visual bajo demanda."""
    if es_modo_privado(app):
        return False, "No puedo mirar la pantalla mientras el modo Privado está activo."

    b64 = capturar_pantalla_b64()
    if not b64:
        return False, "No pude capturar la pantalla del equipo."

    titulo = obtener_ventana_activa(app=app)
    resultado = analizar_imagen_multimodal(b64, pregunta, titulo_ventana=titulo)
    return True, resultado


def detectar_peticion_vision(texto):
    """Detecta si el usuario pide explícitamente ver, analizar o leer la pantalla."""
    if not texto or len(str(texto).strip()) < 5:
        return False
    t = str(texto).strip()
    patron = (
        r"\b(?:mira\s+(?:la\s+)?pantalla|"
        r"qu[eé]\s+(?:ves|hay|aparece|dice)\s+(?:en\s+)?(?:la\s+)?pantalla|"
        r"revisa\s+(?:este\s+)?(?:error|diseño|diseno|codigo|código|pantalla)\s*(?:en\s+(?:la\s+)?pantalla)?|"
        r"qu[eé]\s+opinas\s+de\s+(?:este\s+)?(?:diseño|diseno|codigo|código|pantalla)|"
        r"lee\s+(?:lo\s+que\s+dice\s+en\s+)?(?:la\s+)?pantalla)\b"
    )
    return bool(re.search(patron, t, re.I))
