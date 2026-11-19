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
    "charla": ["Groq", "Cerebras", "Cloudflare", "Google", "Mistral", "NVIDIA", "OpenRouter", "Cohere"],
    "razonamiento": ["Groq", "Mistral", "Cloudflare", "Google", "NVIDIA", "Cerebras", "OpenRouter", "Cohere"],
    "vision": ["Groq", "Cloudflare", "Google", "Mistral", "NVIDIA", "OpenRouter"],
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


def marcar_enfriamiento(enfriamientos, nombre, modelo=None, headers=None):
    """Pone a un modelo o proveedor en pausa durante 60 s o según Retry-After (máx 60 s)."""
    duracion = 60.0
    if headers:
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                duracion = min(60.0, max(5.0, float(ra)))
            except ValueError:
                duracion = 60.0
    ahora = time.time()
    if modelo:
        clave = f"{nombre}::{modelo}"
        enfriamientos[clave] = ahora + duracion
        print(f"[tiempo] enfriamiento modelo={clave} duracion={duracion:.0f}s", flush=True)
    else:
        enfriamientos[nombre] = ahora + duracion
        print(f"[tiempo] enfriamiento proveedor={nombre} duracion={duracion:.0f}s", flush=True)


def proveedores_disponibles(tarea, enfriamientos, claves_anteriores):
    """Devuelve la lista de candidatos disponibles reseteando enfriamientos al cambiar claves."""
    ahora = time.time()
    mapa_claves = {
        "Groq": getattr(config, "CLAVE", ""),
        "Cloudflare": getattr(config, "CLAVE_CLOUDFLARE", "") + getattr(config, "ID_CUENTA_CLOUDFLARE", ""),
        "Google": getattr(config, "CLAVE_GOOGLE", ""),
        "Mistral": getattr(config, "CLAVE_MISTRAL", ""),
        "NVIDIA": getattr(config, "CLAVE_NVIDIA", ""),
        "Cerebras": getattr(config, "CLAVE_CEREBRAS", ""),
        "OpenRouter": getattr(config, "CLAVE_OPENROUTER", ""),
        "Cohere": getattr(config, "CLAVE_COHERE", ""),
    }
    for n, clv in mapa_claves.items():
        if clv != claves_anteriores.get(n):
            claves_anteriores[n] = clv
            claves_a_borrar = [k for k in enfriamientos if k == n or k.startswith(f"{n}::")]
            for k in claves_a_borrar:
                enfriamientos.pop(k, None)
            if claves_a_borrar:
                print(f"[tiempo] {n}: detectada nueva clave en config.py, reiniciando enfriamiento", flush=True)

    orden = CADENAS_ORDEN.get(tarea, CADENAS_ORDEN["charla"])
    for n in orden:
        clv = (mapa_claves.get(n) or "").strip()
        if not clv:
            print(f"[tiempo] cerebro saltando proveedor={n} motivo=clave_vacia", flush=True)
        elif ahora < enfriamientos.get(n, 0):
            restan = int(enfriamientos[n] - ahora)
            print(f"[tiempo] cerebro saltando proveedor={n} motivo=en_enfriamiento_por_cuota_faltan_{restan}s", flush=True)

    return obtener_candidatos_tarea(tarea, enfriamientos)


def refrescar_clave_proveedor(prov_dict):
    """Actualiza la clave dinámica y base_url del proveedor desde config.py."""
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
    elif nombre == "Cloudflare":
        clv = getattr(config, "CLAVE_CLOUDFLARE", "")
        acc_id = getattr(config, "ID_CUENTA_CLOUDFLARE", "")
        if not clv or not acc_id:
            prov_dict["clave"] = ""
        else:
            prov_dict["clave"] = clv
            prov_dict["base_url"] = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/v1"
    elif nombre == "Cohere":
        prov_dict["clave"] = getattr(config, "CLAVE_COHERE", "")
    return prov_dict


def obtener_modelos_tarea(prov_dict, tarea):
    """Devuelve la lista de modelos priorizados para una tarea específica."""
    clave_tarea = f"modelos_{tarea}"
    modelos = prov_dict.get(clave_tarea)
    if modelos is not None:
        return list(modelos)
    return list(prov_dict.get("modelos", []))


def obtener_candidatos_tarea(tarea, enfriamientos):
    """Devuelve la lista ordenada de proveedores aptos con sus modelos disponibles (no enfriados)."""
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

        # Verificar enfriamiento general del proveedor
        t_enfriar_prov = enfriamientos.get(nombre, 0)
        if ahora < t_enfriar_prov:
            continue

        modelos = obtener_modelos_tarea(p, tarea)
        if not modelos:
            # Si el proveedor no tiene modelos para esta tarea (ej. visión en Cerebras/Cohere)
            continue

        # Filtrar modelos que tengan su propio enfriamiento 429 activo
        modelos_disponibles = [m for m in modelos if ahora >= enfriamientos.get(f"{nombre}::{m}", 0)]
        if not modelos_disponibles:
            # Todos los modelos de este proveedor están agotados por cuota
            continue

        p_candidato = dict(p)
        p_candidato["modelos_activos"] = modelos_disponibles
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
    todos = ["Groq", "Cloudflare", "Google", "Mistral", "NVIDIA", "Cerebras", "OpenRouter", "Cohere"]
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

        # Evaluar enfriamiento general o de modelos
        t_fin_prov = enfriamientos.get(n, 0)
        prov_modelos = list(p.get("modelos", []))
        modelos_enfriados = []
        for m in prov_modelos:
            t_m = enfriamientos.get(f"{n}::{m}", 0)
            if ahora < t_m:
                modelos_enfriados.append((m, int(t_m - ahora)))

        if ahora < t_fin_prov:
            seg = int(t_fin_prov - ahora)
            estados[n] = f"Enfriamiento ({seg}s restan)"
            enfriando_nombres.append(f"{n} ({seg}s)")
        elif prov_modelos and len(modelos_enfriados) == len(prov_modelos):
            max_seg = max(s for _, s in modelos_enfriados)
            estados[n] = f"Enfriamiento ({max_seg}s restan)"
            enfriando_nombres.append(f"{n} ({max_seg}s)")
        elif modelos_enfriados:
            n_act = len(prov_modelos) - len(modelos_enfriados)
            estados[n] = f"Activo ({n_act}/{len(prov_modelos)} modelos)"
            activos_nombres.append(f"{n} ({n_act} mod)")
            enfriando_nombres.append(f"{n} ({len(modelos_enfriados)} mod en pausa)")
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
        extra_tag = " [Emergencia]" if n == "Cohere" else ""
        icono = "✅" if "Activo" in st else ("⏳" if "Enfriamiento" in st else "⚪")
        lineas.append(f"{icono} {n}{extra_tag}: {st}")

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
    lineas.append("• Respaldo de emergencia: Cohere (Trial 1,000 llamadas/mes)")

    texto_burbuja = "\n".join(lineas)
    return texto_voz, texto_burbuja
