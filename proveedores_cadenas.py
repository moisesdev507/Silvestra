"""Cadenas de proveedores LLM por tarea, clasificador de dificultad y estado.

Separa las cadenas en:
(a) charla: modelo liviano primero para responder rápido y gastar pocos tokens.
(b) razonamiento: modelos potentes primero para código, análisis y preguntas complejas.
(c) vision: solo proveedores con soporte de imágenes (Groq, Google, Mistral, NVIDIA, OpenRouter).
(d) voz: reconocimiento de voz con Whisper y respaldo local Vosk.
"""
import re
import time

import config

CADENAS_ORDEN = {
    "charla": ["Groq", "Cerebras", "Google", "Mistral", "NVIDIA", "OpenRouter"],
    "razonamiento": ["Groq", "Mistral", "Google", "NVIDIA", "Cerebras", "OpenRouter"],
    "vision": ["Groq", "Google", "Mistral", "NVIDIA", "OpenRouter"],
    "voz": ["Groq"],
}

_PATRON_RAZONAMIENTO = re.compile(
    r"\b(piensa|piensa bien|razona|analiza|reflexiona|detalla|explica a fondo|paso a paso|"
    r"por qu[eé]|diferencia entre|compara|resuelve|calcula|algoritmo|complejidad|optimiza)\b",
    re.I,
)

_PATRON_CODIGO = re.compile(
    r"(\bdef\b|\bclass\b|\bimport\b|\bfunction\b|\bconst\b|\bvar\b|\blet\b|\bselect\b|\bfrom\b|"
    r"\bwhere\b|```|<html>|<\?php|==|!=|=>|->|\.py\b|\.js\b|\.html\b|\.json\b|\berror\b|"
    r"\btraceback\b|\bexcepci[oó]n\b|\bexception\b|\bbug\b)",
    re.I,
)

_PATRON_ENLACE = re.compile(r"https?://", re.I)


def clasificar_dificultad(texto):
    """Clasifica localmente el mensaje en 'charla' o 'razonamiento' sin llamadas de red."""
    if not texto or not isinstance(texto, str):
        return "charla"

    t = texto.strip()
    if not t:
        return "charla"

    # Enlaces o URLs requieren análisis profundo
    if _PATRON_ENLACE.search(t):
        return "razonamiento"

    # Código, errores de terminal o sintaxis de programación
    if _PATRON_CODIGO.search(t):
        return "razonamiento"

    # Petición explícita de pensar, comparar o analizar a fondo
    if _PATRON_RAZONAMIENTO.search(t):
        return "razonamiento"

    # Mensajes muy extensos (> 140 caracteres) suelen requerir síntesis compleja
    if len(t) > 140:
        return "razonamiento"

    return "charla"


def refrescar_clave_proveedor(prov_dict):
    """Actualiza la clave dinámica del proveedor desde config.py."""
    nombre = prov_dict.get("nombre", "")
    if nombre == "Groq":
        prov_dict["clave"] = getattr(config, "CLAVE", "")
    elif nombre == "Google":
        prov_dict["clave"] = getattr(config, "CLAVE_GOOGLE", "")
    elif nombre == "Mistral":
        prov_dict["clave"] = getattr(config, "CLAVE_MISTRAL", "")
    elif nombre == "NVIDIA":
        prov_dict["clave"] = getattr(config, "CLAVE_NVIDIA", "")
    elif nombre == "Cerebras":
        prov_dict["clave"] = getattr(config, "CLAVE_CEREBRAS", "")
    elif nombre == "OpenRouter":
        prov_dict["clave"] = getattr(config, "CLAVE_OPENROUTER", "")
    return prov_dict


def obtener_modelos_tarea(prov_dict, tarea):
    """Devuelve la lista de modelos priorizados para una tarea específica."""
    clave_tarea = f"modelos_{tarea}"
    modelos = prov_dict.get(clave_tarea)
    if modelos is not None:
        return list(modelos)
    return list(prov_dict.get("modelos", []))


