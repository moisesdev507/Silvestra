"""Cadenas de proveedores LLM por tarea, clasificador de dificultad y estado."""
import re
import time

import config

CADENAS_ORDEN = {
    "charla": ["Groq", "Google", "Cloudflare", "Mistral", "NVIDIA", "GitHub", "SambaNova", "OpenRouter", "Cerebras", "Cohere"],
    "razonamiento": ["Groq", "Google", "Mistral", "Cloudflare", "NVIDIA", "GitHub", "SambaNova", "OpenRouter", "Cerebras", "Cohere"],
    "vision": ["Groq", "Cloudflare", "Google", "Mistral", "NVIDIA", "OpenRouter", "GitHub"],
    "voz": ["Groq"],
    "fondo": ["Cloudflare", "NVIDIA", "GitHub", "SambaNova", "Google", "Mistral", "Cerebras", "OpenRouter", "Cohere"],
}

FRASE_EMERGENCIA_LOCAL = "Dame un segundito que se me fue la señal de mis cerebros, pero ya estoy reintentando reconectarme."
_avisados_clave_vacia = set()


def respuesta_emergencia_local():
    """Devuelve una respuesta local sin red en formato completo de Silvestra."""
    return (
        "EMOCION: calida\n"
        f"RESPUESTA: {FRASE_EMERGENCIA_LOCAL}\n"
        "ACCION: ninguna\n"
        "RECUERDO: ninguno"
    )


def lanzar_reintento_segundo_plano(obtener_cands_fn, tarea):
    """Reintenta en segundo plano tras una pausa para reconectar con los proveedores."""
    import threading
    import requests

    def _reintento():
        time.sleep(8.0)
        print(f"[tiempo] reintento en segundo plano: verificando recuperación para '{tarea}'", flush=True)
        try:
            cands = obtener_cands_fn(tarea)
            if cands:
                p = cands[0]
                m = (p.get("modelos_activos") or p.get("modelos", []))[0]
                url = f"{p['base_url'].rstrip('/')}/chat/completions"
                headers = {"Authorization": f"Bearer {p['clave']}", "Content-Type": "application/json"}
                from sesion_http import obtener_sesion
                r = obtener_sesion().post(
                    url,
                    headers=headers,
                    json={"model": m, "messages": [{"role": "user", "content": "ping"}]},
                    timeout=5.0,
                )
                if r.status_code == 200:
                    print(f"[tiempo] reintento en segundo plano: conexión restablecida con {p['nombre']} ({m})", flush=True)
        except Exception as e:
            print(f"[tiempo] reintento en segundo plano: aún no disponible ({e})", flush=True)

    threading.Thread(target=_reintento, daemon=True).start()


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

    if _PATRON_ENLACE.search(t) or _PATRON_CODIGO.search(t) or _PATRON_RAZONAMIENTO.search(t) or len(t) > 140:
        return "razonamiento"

    return "charla"


def _parsear_tiempo_segundos(cadena):
    """Parsea formatos como '14h23m', '6m0s', '25s' o números a segundos flotantes."""
    if not cadena or not isinstance(cadena, str):
        return None
    cad = cadena.strip().lower()
    try:
        return float(cad)
    except ValueError:
        pass
    m = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$", cad)
    if m:
        h = float(m.group(1) or 0)
        mins = float(m.group(2) or 0)
        s = float(m.group(3) or 0)
        total = h * 3600.0 + mins * 60.0 + s
        return total if total > 0 else None
    return None


