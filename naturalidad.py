"""Naturalidad conversacional humana y autocorrección viva para Silvestra.

Maneja continuidad temporal entre turnos (evita repetición de saludos en charlas activas)
y captura correcciones directas en tiempo real ("no dije", "eso no es así")
para transmitirlas a correcciones.py e inyectar directivas al prompt.
"""
import re
import time
import unicodedata

# Estado conversacional en memoria RAM
_ULTIMO_TURNO_TS = 0.0
_ULTIMO_TEXTO_ASISTENTE = ""

DIRECTIVA_ACTIVA = (
    "[CONTINUIDAD: Charla activa (< 15 min). Prohibido volver a saludar (hola, qué tal). Sigue el hilo directo.]"
)
DIRECTIVA_REGRESO = (
    "[CONTINUIDAD: Regreso corto (15 min - 3 h). Retoma casual sin saludos formales.]"
)
DIRECTIVA_NUEVA = (
    "[CONTINUIDAD: Nueva conversación (> 3 h). Saludo fresco y natural según la hora del día.]"
)
DIRECTIVA_AUTOCORRECCION = (
    "[AUTOCORRECCIÓN: El usuario corrigió tu turno anterior. Reconoce el error con naturalidad breve "
    "(ej: 'Mala mía', 'Entendido') y responde lo correcto sin ponerte robótica ni pedir mil disculpas.]"
)


def normalizar(texto):
    """Quita tildes y normaliza a minúsculas para comparaciones semánticas."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def fijar_ultimo_turno_ts(ts):
    """Establece timestamp del último turno (usado en tests y resets)."""
    global _ULTIMO_TURNO_TS
    _ULTIMO_TURNO_TS = float(ts)


def fijar_ultimo_texto_asistente(txt):
    """Establece último texto del asistente (usado en tests)."""
    global _ULTIMO_TEXTO_ASISTENTE
    _ULTIMO_TEXTO_ASISTENTE = (txt or "").strip()


def registrar_turno_usuario(texto):
    """Registra timestamp de interacción del usuario."""
    global _ULTIMO_TURNO_TS
    _ULTIMO_TURNO_TS = time.time()


def registrar_turno_asistente(texto):
    """Registra la respuesta emitida por Silvestra para dar contexto a futuras correcciones."""
    global _ULTIMO_TEXTO_ASISTENTE
    if texto and texto.strip():
        _ULTIMO_TEXTO_ASISTENTE = texto.strip()


def obtener_pista_continuidad(ahora=None):
    """Calcula la directiva de continuidad según el tiempo transcurrido desde el último turno."""
    global _ULTIMO_TURNO_TS
    if _ULTIMO_TURNO_TS <= 0.0:
        return DIRECTIVA_NUEVA

    t_actual = time.time() if ahora is None else float(ahora)
    delta = max(0.0, t_actual - _ULTIMO_TURNO_TS)

    if delta < 900.0:  # < 15 minutos
        return DIRECTIVA_ACTIVA
    if delta < 10800.0:  # 15 minutos a 3 horas
        return DIRECTIVA_REGRESO
    return DIRECTIVA_NUEVA  # >= 3 horas


def evaluar_autocorreccion(texto_usuario, ultimo_asistente=None):
    """Detecta si el usuario corrige a Silvestra, la guarda y retorna directiva."""
    global _ULTIMO_TEXTO_ASISTENTE
    if not texto_usuario:
        return ""

    try:
        import correcciones
        es_corr = correcciones.es_correccion(texto_usuario)
    except Exception:
        es_corr = False

    if not es_corr:
        t_norm = normalizar(texto_usuario)
        patrones_extra = (
            r"\bno dije\b",
            r"\beso no es as[ií]\b",
            r"\bya no\b",
            r"\bas[ií] no\b",
            r"\bte equivocaste\b",
            r"\bno es eso\b",
        )
        for p in patrones_extra:
            if re.search(p, t_norm):
                es_corr = True
                break

    if es_corr:
        asistente_ref = ultimo_asistente or _ULTIMO_TEXTO_ASISTENTE
        try:
            import correcciones
            correcciones.registrar_correccion(asistente_ref, texto_usuario)
        except Exception as e:
            print(f"[naturalidad] Error al registrar corrección: {e}", flush=True)

        print(f"[naturalidad] correccion_capturada='{texto_usuario.strip()}'", flush=True)
        return DIRECTIVA_AUTOCORRECCION

    return ""


def obtener_directivas_naturalidad(texto_usuario=None, ahora=None):
    """Combina pista de continuidad temporal y autocorrección viva para el prompt."""
    directivas = []

    pista = obtener_pista_continuidad(ahora=ahora)
    if pista:
        directivas.append(pista)

    if texto_usuario:
        dir_corr = evaluar_autocorreccion(texto_usuario)
        if dir_corr:
            directivas.append(dir_corr)

    return "\n".join(directivas) if directivas else ""
