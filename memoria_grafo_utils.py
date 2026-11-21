"""Normalización compartida para el grafo cognitivo."""
import re
import unicodedata


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", t, re.UNICODE))
