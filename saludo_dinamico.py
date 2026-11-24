"""Generador de saludo inicial espontáneo con memoria real y anti-repetición.

Usa personalidad F.R.I.D.A.Y., hilos abiertos, diario y hábitos locales.
Prioriza Groq (llama-3.1-8b-instant y qwen) con respaldo Cloudflare y fallback natural variado.
"""
import concurrent.futures
import datetime
import os
import random
import re
import time

import config
import estado
import httpx

DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")

MULETILLAS_PROHIBIDAS = (
    "¿en qué te puedo ayudar",
    "en que te puedo ayudar",
    "aquí tienes",
    "aqui tienes",
    "por supuesto",
    "estoy lista para ayudarte",
    "estoy lista para ayudar",
    "¿qué plan tienes",
    "que plan tienes",
    "¿cómo puedo ayudarte",
    "como puedo ayudarte",
    "¡hola! aquí",
)

FALLBACKS_NATURALES = (
    "De vuelta al puesto, Moisés; dime por dónde arrancamos hoy.",
    "Todo en orden por aquí, Moisés; ¿qué atacamos primero?",
    "Aquí estoy contigo, Moisés; listo el entorno para avanzar.",
    "Sistemas activos; cuando quieras retomamos lo que traías entre manos.",
    "Todo despejado por acá, Moisés; dime qué tenemos en radar.",
    "En línea y atenta; tú mandas con qué abrimos el turno.",
    "Sistemas listos, Moisés; continuamos con el código cuando digas.",
    "Buenas horas para concentrarse; dime en qué nos enfocamos hoy.",
)


def _log_saludo(mensaje):
    """Registra trazabilidad del saludo en consola y en silvestra.log."""
    print(f"[saludo] {mensaje}", flush=True)
    try:
        ruta_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra.log")
        momento = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ruta_log, "a", encoding="utf-8") as f:
            f.write(f"[{momento}] [saludo] {mensaje}\n")
    except Exception:
        pass


def _dato_calendario(timeout=0.45):
    """Consulta rápida a Google Calendar (<0.5s); devuelve evento breve o vacío."""
    try:
        import google_workspace
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(google_workspace.agenda_hoy)
            res = fut.result(timeout=timeout)
            if isinstance(res, dict) and res.get("ok"):
                eventos = res.get("eventos", [])
                if eventos:
                    ev = eventos[0]
                    tit = ev.get("resumen") or ev.get("titulo") or "evento"
                    ini = ev.get("inicio") or ev.get("hora") or ""
                    return f"Evento hoy: {tit} ({ini})." if ini else f"Evento hoy: {tit}."
    except Exception:
        pass
    return ""


def recopilar_memoria_saludo():
    """Recopila memoria real (< 50ms): hilos abiertos, perfil, diario y recuerdos."""
    datos = {}
    try:
        import hilos
        todos = hilos.cargar()
        abiertos = [h.get("texto", "").strip() for h in todos
                    if h.get("estado") == "abierto" and h.get("texto")
                    and h.get("texto").strip() != "NINGUNO."]
        if abiertos:
            datos["hilos_abiertos"] = abiertos[-3:]
    except Exception:
        pass

    try:
        import aprendizaje
        resumen_p = aprendizaje.resumen_para_prompt()
        if resumen_p:
            lineas = [l.strip() for l in resumen_p.splitlines() if l.strip()]
            for linea in lineas:
                if any(k in linea for k in ("Tema abierto:", "Referencias:", "Costumbres:")):
                    datos["perfil_estilo"] = linea[:180]
                    break
    except Exception:
        pass

    try:
        import diario
        if os.path.exists(diario.RUTA_DIARIO):
            with open(diario.RUTA_DIARIO, "r", encoding="utf-8", errors="replace") as f:
                contenido = f.read().strip()
                if contenido:
                    datos["ultimo_diario"] = " ".join(contenido[-220:].split())
    except Exception:
        pass

    try:
        import memoria_persistente as mp
        recuerdos = mp.listar_recuerdos()
        if recuerdos:
            datos["recuerdos_recientes"] = [r.get("valor", "") for r in recuerdos[:3] if r.get("valor")]
    except Exception:
        pass

    cal = _dato_calendario(timeout=0.45)
    if cal:
        datos["calendario"] = cal

    return datos


