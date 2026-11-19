"""Procesamiento y parseo de respuestas devueltas por modelos de lenguaje."""
import re

_ETIQ_RESP = re.compile(r"RESPUESTA\s*\*{0,2}\s*:\s*\*{0,2}", re.I)
_ETIQ_FIN = re.compile(r"\s*\*{0,2}(ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)\*{0,2}\s*:", re.I)


def separar(texto):
    """Separa RESPUESTA, ACCION, RECUERDO y EMOCION de lo que devuelve el modelo."""
    texto = re.sub(r"(?is)<think>.*?</think>", "", texto or "").strip()
    etiqueta = re.compile(r"^[\W_]*(RESPUESTA|ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)[\s*_]*:[\s*_]*(.*)$", re.I)
    texto = re.sub(r"\s*\*{0,2}(RESPUESTA|ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)\*{0,2}\s*:", r"\n\1:", texto)
    antes, resp, recuerdo, accion, emocion = [], [], None, None, None
    actual = None
    for linea in texto.splitlines():
        s = linea.strip()
        if not s:
            continue
        m = etiqueta.match(s)
        if m:
            actual = m.group(1).upper().replace("Ó", "O")
            valor = m.group(2).strip()
            if actual == "RESPUESTA":
                resp.append(valor)
            elif actual == "ACCION":
                accion = valor
            elif actual == "EMOCION":
                emocion = valor
            else:
                recuerdo = valor
        elif actual == "RESPUESTA":
            resp.append(s)
        elif actual is None:
            antes.append(s)

    final = " ".join(p for p in (resp if resp else antes) if p).replace("*", "").strip()
    final = re.sub(r"(?i)\bEMOCI[OÓ]N\s*:\s*[a-zA-ZáéíóúÁÉÍÓÚñÑ]+", "", final).strip()
    if recuerdo and recuerdo.lower().strip(" .*") in ("", "ninguno", "ninguna", "nada"):
        recuerdo = None
    if accion:
        accion = accion.strip(" *")
        if accion.lower().strip(" .") in ("", "ninguno", "ninguna", "nada"):
            accion = None

    try:
        from voz import normalizar_emocion, deducir_emocion
        if emocion:
            palabra = emocion.split()[0].strip(" *.,;:-") if emocion.split() else ""
            emocion_final = normalizar_emocion(palabra)
        else:
            emocion_final = deducir_emocion(final)
    except Exception:
        emocion_final = "neutral"

    return final or (texto.strip() if texto else ""), accion, recuerdo, emocion_final


def _respuesta_parcial(crudo):
    """Lo que lleva dicho después de RESPUESTA: (o None si todavía no llega la etiqueta)."""
    m = _ETIQ_RESP.search(crudo)
    if not m:
        return None
    resto = crudo[m.end():]
    f = _ETIQ_FIN.search(resto)
    if f:
        resto = resto[:f.start()]
    return resto


def _cortar(parcial, emitido, final=False):
    """Saca las frases completas nuevas. Devuelve (frases, nuevo_emitido)."""
    pendiente = parcial[emitido:]
    frases, inicio = [], 0
    for m in re.finditer(r"[.!?…]+\s+", pendiente):
        frag = pendiente[inicio:m.end()].strip()
        if len(frag) >= 25:
            frases.append(frag.replace("*", ""))
            inicio = m.end()
    if final:
        resto = pendiente[inicio:].strip()
        if resto:
            frases.append(resto.replace("*", ""))
        inicio = len(pendiente)
    return frases, emitido + inicio
