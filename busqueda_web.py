"""Búsqueda web en vivo para Lyris usando Tavily API.

Procesa búsquedas rápidas con include_answer=True y search_depth='basic',
priorizando la síntesis directa de Tavily y recortando por oraciones completas.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

TAVILY_URL = "https://api.tavily.com/search"


def _limpiar_para_voz(texto: str) -> str:
    """Elimina URLs, markdown, corchetes, citas numéricas y saltos redundantes."""
    t = str(texto or "")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\[\s*[^\]]*\s*\]", "", t)
    t = re.sub(r"[*_#`~>|]", " ", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = " ".join(t.split())
    return t.strip()


def _recortar_oraciones(texto: str, max_oraciones: int = 3, max_chars: int = 320) -> str:
    """Recorta texto al final de una oración completa o en el último espacio sin truncar palabras."""
    t = str(texto or "").strip()
    if not t:
        return ""

    # Dividir oraciones manteniendo el delimitador
    patron = re.compile(r"([^.!?]+[.!?]+)")
    coincidencias = patron.findall(t)
    if coincidencias:
        acumulado = []
        caracteres = 0
        for oracion in coincidencias[:max_oraciones]:
            o_limpia = oracion.strip()
            if not o_limpia:
                continue
            if caracteres + len(o_limpia) + 1 <= max_chars or not acumulado:
                acumulado.append(o_limpia)
                caracteres += len(o_limpia) + 1
            else:
                break
        if acumulado:
            return " ".join(acumulado).strip()

    # Si no hay delimitador de oración o excede max_chars
    if len(t) <= max_chars:
        return t

    recorte = t[:max_chars]
    idx_espacio = recorte.rfind(" ")
    if idx_espacio > int(max_chars * 0.5):
        recorte = recorte[:idx_espacio].rstrip(" ,;:-")

    # Si no termina en puntuación, asegurar punto final limpio sin '...'
    if recorte and recorte[-1] not in ".!?":
        recorte += "."
    return recorte


def buscar_web(consulta: str, max_resultados: int = 3) -> str:
    """Busca en la web mediante Tavily API y devuelve un extracto limpio para voz."""
    q = str(consulta or "").strip()
    if not q:
        return "No indicaste ninguna consulta para buscar en la web."

    clave = ""
    try:
        import config
        clave = getattr(config, "TAVILY_API_KEY", "") or ""
    except Exception:
        clave = ""

    if not clave or not str(clave).strip():
        return "La búsqueda web no está configurada: falta la clave de Tavily."

    payload = {
        "api_key": str(clave).strip(),
        "query": q,
        "search_depth": "basic",
        "include_answer": True,
        "max_results": max(1, min(5, int(max_resultados or 3))),
    }

    try:
        cuerpo = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            TAVILY_URL,
            data=cuerpo,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Lyris-Silvestra/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return f"No se pudo completar la búsqueda web: servicio no disponible ({e.code})."
    except (urllib.error.URLError, TimeoutError):
        return "No se pudo conectar a la búsqueda web por tiempo de espera o fallo de red."
    except Exception:
        return "Ocurrió un error inesperado al consultar la búsqueda web."

    # 1. Priorizar EXCLUSIVAMENTE la síntesis 'answer' si contiene texto útil
    respuesta_directa = data.get("answer") if isinstance(data, dict) else ""
    if respuesta_directa and isinstance(respuesta_directa, str) and respuesta_directa.strip():
        limpia_ans = _limpiar_para_voz(respuesta_directa)
        if limpia_ans and len(limpia_ans) >= 10:
            return _recortar_oraciones(limpia_ans, max_oraciones=3, max_chars=320)

    # 2. Si 'answer' no existe o está vacío, usar snippets de 'results'
    partes = []
    resultados = data.get("results") if isinstance(data, dict) else []
    if isinstance(resultados, list):
        for item in resultados[:max_resultados]:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or item.get("snippet") or ""
            limpio_cnt = _limpiar_para_voz(content)
            if limpio_cnt and limpio_cnt not in partes:
                partes.append(limpio_cnt)

    if not partes:
        return f"No encontré resultados recientes para {q}."

    unido = " ".join(partes)
    return _recortar_oraciones(unido, max_oraciones=3, max_chars=320)


__all__ = ["buscar_web", "_limpiar_para_voz", "_recortar_oraciones"]
