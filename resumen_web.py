"""Módulo de extracción y descarga web segura para resúmenes en Silvestra."""
from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import urllib.parse

TIMEOUT_RED = 10
MAX_DESCARGA_BYTES = 2 * 1024 * 1024  # 2 MB


def limpiar_url(texto: str) -> str:
    """Extrae la primera URL https://, elimina basura envolvente y codifica caracteres."""
    if not texto or not isinstance(texto, str):
        return ""
    m = re.search(r"https://\S+", texto.strip())
    if not m:
        return ""

    url = m.group(0)
    envolventes = "\"'`<>«»“”‘’"
    url = url.strip(envolventes)
    puntuacion_final = ".,;:!?"

    while True:
        cambio = False
        if url and url[-1] in envolventes:
            url = url[:-1]
            cambio = True
        elif url and url[-1] in puntuacion_final:
            url = url[:-1]
            cambio = True
        elif url and url.endswith(")"):
            if url.count(")") > url.count("("):
                url = url[:-1]
                cambio = True
        elif url and url.endswith("]"):
            if url.count("]") > url.count("["):
                url = url[:-1]
                cambio = True
        if not cambio:
            break

    partes = urllib.parse.urlsplit(url)
    try:
        netloc = partes.netloc.encode("idna").decode("ascii")
    except Exception:
        netloc = partes.netloc

    path = urllib.parse.quote(urllib.parse.unquote(partes.path), safe="/()@:+&=$%,-_.!~*'")
    query = urllib.parse.quote(urllib.parse.unquote(partes.query), safe="=&?/:@+$%,-_.!~*'")
    fragment = urllib.parse.quote(urllib.parse.unquote(partes.fragment), safe="=&?/:@+$%,-_.!~*'")

    return urllib.parse.urlunsplit((partes.scheme, netloc, path, query, fragment))


def es_url_segura(url: str) -> tuple[bool, str | None]:
    """Valida que la URL use HTTPS y no apunte a direcciones locales o privadas."""
    if not url or not isinstance(url, str):
        return False, "No se proporcionó un enlace válido."

    try:
        p = urllib.parse.urlparse(url.strip())
        if p.scheme.lower() != "https":
            return False, "Por seguridad solo se admiten enlaces seguros que comiencen con https://"

        host = (p.hostname or "").strip().lower()
        if not host:
            return False, "El enlace no contiene un nombre de dominio válido."

        if host in ("localhost", "local", "broadcasthost") or host.endswith(".local") or host.endswith(".internal"):
            return False, "Por seguridad no se permite acceder a direcciones locales o internas."

        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, "Por seguridad no se permite acceder a direcciones IP privadas o de red local."
        except ValueError:
            pass

        return True, None
    except Exception as e:
        return False, f"Enlace no válido ({e})."


class ExtractorTextoHTML(HTMLParser):
    """Extractor ligero de texto plano que descarta scripts, estilos y navegación."""

    def __init__(self):
        super().__init__()
        self.en_ignorado = 0
        self.etiquetas_ignorar = {
            "script", "style", "noscript", "svg", "header", "footer",
            "nav", "aside", "form", "iframe", "head"
        }
        self.partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list):
        t = tag.lower()
        if t in self.etiquetas_ignorar:
            self.en_ignorado += 1
        elif t in ("p", "div", "article", "section", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr"):
            self.partes.append("\n")

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in self.etiquetas_ignorar:
            self.en_ignorado = max(0, self.en_ignorado - 1)
        elif t in ("p", "div", "article", "section", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.partes.append("\n")

    def handle_data(self, data: str):
        if self.en_ignorado == 0:
            txt = data.strip()
            if txt:
                self.partes.append(data)


def extraer_texto_html(html_str: str) -> str:
    """Extrae el contenido textual limpio eliminando etiquetas y espacios redundantes."""
    parser = ExtractorTextoHTML()
    try:
        parser.feed(html_str)
        crudo = "".join(parser.partes)
        lineas = [l.strip() for l in crudo.splitlines() if l.strip()]
        return "\n".join(lineas)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html_str)


def descargar_pagina(url: str) -> tuple[str | None, str | None]:
    """Descarga el contenido de la página respetando seguridad, timeout y tope de 2 MB."""
    import requests

    url_limpia = limpiar_url(url)
    ok, motivo = es_url_segura(url_limpia)
    if not ok:
        return None, motivo

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SilvestraAssistant/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    try:
        r = requests.get(url_limpia, headers=headers, timeout=TIMEOUT_RED, stream=True)
        if r.status_code != 200:
            return None, f"La página respondió con error HTTP {r.status_code}."

        contenido = bytearray()
        for trozo in r.iter_content(chunk_size=16384):
            contenido += trozo
            if len(contenido) > MAX_DESCARGA_BYTES:
                return None, "La página es demasiado pesada (supera el límite de 2 MB)."

        codificacion = r.encoding or "utf-8"
        try:
            texto = contenido.decode(codificacion, errors="replace")
        except Exception:
            texto = contenido.decode("utf-8", errors="replace")

        return texto, None
    except requests.exceptions.Timeout:
        return None, "La página tardó más de 10 segundos en responder."
    except requests.exceptions.RequestException as e:
        return None, f"No se pudo descargar la página ({e})."
