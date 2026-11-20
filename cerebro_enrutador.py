"""Enrutador determinista de dos carriles: 'rapido' (gratis) vs 'pro' (avanzado)."""
import json
import re
import time
import unicodedata

import config

FRASES_EXPLICITAS_PRO = (
    "piensalo bien",
    "piensa bien",
    "analiza a fondo",
    "modo pro",
    "en detalle",
    "explica a profundidad",
    "a profundidad",
    "profundidad",
    "analisis detallado",
    "analisis profundo",
    "razona a fondo",
    "piensa con calma",
)

PALABRAS_TECNICAS_PRO = {
    "codigo", "algoritmo", "arquitectura", "debugging", "debug",
    "refactorizar", "optimizacion", "base de datos", "sql", "backend",
    "frontend", "excepcion", "traceback", "concurrencia", "asincrono",
    "rendimiento", "negocio", "estrategia", "comparativa", "complejidad",
    "patron de diseno", "unit test", "endpoint", "pull request",
}


def normalizar_texto(texto):
    """Quita tildes y convierte a minúsculas para comparaciones semánticas."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def decidir_carril(texto, modo_activo="normal", pro_disponible=False):
    """Clasificador local determinista (< 1 ms) para enrutar a 'rapido' o 'pro'.
    
    Retorna: (carril, motivo)
      carril: 'rapido' o 'pro'
      motivo: breve cadena descriptiva para telemetría
    """
    if not pro_disponible:
        return "rapido", "sin_pro_configurado"

    txt_norm = normalizar_texto(texto)
    if not txt_norm:
        return "rapido", "texto_vacio"

    # 1. Petición explícita del usuario
    for frase in FRASES_EXPLICITAS_PRO:
        if frase in txt_norm:
            return "pro", "solicitud_explicita_usuario"

    longitud = len(txt_norm)

    # Todo lo cotidiano, saludos, comandos cortos (< 80 caracteres) va a rápido
    if longitud < 80 and modo_activo not in ("programacion", "estudio"):
        return "rapido", "cotidiano_o_comando"

    # 2. Búsqueda de términos técnicos/analíticos
    palabras = set(re.findall(r"\b[a-z0-9_]{3,}\b", txt_norm))
    coincidencias_tecnicas = any(
        (t in txt_norm if " " in t else t in palabras)
        for t in PALABRAS_TECNICAS_PRO
    )

    # 3. Consulta compleja larga (>= 150 chars) con temática técnica o analítica
    if longitud >= 150 and coincidencias_tecnicas:
        return "pro", "consulta_compleja_tecnica"

    # 4. Modo programación o estudio con consulta técnica no trivial (>= 50 chars)
    if modo_activo in ("programacion", "estudio") and longitud >= 50 and coincidencias_tecnicas:
        return "pro", f"modo_{modo_activo}_tecnico"

    return "rapido", "general_o_cotidiano"


def verificar_pro_disponible():
    """Retorna True si existe una clave de proveedor Pro configurada y no vacía."""
    clave = (
        getattr(config, "PRO_API_KEY", None)
        or getattr(config, "OPENROUTER_API_KEY", None)
        or getattr(config, "ANTHROPIC_API_KEY", None)
    )
    return bool(clave and str(clave).strip())


def obtener_configuracion_pro():
    """Devuelve diccionario con proveedor, clave y modelo para el carril Pro."""
    clave_pro = getattr(config, "PRO_API_KEY", None)
    clave_openrouter = getattr(config, "OPENROUTER_API_KEY", None)
    clave_anthropic = getattr(config, "ANTHROPIC_API_KEY", None)

    proveedor_cfg = str(getattr(config, "PRO_PROVEEDOR", "")).strip().lower()

    if proveedor_cfg in ("anthropic", "claude"):
        prov = "anthropic"
        clave = clave_pro or clave_anthropic
    elif proveedor_cfg in ("openrouter", ""):
        if clave_pro or clave_openrouter:
            prov = "openrouter"
            clave = clave_pro or clave_openrouter
        elif clave_anthropic:
            prov = "anthropic"
            clave = clave_anthropic
        else:
            prov = "openrouter"
            clave = ""
    else:
        prov = proveedor_cfg
        clave = clave_pro or clave_openrouter

    modelo_cfg = getattr(config, "PRO_MODELO", None)
    if not modelo_cfg:
        if prov == "anthropic":
            modelo_cfg = "claude-3-5-haiku-20241022"
        else:
            modelo_cfg = "anthropic/claude-3.5-haiku"

    return {
        "proveedor": prov,
        "clave": str(clave or "").strip(),
        "modelo": str(modelo_cfg).strip(),
    }


def completar_pro(mensajes, tarea="charla", timeout=15.0):
    """Envía la solicitud al modelo Pro (OpenRouter o Anthropic directo)."""
    cfg = obtener_configuracion_pro()
    prov = cfg["proveedor"]
    clave = cfg["clave"]
    modelo = cfg["modelo"]

    if not clave:
        raise RuntimeError("No hay clave configurada para el carril Pro.")

    from sesion_http import obtener_sesion
    sesion = obtener_sesion()

    if prov == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": clave,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        system_text = ""
        user_assistant_msgs = []
        for m in mensajes:
            r = m.get("role", "user")
            c = m.get("content", "")
            if r == "system":
                system_text += f"\n{c}".strip()
            else:
                user_assistant_msgs.append({"role": r, "content": c})

        payload = {
            "model": modelo,
            "max_tokens": 1000,
            "temperature": 0.5,
            "system": system_text,
            "messages": user_assistant_msgs,
        }
        resp = sesion.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} desde Anthropic: {resp.text[:120]}")
        data = resp.json()
        content_list = data.get("content", [])
        if content_list and "text" in content_list[0]:
            return content_list[0]["text"]
        raise RuntimeError("Respuesta inesperada de Anthropic.")

    # Por defecto: OpenRouter / OpenAI compatible
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/moises/silvestra",
        "X-Title": "Silvestra Assistant",
    }
    payload = {
        "model": modelo,
        "messages": mensajes,
        "temperature": 0.5,
        "max_tokens": 1000,
    }
    resp = sesion.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} desde OpenRouter: {resp.text[:120]}")
    data = resp.json()
    choices = data.get("choices", [])
    if choices and "message" in choices[0]:
        return choices[0]["message"].get("content", "")
    raise RuntimeError("Respuesta inesperada de OpenRouter.")


def completar_pro_flujo(mensajes, al_frase=None, on_primer_token=None, on_emocion=None, timeout=15.0):
    """Envía la solicitud al modelo Pro con streaming de tokens y emisión de frases."""
    cfg = obtener_configuracion_pro()
    prov = cfg["proveedor"]
    clave = cfg["clave"]
    modelo = cfg["modelo"]

    if not clave:
        raise RuntimeError("No hay clave configurada para el carril Pro.")

    from sesion_http import obtener_sesion
    sesion = obtener_sesion()
    from cerebro_parser import _cortar, _respuesta_parcial, extraer_emocion_parcial

    crudo = ""
    emitido = 0
    primer_token_notificado = False
    emo_detectada = None

    if prov == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": clave,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        system_text = ""
        user_assistant_msgs = []
        for m in mensajes:
            r = m.get("role", "user")
            c = m.get("content", "")
            if r == "system":
                system_text += f"\n{c}".strip()
            else:
                user_assistant_msgs.append({"role": r, "content": c})

        payload = {
            "model": modelo,
            "max_tokens": 1000,
            "temperature": 0.5,
            "system": system_text,
            "messages": user_assistant_msgs,
            "stream": True,
        }
        resp = sesion.post(url, headers=headers, json=payload, stream=True, timeout=(4.0, timeout))
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} desde Anthropic: {resp.text[:120]}")

        for linea_raw in resp.iter_lines(decode_unicode=False):
            if not linea_raw:
                continue
            linea = linea_raw.decode("utf-8", errors="replace").strip()
            if not linea.startswith("data:"):
                continue
            data_str = linea[5:].strip()
            if not data_str or data_str == "[DONE]":
                break
            try:
                evento = json.loads(data_str)
                tipo = evento.get("type", "")
                if tipo == "content_block_delta":
                    delta = evento.get("delta", {})
                    texto_chunk = delta.get("text", "")
                    if texto_chunk:
                        if not primer_token_notificado:
                            primer_token_notificado = True
                            if callable(on_primer_token):
                                on_primer_token()
                        crudo += texto_chunk
                        if emo_detectada is None:
                            emo_detectada = extraer_emocion_parcial(crudo)
                            if emo_detectada and callable(on_emocion):
                                on_emocion(emo_detectada)
                        parcial = _respuesta_parcial(crudo)
                        if parcial is not None and callable(al_frase):
                            frases, emitido = _cortar(parcial, emitido)
                            for f in frases:
                                if f.strip():
                                    al_frase((f.strip(), emo_detectada) if emo_detectada else f.strip())
            except Exception:
                continue
    else:
        # OpenRouter / OpenAI compatible
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {clave}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/moises/silvestra",
            "X-Title": "Silvestra Assistant",
        }
        payload = {
            "model": modelo,
            "messages": mensajes,
            "temperature": 0.5,
            "max_tokens": 1000,
            "stream": True,
        }
        resp = sesion.post(url, headers=headers, json=payload, stream=True, timeout=(4.0, timeout))
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} desde OpenRouter: {resp.text[:120]}")

        for linea_raw in resp.iter_lines(decode_unicode=False):
            if not linea_raw:
                continue
            linea = linea_raw.decode("utf-8", errors="replace").strip()
            if not linea.startswith("data:"):
                continue
            data_str = linea[5:].strip()
            if not data_str or data_str == "[DONE]":
                break
            try:
                evento = json.loads(data_str)
                choices = evento.get("choices", [])
                if choices:
                    texto_chunk = choices[0].get("delta", {}).get("content", "")
                    if texto_chunk:
                        if not primer_token_notificado:
                            primer_token_notificado = True
                            if callable(on_primer_token):
                                on_primer_token()
                        crudo += texto_chunk
                        if emo_detectada is None:
                            emo_detectada = extraer_emocion_parcial(crudo)
                            if emo_detectada and callable(on_emocion):
                                on_emocion(emo_detectada)
                        parcial = _respuesta_parcial(crudo)
                        if parcial is not None and callable(al_frase):
                            frases, emitido = _cortar(parcial, emitido)
                            for f in frases:
                                if f.strip():
                                    al_frase((f.strip(), emo_detectada) if emo_detectada else f.strip())
            except Exception:
                continue

    # Emitir cualquier residuo pendiente al terminar el stream
    if callable(al_frase) and crudo:
        parcial = _respuesta_parcial(crudo)
        if parcial is not None and len(parcial) > emitido:
            resto = parcial[emitido:].strip()
            if resto:
                al_frase(resto)

    if not crudo:
        raise RuntimeError("No se recibieron tokens del stream Pro.")
    return crudo


def ejecutar_con_enrutador(texto, mensajes, tarea="charla", app=None, fallback_fn=None):
    """Enruta a 'rapido' o 'pro' con fallback transparente al carril rápido."""
    modo = "normal"
    if app and hasattr(app, "modo_activo"):
        modo = getattr(app, "modo_activo", "normal") or "normal"
    else:
        try:
            import modos_sistema
            modo = modos_sistema.obtener_modo_activo(app)
        except Exception:
            pass

    pro_disp = verificar_pro_disponible()
    carril, motivo = decidir_carril(texto, modo_activo=modo, pro_disponible=pro_disp)
    print(f"[enrutador] carril={carril} motivo={motivo}", flush=True)

    if carril == "pro":
        try:
            return completar_pro(mensajes, tarea=tarea)
        except Exception as e:
            print(f"[enrutador] fallback_pro->rapido motivo={e}", flush=True)

    if fallback_fn:
        return fallback_fn(mensajes, tarea=tarea)

    raise RuntimeError("No se pudo completar la solicitud con el enrutador.")
