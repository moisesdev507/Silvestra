"""Temas abiertos persistentes entre días e iniciativa orgánica para Kaya.

Guarda hasta 5 temas abiertos sin bloquear el turno (hilo daemon en segundo plano).
Expone un resumen ultraligero en RAM (< 180 chars) para saludo inicial y prompt.
Aplica reglas anti-fastidio con cooldown de 45-60 min y respeto al silencio cuando
el usuario está ocupado.
"""
import json
import os
import re
import threading
import time

RUTA_TEMAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos", "temas_abiertos_kaya.json")
MAX_TEMAS = 5
COOLDOWN_INICIATIVA_SEG = 45 * 60  # 45 minutos mínimo entre iniciativas espontáneas

_bloqueo = threading.RLock()
_cache_temas = None
_ultimo_disparo_iniciativa = 0.0

# Patrones para detectar resolución/cierre de temas
PATRONES_CIERRE_TEMA = [
    re.compile(r"\b(?:ya|por fin)\s+(?:termine|entregue|resolvi|arregle|quedo listo|solucione)\b", re.IGNORECASE),
    re.compile(r"\b(?:listo|cerrado|aprobado)\s+(?:lo de|el proyecto|la entrega|el parcial|la tarea)\b", re.IGNORECASE),
    re.compile(r"\bya\s+(?:no importa|esta listo|termino|paso)\b", re.IGNORECASE),
]

# Patrones para detectar proyectos, clases o temas abiertos relevantes
PATRONES_TEMA_ABIERTO = [
    re.compile(r"\b(?:estoy|ando|estaba|tengo que|debo)\s+(?:avanzando|trabajando|estudiando|haciendo|preparando|programando)\s+(?:con|en)?\s*([^,.:;!?]{6,60})", re.IGNORECASE),
    re.compile(r"\b(?:el proyecto|la entrega|el parcial|la clase|el examen|la tarea)\s+(?:de|para)\s+([^,.:;!?]{5,50})", re.IGNORECASE),
    re.compile(r"\b(?:mañana|esta semana|despues)\s+(?:tengo|debo|voy a)\s+(?:entregar|revisar|rendir|presentar)\s+([^,.:;!?]{5,50})", re.IGNORECASE),
]


def _asegurar_directorio():
    d = os.path.dirname(RUTA_TEMAS)
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def _cargar_disco():
    global _cache_temas
    if os.path.exists(RUTA_TEMAS):
        try:
            with open(RUTA_TEMAS, "r", encoding="utf-8") as f:
                _cache_temas = json.load(f)
                if isinstance(_cache_temas, list):
                    return _cache_temas
        except Exception:
            pass
    _cache_temas = []
    return _cache_temas


def obtener_temas_abiertos():
    """Devuelve la lista de temas abiertos en RAM (caché thread-safe)."""
    global _cache_temas
    with _bloqueo:
        if _cache_temas is None:
            return _cargar_disco()
        return list(_cache_temas)


def _guardar_disco(temas):
    _asegurar_directorio()
    try:
        with open(RUTA_TEMAS + ".tmp", "w", encoding="utf-8") as f:
            json.dump(temas, f, ensure_ascii=False, indent=2)
        import os
        os.replace(RUTA_TEMAS + ".tmp", RUTA_TEMAS)
    except Exception:
        pass


def registrar_tema_abierto(tema, contexto=""):
    """Registra o actualiza un tema abierto activo (hasta 5 temas)."""
    t_limpio = str(tema or "").strip().rstrip(".?!,:;")
    if len(t_limpio) < 4:
        return False
    ahora = time.time()
    with _bloqueo:
        temas = obtener_temas_abiertos()
        # Si ya existe un tema similar, actualizar timestamp
        for item in temas:
            if item.get("estado") == "abierto" and item.get("tema", "").lower() in t_limpio.lower():
                item["ultimo_seguimiento"] = ahora
                item["contexto"] = contexto or item.get("contexto", "")
                _guardar_disco(temas)
                return True

        # Filtrar solo abiertos
        abiertos = [t for t in temas if t.get("estado") == "abierto"]
        if len(abiertos) >= MAX_TEMAS:
            # Reemplazar el más antiguo
            abiertos.sort(key=lambda x: x.get("ultimo_seguimiento", 0.0))
            abiertos.pop(0)

        nuevo = {
            "tema": t_limpio,
            "contexto": str(contexto or "")[:80],
            "creado_en": ahora,
            "ultimo_seguimiento": ahora,
            "estado": "abierto"
        }
        abiertos.append(nuevo)
        global _cache_temas
        _cache_temas = abiertos
        _guardar_disco(abiertos)
        return True


