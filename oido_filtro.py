"""Filtro estricto de transcripciones del oído.

Solo descarta un texto cuando es un eco del último TTS o del prompt, o cuando
la transcripción es un bucle degenerado sin orden real. Una invocación
duplicada al inicio ("Lyris, Lyris, ...") se normaliza, no se descarta.
"""
import re
import unicodedata
from difflib import SequenceMatcher

_INVOCACION = re.compile(r"^(lyris|liris|iris)\b[\s,.:;!-]*", re.I)
_DUP_INVOCACION = re.compile(r"^((?:lyris|liris|iris)\b[\s,.:;!-]*){2,}", re.I)
_SOLO_INVOCACION = re.compile(r"^(?:lyris|liris|iris)\b[\s,.:;!-]*", re.I)


def normalizar_transcripcion(texto):
    """Colapsa invocaciones duplicadas al inicio, conservando la primera."""
    t = " ".join(str(texto or "").split())
    duplicado = _DUP_INVOCACION.match(t)
    if not duplicado:
        return t
    primero = _INVOCACION.match(duplicado.group(0)).group(1)
    resto = t[duplicado.end():].strip()
    separador = "," if re.search(r"[,.:;!]", duplicado.group(0)) else " "
    return f"{primero}{separador} {resto}".strip() if resto else primero


def _palabras(texto):
    """Tokens sin acentos ni puntuación, para comparar sin falsos negativos."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"\w+", t, re.UNICODE)


def es_bucle_degenerado(texto):
    """True ante n-gramas repetidos o tokens idénticos seguidos, nunca por palabras sueltas."""
    tik = _palabras(texto)
    if len(tik) < 4:
        return False
    for n in (4, 3, 2):
        vistos = set()
        for i in range(len(tik) - n + 1):
            frag = tuple(tik[i:i + n])
            if frag in vistos:
                return True
            vistos.add(frag)
    if any(tik[i] == tik[i - 1] == tik[i - 2] for i in range(2, len(tik))):
        return True
    return any(tik.count(w) >= 4 for w in set(tik) if len(w) >= 4)


def _normal(texto):
    sin_invocacion = _SOLO_INVOCACION.sub("", str(texto or ""), count=1)
    return " ".join(_palabras(sin_invocacion))


def _eco_real(texto, ultimo_dicho):
    """Eco del último TTS: igualdad, contenido total o similitud muy alta."""
    a, b = _normal(texto), _normal(ultimo_dicho)
    if len(a) < 8 or len(b) < 8:
        return False
    if a == b or (len(a) >= 12 and a in b):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.92


def debe_descartar(texto_original, texto, prompt, ultimo_dicho=""):
    """Único punto de decisión: devuelve True solo para eco o bucle degenerado."""
    if es_bucle_degenerado(texto_original):
        return True
    t = " ".join(str(texto or "").lower().split())
    p = " ".join(str(prompt or "").lower().split())
    if not t:
        return True
    if p and (t == p or (len(t) >= 10 and p.startswith(t))
              or (len(t) >= 40 and (p.startswith(t) or t in p))):
        return True
    return _eco_real(texto, ultimo_dicho)
