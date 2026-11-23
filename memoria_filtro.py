"""Filtro de calidad, privacidad y desduplicación para la memoria permanente."""
import re
import unicodedata
import math

import memoria_calidad

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "con",
    "por", "para", "que", "se", "su", "sus", "es", "son", "fue", "y", "o", "pero", "como", "le",
    "les", "lo", "me", "te", "nos", "mi", "mis", "tu", "tus", "suya", "suyo", "este", "esta",
    "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella", "usuario", "moises",
    "silvestra", "asistente", "esta", "estan", "estudiando", "repasando", "tiene", "tienen",
    "gusta", "interesa", "tambien"
}

PATRONES_SECRETOS = (
    r"\bsk-[A-Za-z0-9_-]{10,}\b", r"\bghp_[A-Za-z0-9]{16,}\b",
    r"\bBearer\s+[A-Za-z0-9._~+/-]{6,}",
    r"\b(?:token|password|contrase(?:ñ|n)a|clave|api[_ -]?key|apikey|secret|pin)\s*[:=]\s*\S+",
    r"\b(?:c[oó]digo|code|pin|cvv)\s+(?:temporal\s+)?(?:es\s+|[:=]\s*)?\d{4,8}\b",
    r"\b(?:\d[ -]*?){13,19}\b",
)
# Compatibilidad para memoria_grafo, que compara marcadores normalizados por subcadena.
PALABRAS_PRIVADAS = ("sk-", "ghp_", "bearer ", "token=", "password=", "contrasena=",
    "clave=", "api_key=", "apikey=", "secret=", "pin=", "cvv", "tarjeta de credito")
VALOR_SENSIBLE = re.compile(
    r"\b(?:token|password|contrase(?:ñ|n)a|clave|api[_ -]?key|apikey|secret|pin)"
    r"(?:\s+(?:secreto|actual|temporal|de\s+acceso|de\s+mi\s+cuenta))*"
    r"\s+(?:es|[:=])\s*([^\s,;.!?]+)", re.I
)

_PALABRA_SECRETO = (
    r"(?:contrase(?:ñ|n)a|clave|token|secret[o]|pin|cvv|"
    r"c[oó]digo\s+(?:de\s+seguridad|temporal|de\s+verificaci[oó]n)|api[_ -]?key)"
)
# Detecta menciones de secretos aunque NO tengan formato 'clave: valor',
# p. ej. 'Enela 1 cuenta con la contraseña generada.'
_VERBO_SECRETOS = (
    r"(?:cuenta\s+con|tiene|tengo|guard[oó]|guardad[oa]|cre[oó]|cread[oa]|gener[oó]|"
    r"generad[oa]|escribi[oó]|dijo|comparti[oó]|envia(?:do|da)?|recib[ií]|sabe)"
)
_PALABRA_SECRETO_POST = (
    r"\s+(?:generad[oa]|guardad[oa]|cread[oa]|temporal|actual|secreta|de\s+acceso|de\s+mi\s+cuenta)"
)
PATRON_MENCION_SECRETO = re.compile(
    _VERBO_SECRETOS + r"\s+(?:(?:la|el|una|un|mi|su)\s+)*" + _PALABRA_SECRETO
    + r"|" + _PALABRA_SECRETO + _PALABRA_SECRETO_POST,
    re.I,
)


def _alta_entropia(valor):
    if len(valor) < 18 or not re.search(r"[a-z]", valor, re.I) or not re.search(r"\d", valor):
        return False
    frecuencias = [valor.count(c) / len(valor) for c in set(valor)]
    return -sum(p * math.log2(p) for p in frecuencias) >= 3.2


def _contiene_secreto(texto):
    if any(re.search(p, texto, re.I) for p in PATRONES_SECRETOS):
        return True
    if PATRON_MENCION_SECRETO.search(texto):
        return True
    for valor in VALOR_SENSIBLE.findall(texto):
        if re.fullmatch(r"\d{4,8}", valor) or _alta_entropia(valor):
            return True
    return False


def contiene_pii(texto):
    """True si el texto menciona contraseñas, claves, tokens u otros secretos."""
    return _contiene_secreto(str(texto or ""))

