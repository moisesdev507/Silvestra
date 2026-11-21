"""Normalización conservadora para olvido y consultas temáticas."""
import re
import unicodedata
from difflib import SequenceMatcher

PREFIJOS = ("lo que te dije sobre", "lo que dije sobre", "lo que te conté sobre",
    "lo que te conte sobre", "olvida lo que te dije sobre", "olvida lo que te conte sobre",
    "acerca de", "respecto de", "en relación con", "sobre", "acerca", "de", "del", "lo de",
    "el", "la", "los", "las", "un", "una")
PARADA = set("a al algo algun alguna algunas algunos ambos ante antes como con contra cual cuales cuando de del desde donde durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha hacia hasta hay la las le les lo los me mi mis ni o para pero por que se si sin sobre su sus te tengo tu tus un una unas uno unos y ya dije diciendo hablado dije tema cosa cosas todo todos favor hola recuerda recuerdas".split())
GENERICOS = {"tema", "cosa", "cosas", "recuerdo", "recuerdos", "modulo", "metodo", "pago", "pagos", "algo", "esto"}


def plano(texto):
    t = unicodedata.normalize("NFD", str(texto or "").casefold())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def normalizar(tema):
    t = plano(tema).strip(" \t\r\n¿?¡!.,;:")
    cambia = True
    while cambia:
        cambia = False
        for prefijo in PREFIJOS:
            p = plano(prefijo)
            if t == p:
                t = ""
            elif t.startswith(p + " "):
                t = t[len(p):].strip()
            else:
                continue
            cambia = True
            break
    return re.sub(r"[^\w+#.-]+", " ", t, flags=re.UNICODE).strip()


def terminos(tema):
    nombres = _nombres(tema)
    palabras = {t if t in nombres or len(t) <= 4 else t.rstrip("s")
                for t in re.findall(r"[a-z0-9+#.-]+", normalizar(tema))
                if len(t) >= 3 and t not in PARADA}
    return set() if palabras and palabras <= GENERICOS else palabras


def _nombres(tema):
    raw = str(tema or "")
    salida = set()
    for match in re.finditer(r"[A-ZÁÉÍÓÚÑ][\w+#.-]*", raw):
        token = match.group()
        n = plano(token)
        if len(n) >= 7 and n not in GENERICOS and match.start() > 0:
            salida.add(n)
    return salida


def _cercano(nombre, disponibles):
    for token in disponibles:
        if nombre == token:
            return True
        if nombre[:4] == token[:4] and SequenceMatcher(None, nombre, token).ratio() >= .55:
            return True
    return False


def coincide(tema, contenido):
    nucleo = terminos(tema)
    if not nucleo:
        return False
    texto = {t.rstrip("s") if len(t) > 4 else t for t in re.findall(r"[a-z0-9+#.-]+", plano(contenido))}
    comunes = nucleo & texto
    nombres = _nombres(tema)
    if nombres:
        candidatos = set(re.findall(r"[a-z0-9+#.-]+", plano(contenido)))
        if not any(_cercano(n, candidatos) for n in nombres):
            return False
    minimo = 1 if len(nucleo) == 1 else min(2, len(nucleo))
    return len(comunes) >= minimo or bool(nombres and comunes and len(comunes) + 1 >= minimo)
