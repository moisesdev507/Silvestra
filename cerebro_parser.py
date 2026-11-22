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


def extraer_emocion_parcial(crudo):
    """Extrae tempranamente la emoción si el modelo la emite al principio del streaming."""
    if not crudo:
        return None
    m = re.search(r"\*{0,2}EMOCI[OÓ]N\*{0,2}\s*:\s*([a-zA-Záéíóúñ]+)", crudo, re.I)
    if m:
        try:
            from voz import normalizar_emocion
            return normalizar_emocion(m.group(1))
        except Exception:
            return None
    return None


def _respuesta_parcial(crudo):
    """Extrae el texto de la respuesta en streaming sin esperar la etiqueta o etiquetas finales."""
    if not crudo:
        return None
    # Si todavía está en razonamiento interno incompleto, esperar
    if "<think>" in crudo and "</think>" not in crudo:
        return None
    limpio = re.sub(r"(?is)<think>.*?</think>", "", crudo).strip()
    if not limpio:
        return None

    m = _ETIQ_RESP.search(limpio)
    if m:
        resto = limpio[m.end():]
        f = _ETIQ_FIN.search(resto)
        if f:
            resto = resto[:f.start()]
        return resto

    # Si no usa la etiqueta RESPUESTA:, pero emitió EMOCION: al inicio, saltarla
    lineas = [l for l in limpio.splitlines() if l.strip()]
    if lineas and re.match(r"^[\W_]*EMOCI[OÓ]N\s*:", lineas[0], re.I):
        lineas = lineas[1:]
    resto = "\n".join(lineas).strip()
    if not resto:
        return None
    f = _ETIQ_FIN.search(resto)
    if f:
        resto = resto[:f.start()]
    return resto.strip()


_CONECTORES_COLGANTES = {
    "de", "del", "en", "que", "y", "e", "o", "u", "a", "al", "con", "por",
    "para", "el", "la", "los", "las", "un", "una", "su", "sus", "mi", "mis",
    "tu", "tus", "sin", "sobre", "como", "pero", "sino", "aunque"
}


_PATRON_CORTE = re.compile(
    r"(?<!\b[ap]\. m)(?<!\b[ap]\.m)(?<!\b[ap])(?<!\b[0-9])[.!?]+(?:\s+(?=[A-ZÁÉÍÓÚ¡¿])|\n+|$)",
    re.I,
)


def _es_oracion_completa(texto):
    """Verifica que el fragmento sea una oración completa y no termine en conector o abreviatura."""
    t = (texto or "").strip()
    if not t or len(t) < 5:
        return False
    if re.search(r"\b[ap]\.$", t, re.I):
        return False
    # No cortar en extensiones de archivos
    if re.search(r"\.(?:py|txt|json|md|csv|log|html|js|exe|bat|db|tmp)[.!?]?$", t, re.I):
        return False
    # No cortar si termina en contraseña o token alfanumérico mixto
    if re.search(r"\b(?:[a-zA-Z]+[0-9]+|[0-9]+[a-zA-Z]+)[!.]?$", t):
        return False
    palabras = [w.lower() for w in re.findall(r"[a-záéíóúñ0-9]+", t)]
    if palabras and palabras[-1] in _CONECTORES_COLGANTES:
        return False
    return t[-1] in ".!?…"


def _cortar(parcial, emitido, final=False):
    """Saca las oraciones completas nuevas sin cortar en conectores ni abreviaturas."""
    pendiente = parcial[emitido:]
    frases, inicio = [], 0
    # Cortar por signos de puntuación evitando romper 'a. m.', números, contraseñas o extensiones
    for m in _PATRON_CORTE.finditer(pendiente):
        precedente = pendiente[:m.start()]
        # Evitar cortar extensiones de archivo como script.py o datos.json
        if re.search(r"\.(?:py|txt|json|md|csv|log|html|js|exe|bat|db|tmp)$", precedente, re.I):
            continue
        # Evitar cortar en contraseñas o tokens alfanuméricos con signos internos (ej: V9k!)
        if re.search(r"\b(?:[a-zA-Z]+[0-9]+|[0-9]+[a-zA-Z]+)[!.]?$", precedente):
            if not final or m.end() < len(pendiente):
                continue

        frag = pendiente[inicio:m.end()].strip().replace("*", "")
        if _es_oracion_completa(frag):
            frases.append(frag)
            inicio = m.end()

    if final:
        resto = pendiente[inicio:].strip().replace("*", "")
        if resto:
            palabras = [w.lower() for w in re.findall(r"[a-záéíóúñ0-9]+", resto)]
            if palabras and palabras[-1] in _CONECTORES_COLGANTES:
                pass
            else:
                if resto[-1] not in ".!?…":
                    resto += "."
                frases.append(resto)
        inicio = len(pendiente)
    return frases, emitido + inicio
