"""Conciencia temporal para el anclaje y recuperación fechada de recuerdos."""
import datetime
import re
import unicodedata

try:
    from zoneinfo import ZoneInfo
    _ZONA_PANAMA = ZoneInfo("America/Panama")
except Exception:
    _ZONA_PANAMA = None


def obtener_fecha_actual(fecha_ref=None):
    """Devuelve la fecha actual como datetime.date en la zona horaria de Panamá."""
    if isinstance(fecha_ref, datetime.date):
        return fecha_ref
    if isinstance(fecha_ref, datetime.datetime):
        return fecha_ref.date()
    try:
        if _ZONA_PANAMA:
            return datetime.datetime.now(_ZONA_PANAMA).date()
    except Exception:
        pass
    return datetime.date.today()


def normalizar_texto(texto):
    """Quita acentos y pasa a minúsculas para comparaciones semánticas."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def anclar_fechas_relativas(texto, fecha_ref=None):
    """Anexa la fecha calculada (DD/MM/YYYY) a menciones temporales relativas en el texto.
    
    Evita duplicar si la palabra ya contiene una fecha explícita adyacente.
    """
    if not texto or not isinstance(texto, str):
        return texto

    ref = obtener_fecha_actual(fecha_ref)

    # Patrón para detectar si ya hay una fecha cercana entre paréntesis o corchetes
    def ya_tiene_fecha_adyacente(pos_fin, s):
        cola = s[pos_fin:pos_fin + 25]
        return bool(re.match(r"^\s*[\(\[]?\d{1,2}[\/\-]\d{1,2}", cola))

    # Reglas ordenadas: de expresiones más largas/específicas a más cortas
    # (delta_dias, regex_pattern)
    reglas = [
        (2, re.compile(r"\bpasado\s+ma[nñ]ana\b", re.IGNORECASE)),
        (-2, re.compile(r"\b(anteayer|antes\s+de\s+ayer)\b", re.IGNORECASE)),
        (1, re.compile(r"\bma[nñ]ana\b", re.IGNORECASE)),
        (-1, re.compile(r"\bayer\b", re.IGNORECASE)),
        (0, re.compile(r"\b(esta\s+noche|esta\s+tarde|esta\s+ma[nñ]ana|hoy)\b", re.IGNORECASE)),
    ]

    resultado = texto
    offset = 0

    for delta, patron in reglas:
        for match in list(patron.finditer(resultado)):
            inicio = match.start()
            fin = match.end()
            palabra = match.group(0)

            # Si es 'mañana' pero viene precedido de 'de la' o 'por la' sin ser día (ej. 'a las 9 de la mañana')
            if normalizar_texto(palabra) == "manana":
                prefijo = resultado[max(0, inicio - 10):inicio].lower()
                if re.search(r"\b(de|por)\s+la\s*$", prefijo):
                    continue

            if ya_tiene_fecha_adyacente(fin, resultado):
                continue

            fecha_target = ref + datetime.timedelta(days=delta)
            fecha_str = f"({fecha_target.day:02d}/{fecha_target.month:02d}/{fecha_target.year})"

            reemplazo = f"{palabra} {fecha_str}"
            resultado = resultado[:inicio] + reemplazo + resultado[fin:]
            # Rompemos el ciclo de matches para esta regla y continuamos con el texto modificado
            break

    return resultado


def extraer_fecha_de_recuerdo(hecho):
    """Extrae fecha y contenido limpio de un recuerdo guardado en memoria."""
    if not hecho or not isinstance(hecho, str):
        return None, ""

    s = hecho.strip()
    # Formato ISO: [YYYY-MM-DD]
    m_iso = re.match(r"^\[(\d{4})-(\d{2})-(\d{2})\]\s*(.*)$", s)
    if m_iso:
        try:
            anio, mes, dia = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
            return datetime.date(anio, mes, dia), m_iso.group(4).strip()
        except Exception:
            pass

    # Formato DD/MM/YYYY: [DD/MM/YYYY] o [DD/MM/YYYY, ...]
    m_lat = re.match(r"^\[(\d{1,2})/(\d{1,2})/(\d{4})(?:,[^\]]+)?\]\s*(.*)$", s)
    if m_lat:
        try:
            dia, mes, anio = int(m_lat.group(1)), int(m_lat.group(2)), int(m_lat.group(3))
            return datetime.date(anio, mes, dia), m_lat.group(4).strip()
        except Exception:
            pass

    # Si trae etiqueta previa [fecha previa]
    m_prev = re.match(r"^\[fecha previa\]\s*(.*)$", s, re.IGNORECASE)
    if m_prev:
        return None, m_prev.group(1).strip()

    return None, s


def formatear_recuerdo_con_fecha(texto, timestamp_o_fecha=None, hoy=None):
    """Formatea un recuerdo para inyección al prompt con su fecha y antigüedad relativa.
    
    Ejemplos:
      - [18/11/2026, hace 2 días] Moisés tiene presentación mañana (19/11/2026)
      - [fecha previa] Le gusta el café negro
    """
    if not texto:
        return ""

    ref_hoy = obtener_fecha_actual(hoy)
    fecha_obj = None
    contenido = texto

    if timestamp_o_fecha:
        if isinstance(timestamp_o_fecha, datetime.date):
            fecha_obj = timestamp_o_fecha
        elif isinstance(timestamp_o_fecha, datetime.datetime):
            fecha_obj = timestamp_o_fecha.date()
        elif isinstance(timestamp_o_fecha, str):
            f_parse, c_parse = extraer_fecha_de_recuerdo(f"[{timestamp_o_fecha}] {texto}")
            if f_parse:
                fecha_obj = f_parse

    if not fecha_obj:
        f_extraida, c_extraida = extraer_fecha_de_recuerdo(texto)
        if f_extraida:
            fecha_obj = f_extraida
            contenido = c_extraida
        else:
            contenido = c_extraida

    if not fecha_obj:
        return f"[fecha previa] {contenido}"

    delta = (ref_hoy - fecha_obj).days
    if delta == 0:
        hace_txt = "hoy"
    elif delta == 1:
        hace_txt = "hace 1 día"
    elif delta > 1:
        hace_txt = f"hace {delta} días"
    elif delta == -1:
        hace_txt = "mañana"
    else:
        hace_txt = f"en {-delta} días"

    fecha_fmt = f"{fecha_obj.day:02d}/{fecha_obj.month:02d}/{fecha_obj.year}"
    return f"[{fecha_fmt}, {hace_txt}] {contenido}"
