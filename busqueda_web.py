"""Búsqueda web en vivo para Lyris usando Tavily API.

Procesa búsquedas rápidas con include_answer=True y search_depth='basic',
formateando y limpiando los resultados para lectura por voz (cero URLs ni markdown).
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
    # Quitar URLs tipo http:// o https://
    t = re.sub(r"https?://\S+", "", t)
    # Quitar corchetes y citas numéricas tipo [1], [2], [fuente]
    t = re.sub(r"\[\s*[^\]]*\s*\]", "", t)
    # Quitar marcas de markdown (negritas, cursivas, encabezados, viñetas)
    t = re.sub(r"[*_#`~>|]", " ", t)
    # Quitar paréntesis residuales con texto técnico o vacíos
    t = re.sub(r"\(\s*\)", "", t)
    # Unificar espacios y saltos de línea
    t = " ".join(t.split())
    return t.strip()


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
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        return f"No se pudo completar la búsqueda web: servicio no disponible ({e.code})."
    except (urllib.error.URLError, TimeoutError) as e:
        return "No se pudo conectar a la búsqueda web por tiempo de espera o fallo de red."
    except Exception:
        return "Ocurrió un error inesperado al consultar la búsqueda web."

    # Priorizar la respuesta sintetizada de Tavily si está presente
    partes = []
    respuesta_directa = data.get("answer")
    if respuesta_directa and isinstance(respuesta_directa, str):
        limpia_ans = _limpiar_para_voz(respuesta_directa)
        if limpia_ans:
            partes.append(limpia_ans)

    # Añadir snippets relevantes de los resultados
    resultados = data.get("results")
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

    resumen = " ".join(partes)
    # Limitar a ~650 caracteres para no abrumar al sintetizador de voz
    if len(resumen) > 650:
        resumen = resumen[:647].rstrip() + "..."

    return resumen


__all__ = ["buscar_web", "_limpiar_para_voz"]
