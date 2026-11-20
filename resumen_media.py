"""Módulo de obtención de subtítulos y contenido multimedia para resúmenes."""
from __future__ import annotations

import re
from resumen_web import limpiar_url


def extraer_youtube_id(url: str) -> str | None:
    """Extrae el identificador de 11 caracteres de un enlace de YouTube."""
    if not url:
        return None
    url_str = str(url).strip()
    m = re.search(r"(?:v=|\/embed\/|\/shorts\/|youtu\.be\/|^)([0-9A-Za-z_-]{11})(?:[?&/#]|$)", url_str)
    return m.group(1) if m else None


def es_enlace_youtube(url: str) -> bool:
    """Devuelve True si la URL corresponde a un video de YouTube."""
    if not url:
        return False
    u = url.lower()
    return "youtube.com" in u or "youtu.be" in u


def obtener_subtitulos_youtube(url_o_id: str) -> tuple[str | None, str | None]:
    """Obtiene los subtítulos del video en español, inglés o el disponible con youtube-transcript-api."""
    url_limpia = limpiar_url(url_o_id) if "http" in (url_o_id or "") else (url_o_id or "").strip()
    vid = extraer_youtube_id(url_limpia) or (url_limpia if len(url_limpia) == 11 else None)
    if not vid:
        return None, "No se encontró un enlace o identificador de video de YouTube válido."

    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            IpBlocked,
            RequestBlocked,
            InvalidVideoId,
            AgeRestricted,
            YouTubeRequestFailed,
        )
    except ImportError:
        return None, "REQUIERE_LIBRERIA"

    try:
        api = YouTubeTranscriptApi()
        tl = api.list(vid)

        elegido = None
        for t in tl:
            if t.language_code.lower().startswith("es"):
                elegido = t
                break
        if not elegido:
            for t in tl:
                if t.language_code.lower().startswith("en"):
                    elegido = t
                    break
        if not elegido:
            for t in tl:
                elegido = t
                break

        if not elegido:
            return None, "Este video de YouTube no tiene subtítulos disponibles en ningún idioma."

        fetched = elegido.fetch()
        textos = [s.text.strip() for s in fetched if hasattr(s, "text") and s.text.strip()]
        texto_completo = " ".join(textos)
        if not texto_completo:
            return None, "El video de YouTube no contiene texto en sus pistas de subtítulos."

        return texto_completo, None
    except TranscriptsDisabled:
        return None, "Este video de YouTube tiene los subtítulos desactivados por su autor."
    except NoTranscriptFound:
        return None, "Este video de YouTube no tiene subtítulos disponibles en ningún idioma."
    except VideoUnavailable:
        return None, "El video de YouTube no está disponible o fue marcado como privado."
    except AgeRestricted:
        return None, "El video de YouTube tiene restricción de edad y no permite consultar sus subtítulos."
    except (IpBlocked, RequestBlocked):
        return None, "YouTube bloqueó temporalmente las solicitudes de subtítulos desde esta dirección IP."
    except InvalidVideoId:
        return None, "El enlace o identificador del video de YouTube no es válido."
    except YouTubeRequestFailed as e:
        return None, f"Fallo de conexión al comunicarse con los servidores de YouTube: {e}"
    except Exception as e:
        err_str = str(e).lower()
        if "disabled" in err_str or "no transcript" in err_str:
            return None, "Este video de YouTube no tiene subtítulos disponibles, así que no puedo resumirlo."
        return None, f"Error al leer subtítulos de YouTube: {e}"


def obtener_texto_portapapeles() -> str:
    """Lee el texto actual del portapapeles de forma segura."""
    try:
        from PySide6.QtGui import QGuiApplication
        clip = QGuiApplication.clipboard()
        if clip:
            txt = clip.text()
            if txt:
                return txt.strip()
    except Exception:
        pass

    try:
        import subprocess
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=0x08000000,
        )
        out, _ = p.communicate(timeout=2)
        return (out or "").strip()
    except Exception:
        return ""