def fallback_natural_memoria(creador, memoria, ultimos_saludos=None):
    """Genera un fallback variado usando memoria real sin repetir los últimos 5."""
    if ultimos_saludos is None:
        ultimos_saludos = _obtener_ultimos_saludos()
    candidatos = list(FALLBACKS_NATURALES)

    hilos_act = memoria.get("hilos_abiertos") or []
    if hilos_act:
        ultimo_hilo = hilos_act[-1]
        candidatos.append(f"Moisés, listo el entorno; cuando quieras retomamos lo de {ultimo_hilo[:50]}.")
        candidatos.append(f"De vuelta al código, Moisés; ¿seguimos con {ultimo_hilo[:45]}?")

    recuerdos = memoria.get("recuerdos_recientes") or []
    if recuerdos:
        candidatos.append("Todo listo por acá, Moisés; ¿retomamos lo que teníamos pendiente?")

    no_repetidos = [s for s in candidatos if s not in ultimos_saludos]
    return random.choice(no_repetidos or candidatos)


def _obtener_ultimos_saludos():
    try:
        est = estado.cargar()
        u = est.get("ultimos_saludos", [])
        return list(u[-5:]) if isinstance(u, list) else []
    except Exception:
        return []


def _guardar_ultimo_saludo(saludo):
    try:
        est = estado.cargar()
        u = est.get("ultimos_saludos", [])
        if not isinstance(u, list):
            u = []
        u.append(str(saludo))
        est["ultimos_saludos"] = u[-5:]
        est["ultimo_saludo"] = str(saludo)
        est["ultima_vez"] = time.time()
        estado.guardar(est)
    except Exception:
        pass


