"""Entrenamiento conversacional, coincidencia difusa tolerante a Whisper y auto-propuesta proactiva de habilidades."""
import difflib
import re
import threading
import unicodedata

import acciones
import aprendiz_habilidades
import cerebro_grafo

_bloqueo = threading.RLock()
_propuesta_proactiva_pendiente = None


def normalizar_fonetico(texto):
    """Normaliza texto removiendo acentos y erratas fonéticas habituales de Whisper."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    limpio = "".join(c for c in t if unicodedata.category(c) != "Mn")

    # Mapeo de variantes y erratas fonéticas comunes
    reemplazos = [
        (r"\bcotrasena\b", "contrasena"),
        (r"\bcontrasina\b", "contrasena"),
        (r"\bcontrasenia\b", "contrasena"),
        (r"\bcntrasena\b", "contrasena"),
        (r"\bcontraccin\b", "contrasena"),
        (r"\bcarateles\b", "caracteres"),
        (r"\bhas\b", "hash"),
        (r"\buid\b", "uuid"),
    ]
    for pat, rep in reemplazos:
        limpio = re.sub(pat, rep, limpio)
    return limpio


def buscar_habilidad_difusa(texto, umbral_similitud=0.72):
    """Busca habilidades aprobadas mediante coincidencia difusa tolerante a Whisper (< 50 ms)."""
    if not texto or len(str(texto).strip()) < 3:
        return None, None

    t_norm = normalizar_fonetico(texto)
    palabras_usuario = [p for p in re.findall(r"[a-z0-9]+", t_norm) if len(p) >= 3]
    if not palabras_usuario:
        return None, None

    habs = aprendiz_habilidades.obtener_habilidades_aprobadas()
    if not habs:
        return None, None

    mejor_nombre = None
    mejor_info = None
    max_score = 0.0

    for nombre, info in habs.items():
        nom_norm = normalizar_fonetico(nombre.replace("_", " "))
        partes_nom = [p for p in nombre.split("_") if len(p) >= 3]

        # 1. Similitud global directa con SequenceMatcher
        sim_global = difflib.SequenceMatcher(None, t_norm, nom_norm).ratio()
        if sim_global >= umbral_similitud and sim_global > max_score:
            max_score = sim_global
            mejor_nombre = nombre
            mejor_info = info

        # 2. Similitud por palabras clave individuales
        for pu in palabras_usuario:
            for pn in partes_nom:
                sim_palabra = difflib.SequenceMatcher(None, pu, pn).ratio()
                if (sim_palabra >= 0.80 or pu in pn or pn in pu) and sim_palabra > max_score:
                    max_score = sim_palabra
                    mejor_nombre = nombre
                    mejor_info = info

    if mejor_nombre and max_score >= umbral_similitud:
        if mejor_nombre not in acciones.VIVAS:
            aprendiz_habilidades._activar_modulo_habilidad(mejor_nombre, mejor_info)
        try:
            import cerebro_trabajo
            cerebro_trabajo.actualizar_habilidad(mejor_nombre)
        except Exception:
            pass
        return mejor_nombre, mejor_info

    return None, None


def detectar_peticion_tecnica_nueva(texto):
    """Detecta si el usuario pide una tarea computacional o técnica que Silvestra no posee."""
    if not texto or len(str(texto).strip()) < 8:
        return None

    t = str(texto).strip()
    patron = r"\b(?:calcula|genera|convierte|obten|extrae|crea\s+un|haz\s+un)\s+([a-zA-Z0-9_\s]+)"
    m = re.search(patron, t, re.I)
    if not m:
        return None

    candidato = m.group(1).strip().lower()
    # Si ya existe como acción o habilidad aprobada, no es nueva
    todas_acciones = set(acciones.ACCIONES.keys()) | set(acciones.VIVAS.keys())
    candidato_slug = candidato.replace(" ", "_")
    if any(candidato_slug in acc or acc in candidato_slug for acc in todas_acciones):
        return None

    # Filtrar peticiones comunes que ya tienen enrutamiento nativo
    excluidos = ("recordatorio", "foto", "captura", "hud", "musica", "modo", "archivo", "volumen")
    if any(exc in candidato for exc in excluidos):
        return None

    return candidato


def gestionar_autoaprendizaje_proactivo(texto, app=None):
    """Maneja el flujo proactivo de proponer y programar habilidades ante tareas no existentes."""
    global _propuesta_proactiva_pendiente
    t = str(texto).strip().lower()

    # 1. Si el usuario confirma una propuesta previa ("sí", "hazlo", "apréndelo", "adelante")
    if _propuesta_proactiva_pendiente and re.search(r"\b(?:si|sí|hazlo|aprende|aprendelo|apréndelo|adelante|dale|prográmala|programala)\b", t):
        with _bloqueo:
            nom_habilidad = _propuesta_proactiva_pendiente
            _propuesta_proactiva_pendiente = None
        ok, msg = aprendiz_habilidades.aprender_habilidad(nom_habilidad, app=app)
        if ok:
            try:
                import cerebro_trabajo
                cerebro_trabajo.actualizar_habilidad(nom_habilidad)
            except Exception:
                pass
        return True, msg

    # 2. Detectar si pide una habilidad técnica nueva
    nueva_tarea = detectar_peticion_tecnica_nueva(texto)
    if nueva_tarea:
        with _bloqueo:
            _propuesta_proactiva_pendiente = nueva_tarea
        return True, f"Aún no tengo una acción para {nueva_tarea}, ¿quieres que la programe y la active ahora?"

    return False, ""


def detectar_y_guardar_leccion(texto, creador="Moisés"):
    """Detecta correcciones directas del usuario y las aprende en el grafo y directivas."""
    if not texto or len(str(texto).strip()) < 8:
        return False, ""

    t = str(texto).strip()
    patrones_correccion = [
        r"\b(?:no,\s+mejor|asi\s+no|así\s+no|no\s+lo\s+hagas\s+asi|no\s+lo\s+hagas\s+así)\s*[:,-]?\s*(.+)",
        r"\brecuerda\s+siempre\s+que\s+(.+)",
        r"\bcuando\s+te\s+diga\s+(.+?)\s+(?:haz|responde|debes)\s+(.+)",
    ]

    for pat in patrones_correccion:
        m = re.search(pat, t, re.I)
        if m:
            regla = m.group(1).strip(" .!,;")
            cerebro_grafo.registrar_hecho(creador, "regla_estilo", regla, 1.0, "persona", "regla")
            try:
                import correcciones
                correcciones.anotar_correccion(creador, regla)
            except Exception:
                pass
            return True, f"Entendido, {creador}. He guardado esa regla para tenerla siempre en cuenta."

    return False, ""
