"""G2P español compacto: texto -> codepoints espeak para Piper VITS.

sherpa-onnx 2.x retiró el frontend espeak de los modelos VITS, así que la
síntesis local entrega fonemas vía ``GenerationConfig.phoneme_codepoints``.
"""
# Grafemas -> fonemas espeak usados por los modelos Piper en español (es-419).
_FONEMAS = {
    "a": "a", "á": "a", "b": "b", "c": "k", "d": "d", "e": "e", "é": "e",
    "f": "f", "g": "ɡ", "h": "", "i": "i", "í": "i", "j": "x", "k": "k",
    "l": "l", "m": "m", "n": "n", "ñ": "ɲ", "o": "o", "ó": "o", "p": "p",
    "q": "k", "r": "ɾ", "s": "s", "t": "t", "u": "u", "ú": "u", "ü": "u",
    "v": "v", "w": "w", "x": "ks", "y": "ʝ", "z": "s",
}


def fonemas_es(texto):
    """Devuelve una frase de codepoints espeak para GenerationConfig."""
    frases = []
    for palabra in str(texto or "").lower().split():
        partes = []
        i = 0
        while i < len(palabra):
            letra = palabra[i]
            sig = palabra[i + 1] if i + 1 < len(palabra) else ""
            if letra == "q" and sig == "u":
                partes.append("k")
                i += 2
                continue
            if letra == "g" and sig == "u" and palabra[i + 2:i + 3] in ("e", "i"):
                partes.append("ɡ")
                i += 2
                continue
            if letra == "r" and sig == "r":
                partes.append("r")
                i += 2
                continue
            if letra == "c" and sig in ("e", "i"):
                partes.append("s")
            elif letra == "g" and sig in ("e", "i"):
                partes.append("x")
            elif letra == "y" and (not partes or partes[-1] in "aeiou"):
                partes.append("i")
            else:
                partes.append(_FONEMAS.get(letra, ""))
            i += 1
        frases.extend(ord(c) for c in "".join(partes))
        frases.append(32)
    return [frases] if frases else []