def cerrar_tema(texto_usuario):
    """Cierra el tema que coincida con la resolución expresada por el usuario."""
    t_low = str(texto_usuario or "").lower()
    with _bloqueo:
        temas = obtener_temas_abiertos()
        cambiado = False
        for item in temas:
            if item.get("estado") == "abierto":
                palabras_clave = [p for p in item.get("tema", "").lower().split() if len(p) >= 4]
                if any(p in t_low for p in palabras_clave) or any(pat.search(t_low) for pat in PATRONES_CIERRE_TEMA):
                    item["estado"] = "resuelto"
                    item["cerrado_en"] = time.time()
                    cambiado = True
        if cambiado:
            # Conservar solo los últimos abiertos
            restantes = [t for t in temas if t.get("estado") == "abierto"]
            global _cache_temas
            _cache_temas = restantes
            _guardar_disco(restantes)
            return True
    return False


def procesar_turno_en_segundo_plano(texto_usuario, respuesta_kaya=""):
    """Analiza en hilo daemon si el turno abre o cierra temas, sin sumar latencia activa."""
    def _tarea():
        txt = str(texto_usuario or "").strip()
        if not txt:
            return

        # 1. Verificar si cierra algún tema pendiente
        if any(pat.search(txt) for pat in PATRONES_CIERRE_TEMA):
            if cerrar_tema(txt):
                return

        # 2. Verificar si abre o menciona un proyecto / tarea relevante
        for pat in PATRONES_TEMA_ABIERTO:
            m = pat.search(txt)
            if m:
                tema_extraido = m.group(1).strip()
                if len(tema_extraido) >= 5:
                    registrar_tema_abierto(tema_extraido, contexto=txt[:80])
                    break

    threading.Thread(target=_tarea, daemon=True).start()


def resumen_compacto_temas():
    """Devuelve un resumen de máximo ~180 caracteres para prompt o saludo."""
    temas = obtener_temas_abiertos()
    abiertos = [t for t in temas if t.get("estado") == "abierto"]
    if not abiertos:
        return ""
    # Tomar el más reciente
    abiertos.sort(key=lambda x: x.get("ultimo_seguimiento", 0.0), reverse=True)
    tema_top = abiertos[0]["tema"]
    resumen = f"Tema abierto pendiente: {tema_top}."
    return resumen[:180]


def resumen_memoria_con_sesion():
    """Resumen real y anti-repetición de Memoria para los prompts de Gemini Live."""
    try:
        import memoria_contexto
        return memoria_contexto.resumen_para_prompt()
    except Exception:
        return ""


def usuario_ocupado(app):
    """Detecta si el usuario está en llamada, hablando, reproduciendo música o con pantalla activa en video."""
    if not app:
        return False
    # 1. Si Kaya o el usuario están en turno de voz
    if getattr(app, "escuchando", False) or (hasattr(app, "voz") and app.voz.ocupada()):
        return True
    # 2. Si hay música activa o ducking
    if getattr(app, "musica_activa", False):
        return True
    # 3. Si la ventana activa es videoconferencia o streaming
    try:
        puente = getattr(app, "sistema_multimodal", None)
        if puente and hasattr(puente, "consultar_entorno_actual"):
            entorno = puente.consultar_entorno_actual() or {}
            proc = str((entorno.get("ventana") or {}).get("ejecutable", "")).lower()
            tit = str((entorno.get("ventana") or {}).get("titulo", "")).lower()
            apps_llamada = ("zoom.exe", "teams.exe", "discord.exe", "skype.exe")
            if any(a in proc for a in apps_llamada):
                return True
            if any(x in tit for x in ("youtube", "netflix", "meet.google.com", "call")):
                return True
    except Exception:
        pass
    return False


def evaluar_iniciativa_organica(app, ahora=None):
    """Devuelve una intervención orgánica cálida si se cumplen todas las reglas anti-fastidio."""
    global _ultimo_disparo_iniciativa
    momento = time.time() if ahora is None else float(ahora)

    # 1. Cooldown de 45 a 60 minutos
    with _bloqueo:
        if momento - _ultimo_disparo_iniciativa < COOLDOWN_INICIATIVA_SEG:
            return None

    # 2. Regla anti-fastidio: respeto estricto cuando el usuario está ocupado
    if usuario_ocupado(app):
        return None

    # 3. Obtener tema abierto que amerite seguimiento
    temas = obtener_temas_abiertos()
    abiertos = [t for t in temas if t.get("estado") == "abierto"]
    if not abiertos:
        return None

    abiertos.sort(key=lambda x: x.get("ultimo_seguimiento", 0.0))
    candidato = abiertos[0]

    # No fastidiar si ya se le preguntó hace menos de 4 horas por ese mismo tema
    if momento - candidato.get("ultimo_seguimiento", 0.0) < 4 * 3600:
        return None

    with _bloqueo:
        _ultimo_disparo_iniciativa = momento
        candidato["ultimo_seguimiento"] = momento
        _guardar_disco(temas)

    tema_nombre = candidato["tema"]
    frase = f"Oye, me quedé pensando: ¿cómo te fue con lo de {tema_nombre}?"
    return {
        "tipo": "iniciativa_tema",
        "mensaje": frase,
        "emocion": "calida",
        "timestamp": momento
    }
