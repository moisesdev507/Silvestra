"""Texto visible y frases hablables para el carril Pro.

Evita que una etiqueta de metadatos intermedia (EMOCION:, ACCION:,
RECUERDO:) deje sin voz el resto de una respuesta con lista Markdown.
"""
import re

import cerebro_parser as cp

_PIENSA = re.compile(r"(?is)<think>.*?</think>")
_ETIQUETA_RESP = re.compile(r"RESPUESTA\s*\*{0,2}\s*:\s*\*{0,2}", re.I)
_METADATOS = re.compile(
    r"[ \t]*\*{0,2}(?:ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)\*{0,2}[ \t]*:[^\n]*(?=\n|$)",
    re.I,
)
_NUMERADA = re.compile(r"(?m)^[ \t]*(\d{1,2})[.)][ \t]+")
_VINETA = re.compile(r"(?m)^[ \t]*[-*+•][ \t]+")
_ENCABEZADO = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*")
_ESPACIOS = re.compile(r"[ \t]{2,}")
_SALTOS = re.compile(r"\n{3,}")


def visible(crudo):
    """Devuelve solo el texto de la respuesta, sin recortar listas interiores."""
    texto = _PIENSA.sub("", str(crudo or ""))
    coincidencia = _ETIQUETA_RESP.search(texto)
    if coincidencia:
        texto = texto[coincidencia.end():]
    texto = _METADATOS.sub("", texto)
    return texto.strip()


def a_voz(texto):
    """Convierte Markdown a texto limpio y legible para TTS."""
    limpio = str(texto or "").replace("\r\n", "\n")
    limpio = re.sub(r"\*\*(.*?)\*\*", r"\1", limpio)
    limpio = re.sub(r"`([^`]+)`", r"\1", limpio)
    limpio = _ENCABEZADO.sub("", limpio)
    limpio = _NUMERADA.sub(lambda m: f"Punto {int(m.group(1))}: ", limpio)
    limpio = _VINETA.sub("Punto: ", limpio)
    limpio = limpio.replace("*", "").replace("__", "")
    limpio = _ESPACIOS.sub(" ", limpio)
    limpio = _SALTOS.sub("\n\n", limpio)
    return limpio.strip()


def frases(crudo, final=False):
    """Todas las frases hablables del stream acumulado, en orden."""
    texto = visible(crudo)
    if not texto:
        return []
    crudas, _ = cp._cortar(texto, 0, final=final)
    salida = []
    for fragmento in crudas:
        limpia = a_voz(fragmento).strip()
        if limpia:
            salida.append(limpia)
    return salida


def firma(frase):
    """Clave estable para no repetir una frase ya enviada al TTS."""
    return " ".join(str(frase or "").lower().split())
