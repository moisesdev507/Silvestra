"""Visión de pantalla real bajo demanda para Silvestra / Lyris vía Gemini Flash REST."""
import base64
import io
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

_bloqueo = threading.RLock()
MODELOS_DEFAULT = (
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
)


def es_modo_privado(app=None):
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


def capturar_pantalla_b64(ancho_max=960, calidad=60):
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
            img = img.resize((ancho_max, max(1, int(img.height * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=calidad)
        return base64.b64encode(buf.getvalue()).decode("ascii")


def _limpiar_para_voz(texto: str) -> str:
    t = str(texto or "")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\[\s*[^\]]*\s*\]", "", t)
    t = re.sub(r"[*_#`~>|]", " ", t)
    t = re.sub(r"^\s*[-•\d+\.]+\s+", "", t, flags=re.M)
    return " ".join(t.split()).strip()


def _llamar_gemini(modelo: str, clave: str, b64_img: str, prompt: str, timeout: float = 8.0) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={clave}"
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
        ]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.2},
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        datos = json.loads(resp.read().decode("utf-8"))
    cands = datos.get("candidates", []) if isinstance(datos, dict) else []
    if cands and isinstance(cands, list) and isinstance(cands[0], dict):
        parts = cands[0].get("content", {}).get("parts", [])
        if parts and isinstance(parts, list) and isinstance(parts[0], dict):
            txt = parts[0].get("text", "")
            if str(txt).strip():
                return str(txt).strip()
    return ""


def _obtener_modelos_candidatos():
    candidatos = list(MODELOS_DEFAULT)
    extras = []
    try:
        import config
        cfgs = []
        m_cfg = getattr(config, "MODELOS_VISION", None)
        if isinstance(m_cfg, (list, tuple)):
            cfgs.extend(m_cfg)
        m_s = getattr(config, "MODELO_VISION", "")
        if m_s:
            cfgs.append(m_s)
        for m in cfgs:
            if isinstance(m, str) and m.strip().lower().startswith("gemini-"):
                m_low = m.strip().lower()
                if not any(x in m_low for x in ("audio", "tts", "image", "imagen")):
                    nom = m.strip()
                    if nom not in candidatos and nom not in extras:
                        extras.append(nom)
    except Exception:
        pass
    return candidatos + extras


def analizar_pantalla(pregunta: str = "") -> str:
    if es_modo_privado():
        return "No puedo mirar la pantalla mientras el modo Privado está activo."
    b64_img = capturar_pantalla_b64(ancho_max=960, calidad=60)
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

    peticion = str(pregunta or "").strip() or "Describe lo principal que ves en la pantalla, errores o contenido activo."
    prompt = (
        f"Petición del usuario: {peticion}\n"
        "Instrucción: Eres Lyris, asistente inteligente tipo F.R.I.D.A.Y. "
        "Observa la captura y responde en español en máximo 2 oraciones cortas (15 a 35 palabras). "
        "Sin markdown, sin listas con viñetas, sin URLs ni código kilométrico."
    )
    for mod in _obtener_modelos_candidatos():
        try:
            texto = _llamar_gemini(mod, clave, b64_img, prompt, timeout=8.0)
            if texto:
                limpio = _limpiar_para_voz(texto)
                if limpio:
                    return limpio
        except urllib.error.HTTPError:
            continue
        except (urllib.error.URLError, TimeoutError):
            continue
        except Exception:
            continue
    return "No pude obtener una respuesta visual de Gemini en este momento."


def capturar_y_analizar_pantalla(pregunta, app=None):
    if es_modo_privado(app):
        return False, "No puedo mirar la pantalla mientras el modo Privado está activo."
    res = analizar_pantalla(pregunta)
    ok = not res.startswith("No puedo") and not res.startswith("No pude") and not res.startswith("La visión")
    return ok, res


def detectar_peticion_vision(texto):
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
    "analizar_pantalla", "capturar_y_analizar_pantalla",
    "detectar_peticion_vision", "capturar_pantalla_b64",
    "es_modo_privado", "_limpiar_para_voz", "_obtener_modelos_candidatos",
]