def marcar_enfriamiento(enfriamientos, nombre, modelo=None, headers=None, motivo=None):
    """Pone a un modelo o proveedor en pausa diferenciando límites TPM (minuto) y TPD (día)."""
    headers = headers or {}
    motivo_str = str(motivo or "")
    motivo_lower = motivo_str.lower()

    # Detectar si el 429 fue por día (TPD/RPD) o por minuto (TPM/RPM)
    es_tpd = any(p in motivo_lower for p in ("tpd", "rpd", "per day", "por día", "por dia", "daily"))

    header_reset = (
        headers.get("x-ratelimit-reset-tokens")
        or headers.get("x-ratelimit-reset-requests")
        or headers.get("retry-after")
        or headers.get("Retry-After")
    )

    seg_parsed = _parsear_tiempo_segundos(header_reset)
    if seg_parsed and seg_parsed > 300:
        es_tpd = True

    tipo_limite = "TPD" if es_tpd else "TPM"

    if es_tpd:
        # Límite diario: enfriamiento de varias horas o hasta el reseteo
        duracion = seg_parsed if seg_parsed else 14400.0  # 4 horas por defecto
    else:
        # Límite por minuto: enfriamiento habitual de 60s
        duracion = min(120.0, max(5.0, seg_parsed)) if seg_parsed else 60.0

    ahora = time.time()
    tag_motivo = f" motivo='{motivo}'" if motivo else ""
    if modelo:
        clave = f"{nombre}::{modelo}"
        enfriamientos[clave] = ahora + duracion
        print(f"[tiempo] enfriamiento modelo={clave} tipo={tipo_limite} duracion={duracion:.0f}s{tag_motivo}", flush=True)
    else:
        enfriamientos[nombre] = ahora + duracion
        print(f"[tiempo] enfriamiento proveedor={nombre} tipo={tipo_limite} duracion={duracion:.0f}s{tag_motivo}", flush=True)


def proveedores_disponibles(tarea, enfriamientos, claves_anteriores):
    """Devuelve la lista de candidatos disponibles reseteando enfriamientos al cambiar claves."""
    global _avisados_clave_vacia
    ahora = time.time()
    mapa_claves = {
        "Groq": getattr(config, "CLAVE", ""),
        "Cloudflare": getattr(config, "CLAVE_CLOUDFLARE", "") + getattr(config, "ID_CUENTA_CLOUDFLARE", ""),
        "Google": getattr(config, "CLAVE_GOOGLE", ""),
        "Mistral": getattr(config, "CLAVE_MISTRAL", ""),
        "NVIDIA": getattr(config, "CLAVE_NVIDIA", ""),
        "Cerebras": getattr(config, "CLAVE_CEREBRAS", ""),
        "OpenRouter": getattr(config, "CLAVE_OPENROUTER", ""),
        "GitHub": getattr(config, "CLAVE_GITHUB", ""),
        "SambaNova": getattr(config, "CLAVE_SAMBANOVA", ""),
        "Cohere": getattr(config, "CLAVE_COHERE", ""),
    }
    for n, clv in mapa_claves.items():
        if clv != claves_anteriores.get(n):
            claves_anteriores[n] = clv
            _avisados_clave_vacia.discard(n)
            claves_a_borrar = [k for k in enfriamientos if k == n or k.startswith(f"{n}::")]
            for k in claves_a_borrar:
                enfriamientos.pop(k, None)
            if claves_a_borrar:
                print(f"[tiempo] {n}: detectada nueva clave en config.py, reiniciando enfriamiento", flush=True)

    for ext in getattr(config, "PROVEEDORES_EXTRA", []):
        n = ext.get("nombre")
        clv = ext.get("clave", "")
        if n and clv != claves_anteriores.get(n):
            claves_anteriores[n] = clv
            _avisados_clave_vacia.discard(n)
            claves_a_borrar = [k for k in enfriamientos if k == n or k.startswith(f"{n}::")]
            for k in claves_a_borrar:
                enfriamientos.pop(k, None)
            if claves_a_borrar:
                print(f"[tiempo] {n} (extra): nueva clave detectada, reiniciando enfriamiento", flush=True)

    orden = CADENAS_ORDEN.get(tarea, CADENAS_ORDEN["charla"])
    for n in orden:
        clv = (mapa_claves.get(n) or "").strip()
        if not clv:
            if n not in _avisados_clave_vacia:
                _avisados_clave_vacia.add(n)
                print(f"[tiempo] cerebro saltando proveedor={n} motivo=clave_vacia", flush=True)
        elif ahora < enfriamientos.get(n, 0):
            restan = int(enfriamientos[n] - ahora)
            print(f"[tiempo] cerebro saltando proveedor={n} motivo=en_enfriamiento_por_cuota_faltan_{restan}s", flush=True)

    return obtener_candidatos_tarea(tarea, enfriamientos)