PATRONES_META_NORMALIZADOS = [
    r"^\s*none\s*$",
    r"^\s*null\s*$",
    r"^\s*ningun[oa]\s*$",
    r"recordatorio\s*\|",
    r"accion\s*:\s*",
    r"respuesta\s*:\s*",
    r"\bhud\b",
    r"asistente\s+virtual",
    r"interfaz\s+de\s+usuario",
    r"proveedor(es)?(\s+de\s+ia)?",
    r"camara\s+(de\s+su\s+dispositivo|del\s+dispositivo)",
    r"desactivar\s+la\s+camara",
    r"tomar\s+una\s+foto",
    r"pedir\s+una\s+foto|pidio\s+una\s+foto",
    r"se\s+trabo\s+o\s+fallo",
    r"herramientas\s+virtuales",
    r"interactuo\s+con\s+(un[a]?\s+)?asistente",
    r"parece\s+tener\s+interes",
    r"parece\s+tener\s+una\s+rutina",
    r"lo\s+que\s+(sugiere|indica|podria\s+indicar)",
    r"muestra\s+resistencia",
    r"100\s+meses\s+y\s+necesita",
    r"niega\s+haber\s+pedido",
    r"\b(?:esta|estoy)\s+usando\s+(?:visual\s+studio\s+code|vs\s+code|vscode|antigravity\s+ide|chrome|google\s+chrome|microsoft\s+edge|edge|chatgpt|claude)\b",
    r"\b(?:tiene|tengo)\s+(?:abierto|abierta)\s+(?:el\s+|la\s+)?(?:archivo|ventana|aplicacion|app)\b",
    r"\b(?:archivo|ventana)\s+[\w.-]+\s+(?:abierto|abierta)\b",
    r"registre\s+el\s+tiempo\s+de\s+inicio",
    r"cerrar\s+programas",
    r"mejorar\s+mi\s+codigo",
    r"^\s*el\s+usuario\s+se\s+llama\s+moises\.?\s*$",
    r"\b(y|de|con|en|llamado|llamada)\s*$"
]


def normalizar_para_filtro(texto):
    """Convierte a minúsculas y remueve acentos para comparación tolerante."""
    if not texto:
        return ""
    t = re.sub(r"^\[[^\]]+\]\s*", "", texto).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def palabras_clave(texto):
    """Extrae conjunto de palabras significativas para comparar similitud."""
    t_norm = normalizar_para_filtro(texto)
    palabras = set(re.findall(r"\b[a-z]{3,}\b", t_norm))
    return palabras - STOPWORDS


def es_recuerdo_valido(hecho):
    """Valida que el hecho sea un dato concreto sobre el dueño y no basura meta ni privada."""
    if not hecho or not isinstance(hecho, str):
        return False, "vacío"

    limpio = re.sub(r"^\[[^\]]+\]\s*", "", hecho).strip()
    if len(limpio) < 12:
        return False, "demasiado corto"

    if _contiene_secreto(limpio):
        return False, "privacidad: posible valor secreto"

    norm = normalizar_para_filtro(limpio)
    for pat in PATRONES_META_NORMALIZADOS:
        if re.search(pat, norm):
            return False, f"patrón meta: {pat}"

    if memoria_calidad.es_autorreferencia_ia(limpio):
        return False, "autorreferencia de IA"

    return True, ""


def es_duplicado(nuevo_hecho, hechos_existentes):
    """Detecta duplicados exactos o semánticamente casi idénticos con alta coincidencia de palabras."""
    if not nuevo_hecho or not hechos_existentes:
        return False

    norm_nuevo = normalizar_para_filtro(nuevo_hecho)
    pk_nuevo = palabras_clave(nuevo_hecho)

    for existente in hechos_existentes:
        norm_existente = normalizar_para_filtro(existente)
        if norm_nuevo == norm_existente:
            return True

        pk_existente = palabras_clave(existente)
        if not pk_nuevo or not pk_existente:
            continue

        inter = len(pk_nuevo & pk_existente)
        union = len(pk_nuevo | pk_existente)
        sim_jaccard = inter / union
        sim_min = inter / min(len(pk_nuevo), len(pk_existente))

        # Solo proporciones: un solapamiento absoluto (p. ej. 4 palabras) no
        # puede descartar señal válida en frases largas con vocabulario distinto.
        if sim_jaccard >= 0.55 or (sim_min >= 0.80 and inter >= 3):
            return True

    return False


def recuerdos_con_pii(almacen, usuario_id=None, limite=10000):
    """Lista (id, contenido) de recuerdos activos que mencionan datos sensibles."""
    filas = almacen.listar_recuerdos(limite, solo_activos=True, usuario_id=usuario_id)
    return [(f["id"], f["contenido"]) for f in filas if contiene_pii(f.get("contenido"))]


def depurar_recuerdos_pii(almacen, usuario_id=None, aplicar=False, limite=10000):
    """Inspecciona o marca como eliminados los recuerdos con PII.

    Seguro por diseño: exige un almacén explícito (nunca abre la BD productiva)
    y solo escribe cuando `aplicar=True`. Devuelve un informe serializable.
    """
    if almacen is None:
        raise ValueError("depurar_recuerdos_pii requiere un almacén explícito")
    filas = almacen.listar_recuerdos(limite, solo_activos=True, usuario_id=usuario_id)
    sospechosos = [(f["id"], f["contenido"]) for f in filas if contiene_pii(f.get("contenido"))]
    informe = {
        "inspeccionados": len(filas),
        "sospechosos": len(sospechosos),
        "eliminados": 0,
        "detalle": [{"id": rid, "motivo": "PII detectada"} for rid, _ in sospechosos],
    }
    if not aplicar:
        return informe
    for rid, _ in sospechosos:
        try:
            if almacen.eliminar_recuerdo(rid, fisico=False, usuario_id=usuario_id):
                informe["eliminados"] += 1
        except Exception:
            continue
    return informe
