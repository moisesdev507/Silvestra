"""Módulo de visión de pantalla real bajo demanda para Silvestra / Lyris.

Captura la pantalla en memoria (mss / Pillow), comprime a JPEG base64 (sin archivos en disco),
respeta el modo Privado y consulta a proveedores multimodales configurados.
"""
import base64
import io
import json
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


def obtener_ventana_activa():
    """Obtiene el título de la ventana activa en primer plano de Windows."""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            tit = win32gui.GetWindowText(hwnd)
            if tit and str(tit).strip():
                return str(tit).strip()
    except Exception:
        pass
    try:
        import contexto_windows
        v = contexto_windows.obtener_ventana_activa()
        if v and isinstance(v, dict):
            return str(v.get("titulo") or "").strip()
    except Exception:
        pass
    return "Ventana principal"


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

    # 1. Candidato Groq Vision
    clave_groq = getattr(config, "CLAVE", "")
    if clave_groq:
        modelos_groq = ["llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview"]
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

    # 2. Candidato Google Gemini Vision
    clave_google = getattr(config, "CLAVE_GOOGLE", "")
    if clave_google:
        for mod in ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-1.5-flash"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                headers = {"Authorization": f"Bearer {clave_google}", "Content-Type": "application/json"}
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
                r = session.post(url, headers=headers, json=payload, timeout=timeout_seg)
                if r.status_code == 200:
                    datos = r.json()
                    contenido = datos.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if contenido and str(contenido).strip():
                        return str(contenido).strip()
            except Exception as e:
                print(f"[vision_pantalla] Fallo Google ({mod}): {e}", flush=True)

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

    titulo = obtener_ventana_activa()
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