def generar_saludo_dinamico(creador="Moisés", timeout=3.0):
    """Genera saludo espontáneo con Groq (llama-3.1 / qwen) o Cloudflare."""
    ahora = datetime.datetime.now()
    dia_sem = DIAS_SEMANA[ahora.weekday()]
    mes_nom = MESES[ahora.month - 1]
    hora_str = ahora.strftime("%I:%M %p").lstrip("0")
    fecha_str = f"{dia_sem} {ahora.day} de {mes_nom}"

    mem = recopilar_memoria_saludo()
    ultimos = _obtener_ultimos_saludos()

    bloques_memoria = []
    if mem.get("hilos_abiertos"):
        bloques_memoria.append("Hilos recientes: " + "; ".join(mem["hilos_abiertos"][:2]))
    if mem.get("perfil_estilo"):
        bloques_memoria.append("Estilo/hábitos: " + mem["perfil_estilo"])
    if mem.get("calendario"):
        bloques_memoria.append("Agenda próxima: " + mem["calendario"])
    if mem.get("recuerdos_recientes"):
        bloques_memoria.append("Recuerdos: " + "; ".join(mem["recuerdos_recientes"][:2]))

    ctx_texto = " | ".join(bloques_memoria) if bloques_memoria else "Sin temas específicos pendientes."
    no_repetir_txt = " | ".join(f'"{s}"' for s in ultimos) if ultimos else "Ninguno aún."

    momento = "madrugada" if ahora.hour < 6 else ("mañana" if ahora.hour < 12 else ("tarde" if ahora.hour < 19 else "noche"))

    sys_prompt = (
        f"Eres Lyris, la asistente personal de {creador}. Habla con la actitud de F.R.I.D.A.Y.: "
        "inteligente, perspicaz, relajada, directa y cómplice, como una colega cercana en el taller. "
        "Tu misión es dar un saludo inicial espontáneo y genuino en EXACTAMENTE 1 sola oración corta (de 8 a 18 palabras). "
        "REGLAS CRÍTICAS: "
        "- PROHIBIDO empezar con fórmulas fijas como 'Buenos días/tardes/noches, Moisés' o anunciar la hora exacta como un reloj ('Son las...'). "
        f"- Usa el momento del día ({momento}) solo como contexto de fondo sutil. "
        "- Elige un ángulo fresco y natural usando la memoria: retoma casualmente un hilo de trabajo, o haz un comentario espontáneo. "
        "- PROHIBIDO usar muletillas de robot como: '¿En qué te puedo ayudar?', 'Aquí tienes', 'Por supuesto', 'Estoy lista para ayudarte'. "
        f"- PROHIBIDO repetir o parafrasear estos saludos recientes: {no_repetir_txt}. "
        "- Devuelve ÚNICAMENTE la oración hablada, sin comillas, sin explicaciones ni etiquetas."
    )

    usr_prompt = (
        f"Usuario: {creador}. "
        f"Contexto temporal: {fecha_str}, {momento}. "
        f"Memoria activa: {ctx_texto}. "
        "Genera tu saludo espontáneo ahora."
    )

    clave_groq = str(getattr(config, "CLAVE", "") or os.environ.get("GROQ_API_KEY", "")).strip()
    motivo_fallo = ""
    if clave_groq:
        url_groq = "https://api.groq.com/openai/v1/chat/completions"
        headers_groq = {"Authorization": f"Bearer {clave_groq}", "Content-Type": "application/json"}
        for mod in ("llama-3.1-8b-instant", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"):
            try:
                payload = {
                    "model": mod,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": usr_prompt},
                    ],
                    "max_tokens": 50,
                    "temperature": 0.9,
                }
                resp = httpx.post(url_groq, headers=headers_groq, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    texto = re.sub(r"(?is)<think>.*?</think>", "", str(raw or "")).strip(' "“»«\'')
                    if "\n" in texto:
                        texto = texto.split("\n")[0].strip()
                    t_low = texto.lower()
                    if texto and len(texto.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                        _log_saludo(f"origen=modelo proveedor=Groq modelo={mod} texto='{texto}'")
                        _guardar_ultimo_saludo(texto)
                        return texto
                else:
                    motivo_fallo = f"Groq HTTP {resp.status_code} ({mod})"
            except Exception as e:
                motivo_fallo = f"Groq error ({mod}): {type(e).__name__}"

    clv_cf = str(getattr(config, "CLAVE_CLOUDFLARE", "") or os.environ.get("CLAVE_CLOUDFLARE", "")).strip()
    acc_cf = str(getattr(config, "ID_CUENTA_CLOUDFLARE", "") or os.environ.get("ID_CUENTA_CLOUDFLARE", "")).strip()
    if clv_cf and acc_cf:
        url_cf = f"https://api.cloudflare.com/client/v4/accounts/{acc_cf}/ai/v1/chat/completions"
        headers_cf = {"Authorization": f"Bearer {clv_cf}", "Content-Type": "application/json"}
        try:
            payload_cf = {
                "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                ],
                "max_tokens": 50,
                "temperature": 0.9,
            }
            resp_cf = httpx.post(url_cf, headers=headers_cf, json=payload_cf, timeout=timeout)
            if resp_cf.status_code == 200:
                raw_cf = resp_cf.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                texto_cf = re.sub(r"(?is)<think>.*?</think>", "", str(raw_cf or "")).strip(' "“»«\'')
                if "\n" in texto_cf:
                    texto_cf = texto_cf.split("\n")[0].strip()
                t_low = texto_cf.lower()
                if texto_cf and len(texto_cf.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                    _log_saludo(f"origen=modelo proveedor=Cloudflare modelo=llama-3.3-70b texto='{texto_cf}'")
                    _guardar_ultimo_saludo(texto_cf)
                    return texto_cf
            else:
                motivo_fallo = f"Cloudflare HTTP {resp_cf.status_code}"
        except Exception as e:
            motivo_fallo = f"Cloudflare error: {type(e).__name__}"

    saludo_fb = fallback_natural_memoria(creador, mem, ultimos)
    _log_saludo(f"origen=fallback motivo='{motivo_fallo or 'sin_respuesta_modelo'}' texto='{saludo_fb}'")
    _guardar_ultimo_saludo(saludo_fb)
    return saludo_fb
