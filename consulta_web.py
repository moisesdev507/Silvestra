"""Consulta de clima en tiempo real y búsqueda web compartida.

Totalmente compartido entre el motor clásico y Gemini Live.
- consultar_clima(ciudad="Panamá"): Open-Meteo sin API key requerida.
- buscar_web(consulta): Tavily API con fallback a DuckDuckGo HTML/Lite.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DUCKDUCKGO_LITE_URL = "https://html.duckduckgo.com/html/"

_CODIGOS_WMO = {
    0: "cielo despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna ligera",
    53: "llovizna moderada",
    55: "llovizna densa",
    61: "lluvia ligera",
    63: "lluvia moderada",
    65: "lluvia fuerte",
    71: "nevada ligera",
    73: "nevada moderada",
    75: "nevada fuerte",
    80: "chubascos dispersos",
    81: "chubascos moderados",
    82: "chubascos violentos",
    95: "tormenta eléctrica",
    96: "tormenta con granizo ligero",
    99: "tormenta con granizo fuerte",
}


def _limpiar_para_voz(texto: str) -> str:
    """Limpia URLs, corchetes, markdown y espacios redundantes."""
    t = str(texto or "")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\[\s*[^\]]*\s*\]", "", t)
    t = re.sub(r"[*_#`~>|]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _obtener_coordenadas(ciudad: str) -> Optional[Tuple[float, float, str, str]]:
    """Obtiene latitud, longitud, nombre y país desde Open-Meteo Geocoding."""
    c_limpia = str(ciudad or "Panamá").strip()
    if not c_limpia:
        c_limpia = "Panamá"
    params = urllib.parse.urlencode({
        "name": c_limpia,
        "count": 1,
        "language": "es",
        "format": "json"
    })
    url = f"{GEOCODING_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Silvestra-Clima/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results")
            if results and len(results) > 0:
                item = results[0]
                lat = float(item["latitude"])
                lon = float(item["longitude"])
                nom = str(item.get("name") or c_limpia)
                pais = str(item.get("country") or "")
                return lat, lon, nom, pais
    except Exception:
        pass
    # Fallback por defecto a Ciudad de Panamá si falla el geocoding
    if "panam" in c_limpia.lower():
        return 8.9833, -79.5167, "Ciudad de Panamá", "Panamá"
    return None


def consultar_clima(ciudad: str = "Panamá") -> str:
    """Consulta clima en tiempo real con Open-Meteo y devuelve formato natural para TTS."""
    coords = _obtener_coordenadas(ciudad)
    if not coords:
        return f"No encontré información geográfica para {ciudad}."

    lat, lon, nom_ciudad, pais = coords
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 1
    })
    url = f"{FORECAST_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Silvestra-Clima/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            curr = data.get("current", {})
            temp = round(float(curr.get("temperature_2m", 0.0)))
            sens = round(float(curr.get("apparent_temperature", temp)))
            hum = round(float(curr.get("relative_humidity_2m", 0.0)))
            w_code = int(curr.get("weather_code", 0))
            estado_cielo = _CODIGOS_WMO.get(w_code, "cielo variable")

            daily = data.get("daily", {})
            t_max_list = daily.get("temperature_2m_max", [])
            t_min_list = daily.get("temperature_2m_min", [])
            t_max = round(float(t_max_list[0])) if t_max_list else None
            t_min = round(float(t_min_list[0])) if t_min_list else None

            lugar = f"{nom_ciudad}, {pais}" if pais else nom_ciudad
            frase = f"En {lugar} hay {temp} grados con {estado_cielo} y una sensación térmica de {sens} grados."
            if t_max is not None and t_min is not None:
                frase += f" Para hoy se espera una máxima de {t_max} y una mínima de {t_min} grados."
            elif hum > 0:
                frase += f" La humedad relativa está en {hum}%."
            return frase
    except Exception as e:
        return f"No pude consultar el clima en {nom_ciudad} en este momento."


def _buscar_duckduckgo(consulta: str) -> str:
    """Fallback de búsqueda web rápida mediante DuckDuckGo HTML/Lite."""
    q = str(consulta or "").strip()
    if not q:
        return ""
    data = urllib.parse.urlencode({"q": q}).encode("utf-8")
    req = urllib.request.Request(
        DUCKDUCKGO_LITE_URL,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            # Extraer snippets de resultados en DuckDuckGo
            snippets = re.findall(r'<td class="result-snippet">\s*(.*?)\s*</td>', html, flags=re.DOTALL)
            if not snippets:
                snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, flags=re.DOTALL)
            textos = []
            for s in snippets[:3]:
                limpio = re.sub(r"<[^>]+>", " ", s)
                limpio = _limpiar_para_voz(limpio)
                if len(limpio) > 20:
                    textos.append(limpio)
            if textos:
                res = " ".join(textos)
                return res[:350].rsplit(".", 1)[0] + "." if "." in res[:350] else res[:320]
    except Exception:
        pass
    return ""


def buscar_web(consulta: str) -> str:
    """Busca en la web usando Tavily si está configurada, con fallback a DuckDuckGo."""
    q = str(consulta or "").strip()
    if not q:
        return "No indicaste qué buscar en internet."

    # 1. Intentar con Tavily a través del módulo busqueda_web existente
    try:
        import busqueda_web
        res_tavily = busqueda_web.buscar_web(q)
        if res_tavily and "falta la clave" not in res_tavily.lower() and "error" not in res_tavily.lower():
            return res_tavily
    except Exception:
        pass

    # 2. Fallback a DuckDuckGo Lite
    res_ddg = _buscar_duckduckgo(q)
    if res_ddg:
        return res_ddg

    return f"Busqué en la web sobre '{q}', pero no obtuve resultados claros en este momento."


def detectar_consulta_clima(texto: str) -> Optional[str]:
    """Detecta si el texto es una petición de clima y extrae la ciudad si aplica."""
    t = str(texto or "").lower().strip()
    if not t:
        return None
    if not any(k in t for k in ("clima", "tiempo", "temperatura", "va a llover", "está lloviendo", "pronostico", "pronóstico")):
        return None
    # Evitar falsos positivos como 'hace tiempo' o 'hace cuánto tiempo'
    if "hace tiempo" in t or "hace cuanto tiempo" in t or "hace cuánto tiempo" in t:
        return None

    # Extraer ciudad tras 'en' o 'para'
    m = re.search(r"\b(?:en|para|de)\s+([a-záéíóúñ\s]+?)(?:\?|$|\.|\,)", t)
    if m:
        ciudad_candidata = m.group(1).strip()
        # Filtrar palabras comunes que no son ciudades
        if ciudad_candidata not in ("hoy", "mañana", "la tarde", "la mañana", "la noche", "mi ciudad", "aquí", "aca", "este momento"):
            return ciudad_candidata.title()
    return "Panamá"


def detectar_consulta_busqueda(texto: str) -> Optional[str]:
    """Detecta si el texto es una búsqueda explícita en internet para respuesta hablada."""
    t = str(texto or "").strip()
    t_min = t.lower()
    if not t_min:
        return None

    patrones = [
        r"^busca en internet\s+(.*)",
        r"^busca en la web\s+(.*)",
        r"^buscar en internet\s+(.*)",
        r"^busca sobre\s+(.*)",
        r"^averigua sobre\s+(.*)",
        r"^averigua en internet\s+(.*)",
        r"^investiga en internet\s+(.*)",
        r"^investiga sobre\s+(.*)",
        r"^noticias sobre\s+(.*)",
        r"^que se sabe de\s+(.*)",
        r"^quién es\s+(.*)",
        r"^quien es\s+(.*)",
    ]
    for p in patrones:
        m = re.match(p, t_min)
        if m:
            query = m.group(1).strip()
            if query:
                return query
    return None


def responder_consulta_web_o_clima(texto: str) -> Optional[Tuple[str, Optional[str], str]]:
    """Procesa atajo de clima o búsqueda web para el motor clásico."""
    ciudad = detectar_consulta_clima(texto)
    if ciudad:
        res = consultar_clima(ciudad)
        return res, None, "alegre"

    query = detectar_consulta_busqueda(texto)
    if query:
        res = buscar_web(query)
        return res, None, "atenta"

    return None
