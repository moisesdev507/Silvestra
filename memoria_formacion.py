"""Evalúa relevancia y forma recuerdos con origen, confianza y tipo."""
from datetime import datetime, timezone
import re
import unicodedata

import memoria_filtro
from memoria_modelos import Recuerdo


AMBIGUAS = ("quizá", "tal vez", "parece", "al parecer", "creo que", "podría ser", "supongo")
RUIDO = ("hola", "gracias", "buenos dias", "buenas noches", "ok", "de acuerdo", "entiendo")
TEMPORAL = ("ahora", "hoy", "esta tarde", "mañana", "por ahora", "esta semana", "mientras")
PROCEDIMIENTO = ("paso 1", "primero", "despues", "luego", "cada vez que", "para hacer", "procedimiento")
EPISODICO = ("ayer", "anoche", "la semana pasada", "ocurrio", "fui a", "conoci", "termine")
ESTABLE = ("me gusta", "prefiero", "siempre", "trabajo en", "estudio", "mi objetivo", "decidi", "decidí")


def detectar_directiva(texto):
    original = str(texto or "")
    t = normalizar(original)
    no = r"\b(no guardes|no recuerdes|no almacenes|no memorices|no lo guardes|no lo recuerdes|no quiero que guardes|no quiero que recuerdes|prefiero que no guardes)\b"
    if re.search(no, t):
        return {"accion": "no_guardar", "contenido": ""}
    guardar = re.search(r"\b(?:recuerda(?:me)?(?: que| esto)?|guarda(?: que)?|anota(?: que)?|apunta(?: que)?)\b\s*[:,-]?\s*(.+)", original, re.I)
    if guardar:
        return {"accion": "guardar", "contenido": guardar.group(1).strip()}
    corregir = re.search(r"\b(?:corrige|actualiza|reemplaza)\s+(?:el\s+)?recuerdo\s+(.+?)\s+(?:por|a)\s+(.+)", original, re.I)
    if corregir:
        return {"accion": "corregir", "anterior": corregir.group(1).strip(), "nuevo": corregir.group(2).strip()}
    consulta = r"\b(que recuerdas de|que recuerdas|que sabes de|revisa mis recuerdos sobre|revisa mis recuerdos|consulta mi recuerdo sobre|consulta mi recuerdo)\b"
    if re.search(consulta, t):
        valor = re.sub(r".*?" + consulta, "", t).strip(" ?.!¿")
        return {"accion": "revisar", "consulta": valor or None}
    return {"accion": "ninguna"}


def historial_prohibido(historial):
    return any(detectar_directiva(m.get("content", "")).get("accion") == "no_guardar"
               for m in (historial or []) if m.get("role") == "user")


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").casefold())
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").split())


def _score(texto, contexto, frecuencia, fuente, explicito):
    t = normalizar(texto)
    temporal = any(x in t for x in map(normalizar, TEMPORAL))
    estable = any(x in t for x in map(normalizar, ESTABLE))
    ambiguous = any(normalizar(x) in t for x in AMBIGUAS)
    source = {"orden_explicita": 1.0, "conversacion": .76, "extraccion": .72,
              "recuerdo_modelo": .62, "multimodal": .48, "contexto": .45,
              "tarea": .68}.get(fuente, .58)
    factors = {
        "importancia": .82 if any(x in t for x in ("objetivo", "importante", "meta", "familia", "proyecto")) else .48,
        "utilidad_futura": .78 if estable or any(x in t for x in ("recordar", "necesito", "plan", "prefer")) else .42,
        "contexto": .72 if contexto else .45,
        "persistencia": .82 if estable or not temporal else .32,
        "frecuencia": min(.9, .42 + max(0, int(frecuencia) - 1) * .12),
        "temporalidad": .68 if temporal else .78,
        "calidad_fuente": source,
        "claridad": .35 if ambiguous else .9,
    }
    pesos = (.15, .15, .1, .15, .1, .08, .17, .1)
    return sum(v * p for v, p in zip(factors.values(), pesos)), factors, temporal, estable, ambiguous


def _tipo(texto, temporal, estable):
    t = normalizar(texto)
    if any(normalizar(x) in t for x in map(normalizar, PROCEDIMIENTO)):
        return "procedimental"
    if any(normalizar(x) in t for x in map(normalizar, EPISODICO)) or re.search(r"\b\d{4}-\d{2}-\d{2}\b", t):
        return "episodica"
    if temporal and not estable:
        return "trabajo"
    return "semantica"


def evaluar_candidato(contenido, usuario_id="local", fuente="recuerdo_modelo",
                      explicito=False, contexto=None, canal="texto", frecuencia=1):
    texto = str(contenido or "").strip()
    valido, razon = memoria_filtro.es_recuerdo_valido(texto)
    limpio = normalizar(texto).strip(" .!?¿¡")
    palabras = limpio.split()
    ruido = any(limpio == normalizar(x) or (len(palabras) <= 5 and limpio.startswith(normalizar(x) + " "))
                for x in RUIDO)
    if not valido or ruido:
        return {"aceptado": False, "motivo": razon or "ruido"}
    score, factores, temporal, estable, ambiguo = _score(texto, contexto, frecuencia, fuente, explicito)
    tipo = _tipo(texto, temporal, estable)
    if ambiguo and not explicito:
        if not temporal:
            return {"aceptado": False, "motivo": "ambiguo", "criterios": factores}
        tipo = "trabajo"
    umbral = .36 if explicito else .54
    if score < umbral:
        return {"aceptado": False, "motivo": "relevancia_insuficiente", "criterios": factores}
    origen = "explicito" if explicito else "inferido"
    confianza = min(.98, (.9 if explicito else .72) * factores["claridad"] * factores["calidad_fuente"])
    if ambiguo:
        confianza = min(.4, confianza)
    meta = {"fuente": fuente, "canal": canal, "fecha_obtencion": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "relevancia": round(score, 3), "criterios": factores,
            "contexto_disponible": bool(contexto)}
    item = Recuerdo(usuario_id, tipo, texto, origen, confianza, "general", meta,
                    datetime.now(timezone.utc).date().isoformat())
    return {"aceptado": True, "motivo": "aceptado", "criterios": factores,
            "relevancia": score, "recuerdo": item}