def refrescar_clave_proveedor(prov_dict):
    """Actualiza la clave dinámica y base_url del proveedor desde config.py."""
    nombre = prov_dict.get("nombre", "")
    attrs = {
        "Groq": "CLAVE", "Google": "CLAVE_GOOGLE", "Mistral": "CLAVE_MISTRAL",
        "NVIDIA": "CLAVE_NVIDIA", "Cerebras": "CLAVE_CEREBRAS", "OpenRouter": "CLAVE_OPENROUTER",
        "GitHub": "CLAVE_GITHUB", "SambaNova": "CLAVE_SAMBANOVA", "Cohere": "CLAVE_COHERE",
    }
    if nombre in attrs:
        prov_dict["clave"] = getattr(config, attrs[nombre], "")
    elif nombre == "Cloudflare":
        clv = getattr(config, "CLAVE_CLOUDFLARE", "")
        acc_id = getattr(config, "ID_CUENTA_CLOUDFLARE", "")
        prov_dict["clave"] = clv if (clv and acc_id) else ""
        if acc_id:
            prov_dict["base_url"] = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/v1"
    return prov_dict


MODELOS_RAPIDOS_GROQ = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
MODELOS_RAPIDOS_GOOGLE = ["gemini-flash-lite-latest", "gemini-flash-latest"]


def obtener_modelos_tarea(prov_dict, tarea):
    """Devuelve la lista de modelos priorizados para una tarea específica."""
    nombre = prov_dict.get("nombre", "")
    clave_tarea = f"modelos_{tarea}"
    modelos = prov_dict.get(clave_tarea)
    if modelos is None:
        modelos = prov_dict.get("modelos", [])
    modelos = list(modelos)
    if nombre == "Groq":
        restantes = [
            m for m in modelos
            if m not in MODELOS_RAPIDOS_GROQ
            and "qwen" not in m.lower()
            and "gpt-oss" not in m.lower()
        ]
        modelos = list(MODELOS_RAPIDOS_GROQ) + restantes
    elif nombre == "Google":
        restantes = [m for m in modelos if m not in MODELOS_RAPIDOS_GOOGLE]
        modelos = [m for m in MODELOS_RAPIDOS_GOOGLE if m in modelos] + restantes
    return modelos


def obtener_candidatos_tarea(tarea, enfriamientos):
    """Devuelve la lista ordenada de proveedores aptos con sus modelos disponibles (no enfriados)."""
    ahora = time.time()
    orden_nombres = CADENAS_ORDEN.get(tarea, CADENAS_ORDEN["charla"])

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

        if ahora < enfriamientos.get(nombre, 0):
            continue

        modelos = obtener_modelos_tarea(p, tarea)
        if not modelos:
            continue

        import proveedores_validador as pv
        modelos_disponibles = [
            m for m in modelos
            if ahora >= enfriamientos.get(f"{nombre}::{m}", 0) and not pv.esta_desactivado(nombre, m)
        ]
        if not modelos_disponibles:
            continue

        p_candidato = dict(p)
        p_candidato["modelos_activos"] = modelos_disponibles
        candidatos.append(p_candidato)

    # Añadir PROVEEDORES_EXTRA al final de las cadenas
    extras = getattr(config, "PROVEEDORES_EXTRA", [])
    extras_cands = []
    import proveedores_validador as pv
    for ext in extras:
        n = ext.get("nombre") or "Extra"
        url = ext.get("url") or ext.get("base_url") or ""
        clv = (ext.get("clave") or "").strip()
        mods = ext.get("modelos") or []
        if not url or not clv or not mods or ahora < enfriamientos.get(n, 0):
            continue
        mods_act = [
            m for m in mods
            if ahora >= enfriamientos.get(f"{n}::{m}", 0) and not pv.esta_desactivado(n, m)
        ]
        if not mods_act:
            continue
        extras_cands.append({
            "nombre": n,
            "base_url": url,
            "clave": clv,
            "modelos": list(mods),
            "modelos_activos": mods_act,
        })

    if extras_cands:
        idx_cohere = next((i for i, c in enumerate(candidatos) if c["nombre"] == "Cohere"), -1)
        if idx_cohere >= 0:
            candidatos[idx_cohere:idx_cohere] = extras_cands
        else:
            candidatos.extend(extras_cands)

    return candidatos


def reporte_estado_proveedores(enfriamientos):
    """Genera el reporte de estado por tarea para voz y burbuja delegando en proveedores_estado."""
    import sys
    import proveedores_estado as pe
    return pe.reporte_estado_proveedores(enfriamientos, sys.modules[__name__])
