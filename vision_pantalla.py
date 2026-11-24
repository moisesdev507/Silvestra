"""Módulo de visión de pantalla real bajo demanda para Silvestra / Lyris.

Captura la pantalla en memoria (mss / Pillow), comprime a JPEG base64 (sin archivos en disco),
respeta el modo Privado y consulta a Gemini Flash vía API REST directa (urllib).
"""
import base64
import io
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

_bloqueo = threading.RLock()


def es_modo_privado(app=None):
    """Verifica si el modo privado está activo en app o estado.json."""
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


def capturar_pantalla_b64(ancho_max=1280, calidad=70):
    """Captura el monitor principal en memoria y lo devuelve como JPEG base64 (< 150 KB)."""
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
            except Exception:
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


def _limpiar_para_voz(texto: str) -> str:
    """Elimina markdown, URLs, listas y asteriscos para voz hablada fluida."""
    t = str(texto or "")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\[\s*[^\]]*\s*\]", "", t)
    t = re.sub(r"[*_#`~>|]", " ", t)
    t = re.sub(r"^\s*[-•\d+\.]+\s+", "", t, flags=re.M)
    t = " ".join(t.split())
    return t.strip()


def _llamar_gemini(modelo: str, clave: str, b64_img: str, prompt_texto: str, timeout: float = 8.0) -> str:
    """Envía la imagen a Gemini REST generateContent con timeout controlado."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={clave}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_texto},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 250, "temperature": 0.4},
    }
    cuerpo = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        datos = json.loads(resp.read().decode("utf-8"))
    cands = datos.get("candidates", [])
    if cands:
        parts = cands[0].get("content", {}).get("parts", [])
        if parts and "text" in parts[0] and parts[0]["text"].strip():
            return parts[0]["text"].strip()
    return ""


def analizar_pantalla(pregunta: str = "") -> str:
    """Analiza la pantalla principal con Gemini Flash y devuelve respuesta hablada estilo F.R.I.D.A.Y."""
    if es_modo_privado():
        return "No puedo mirar la pantalla mientras el modo Privado está activo."

    b64_img = capturar_pantalla_b64(ancho_max=1280, calidad=70)
    if not b64_img:
        return "No pude capturar la pantalla en este momento."

    clave = ""
    try:
        import config
        clave = getattr(config, "CLAVE_GOOGLE", "") or ""
    except Exception:
        clave = ""

    if not clave or not str(clave).strip():
        return "La visión de pantalla no está configurada: falta la clave de Google Gemini."

    # Modelos configurados o fallback seguro a Gemini Flash
    modelos_candidatos = []
    try:
        import config
        m_cfg = getattr(config, "MODELOS_VISION", None)
        if isinstance(m_cfg, (list, tuple)):
            modelos_candidatos.extend(m_cfg)
        m_single = getattr(config, "MODELO_VISION", "")
        if m_single and m_single not in modelos_candidatos:
            modelos_candidatos.append(m_single)
    except Exception:
        pass

    for m_def in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
        if m_def not in modelos_candidatos:
            modelos_candidatos.append(m_def)

    peticion = str(pregunta or "").strip()
    if not peticion:
        peticion = "Describe lo principal que ves en la pantalla, enfocándote en errores o contenido activo."

    prompt = (
        f"Petición del usuario: {peticion}\n"
        "Instrucción: Eres Lyris, asistente inteligente tipo F.R.I.D.A.Y. "
        "Observa la captura de pantalla y responde de forma directa en español en máximo 2 oraciones cortas "
        "(entre 15 y 35 palabras en total). No uses markdown, no uses listas con viñetas, no leas URLs ni código "
        "kilométrico: sintetiza exactamente lo que el usuario necesita saber para ser leído en voz alta."
    )

    for mod in modelos_candidatos:
        try:
            texto = _llamar_gemini(mod, clave, b64_img, prompt, timeout=8.0)
            if texto:
                limpio = _limpiar_para_voz(texto)
                if limpio:
                    return limpio
        except urllib.error.HTTPError as e:
            continue
        except (urllib.error.URLError, TimeoutError):
            continue
        except Exception:
            continue

    return "No pude obtener una respuesta visual de Gemini en este momento."


def capturar_y_analizar_pantalla(pregunta, app=None):
    """Punto de entrada compatible con respuesta_flujo.py y tests existentes."""
    if es_modo_privado(app):
        return False, "No puedo mirar la pantalla mientras el modo Privado está activo."
    res = analizar_pantalla(pregunta)
    ok = not res.startswith("No puedo") and not res.startswith("No pude") and not res.startswith("La visión")
    return ok, res


def detectar_peticion_vision(texto):
    """Detecta peticiones naturales de inspección visual de pantalla."""
    if not texto or len(str(texto).strip()) < 4:
        return False
    t = str(texto).lower()
    patrones = (
        r"mira (?:la |mi )?pantalla",
        r"(?:ves|puedes ver) (?:la |mi )?pantalla",
        r"qu[eé] ves(?: aqu[ií]| en (?:la |mi )?pantalla)?",
        r"qu[eé] (?:errores|fallos|problemas) (?:que )?encuentras",
        r"lee (?:este )?error",
        r"qu[eé] error (?:sale|tengo) aqu[ií]",
        r"qu[eé] error es (?:este)?",
        r"revisa (?:mi |el |este )?(?:c[oó]digo|error|pantalla)",
        r"revisa (?:la |mi )?pantalla",
        r"analiza lo que tengo abierto",
        r"analiza (?:la |mi )?pantalla",
        r"qu[eé] tengo en (?:la |mi )?pantalla",
    )
    return any(re.search(p, t) for p in patrones)


__all__ = [
    "analizar_pantalla",
    "capturar_y_analizar_pantalla",
    "detectar_peticion_vision",
    "capturar_pantalla_b64",
    "es_modo_privado",
    "_limpiar_para_voz",
]