def obtener_candidatos_tarea(tarea, enfriamientos):
    """Devuelve la lista ordenada de proveedores aptos y disponibles para una tarea."""
    ahora = time.time()
    orden_nombres = CADENAS_ORDEN.get(tarea, CADENAS_ORDEN["charla"])

    # Mapear proveedores configurados
    prov_map = {}
    for p in config.PROVEEDORES:
        copia = dict(p)
        refrescar_clave_proveedor(copia)
        prov_map[copia["nombre"]] = copia

    candidatos = []
    for nombre in orden_nombres:
        p = prov_map.get(nombre)
        if not p:
            continue

        clave = (p.get("clave") or "").strip()
        if not clave:
            continue

        modelos = obtener_modelos_tarea(p, tarea)
        if not modelos:
            # Si el proveedor no tiene modelos para esta tarea (ej. visión en Cerebras), se salta
            continue

        # Verificar enfriamiento por 429
        t_enfriar = enfriamientos.get(nombre, 0)
        if ahora < t_enfriar:
            continue

        p_candidato = dict(p)
        p_candidato["modelos_activos"] = modelos
        candidatos.append(p_candidato)

    return candidatos


def reporte_estado_proveedores(enfriamientos):
    """Genera el reporte de estado por tarea para voz y burbuja."""
    ahora = time.time()
    prov_map = {}
    for p in config.PROVEEDORES:
        copia = dict(p)
        refrescar_clave_proveedor(copia)
        prov_map[copia["nombre"]] = copia

    estados = {}
    todos = ["Groq", "Google", "Mistral", "NVIDIA", "Cerebras", "OpenRouter"]
    activos_nombres = []
    enfriando_nombres = []
    sin_clave_nombres = []

    for n in todos:
        p = prov_map.get(n)
        if not p:
            estados[n] = "No configurado"
            sin_clave_nombres.append(n)
            continue
        clave = (p.get("clave") or "").strip()
        if not clave:
            estados[n] = "Sin clave"
            sin_clave_nombres.append(n)
            continue
        t_fin = enfriamientos.get(n, 0)
        if ahora < t_fin:
            seg = int(t_fin - ahora)
            estados[n] = f"Enfriamiento ({seg}s restan)"
            enfriando_nombres.append(f"{n} ({seg}s)")
        else:
            estados[n] = "Activo"
            activos_nombres.append(n)

    # Resumen hablado conciso en español natural
    partes_voz = []
    if activos_nombres:
        partes_voz.append(f"Activos: {', '.join(activos_nombres)}.")
    if enfriando_nombres:
        partes_voz.append(f"En pausa por cuota: {', '.join(enfriando_nombres)}.")
    if sin_clave_nombres:
        partes_voz.append(f"Sin clave: {', '.join(sin_clave_nombres)}.")
    texto_voz = " ".join(partes_voz) if partes_voz else "No hay proveedores configurados."

    # Tarjeta estructurada para la burbuja
    lineas = ["🌐 ESTADO DE PROVEEDORES LLM:"]
    for n in todos:
        st = estados.get(n, "Desconocido")
        icono = "✅" if "Activo" in st else ("⏳" if "Enfriamiento" in st else "⚪")
        lineas.append(f"{icono} {n}: {st}")

    lineas.append("\n📋 CADENAS ACTIVAS:")
    for t_nom, t_desc in [
        ("charla", "Charla y órdenes"),
        ("razonamiento", "Razonamiento y código"),
        ("vision", "Visión artificial"),
    ]:
        cands = [p["nombre"] for p in obtener_candidatos_tarea(t_nom, enfriamientos)]
        ruta = " ➔ ".join(cands) if cands else "Ninguno disponible"
        lineas.append(f"• {t_desc}: {ruta}")

    lineas.append("• Voz a texto: Groq (Whisper) con respaldo local Vosk")

    texto_burbuja = "\n".join(lineas)
    return texto_voz, texto_burbuja
