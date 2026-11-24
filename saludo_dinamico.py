"""Generador de saludo inicial espontáneo con memoria real y anti-repetición.

Usa personalidad F.R.I.D.A.Y., hilos abiertos, diario y hábitos locales.
Inyecta la hora y franja horaria real del sistema como verdad inamovible para evitar alucinaciones.
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

FALLBACKS_FRANJAS = {
    "madrugada": (
        "De vuelta al puesto en plena madrugada, Moisés; dime por dónde arrancamos.",
        "Buenas horas para concentrarse en silencio; ¿qué atacamos primero?",
        "Veo que seguimos despiertos, Moisés; listo el entorno para avanzar.",
        "Sistemas activos a esta hora de la noche; cuando quieras continuamos.",
    ),
    "mañana": (
        "Buen inicio de jornada, Moisés; dime con qué abrimos el turno.",
        "Todo despejado por acá esta mañana; dime qué tenemos en radar.",
        "Listo el entorno para empezar el día, Moisés; tú mandas.",
        "Sistemas activos y listos para la jornada; ¿por dónde arrancamos?",
    ),
    "tarde": (
        "De vuelta al puesto esta tarde, Moisés; ¿qué atacamos primero?",
        "Todo en orden por aquí, Moisés; continuamos con el código cuando digas.",
        "Sistemas listos para la tarde; dime qué tenemos pendiente.",
        "En línea y atenta; tú mandas con qué seguimos hoy.",
    ),
    "noche": (
        "Todo en orden por aquí esta noche, Moisés; ¿retomamos lo pendiente?",
        "Sistemas activos para cerrar la jornada; dime qué atacamos.",
        "Aquí estoy contigo esta noche; listo el entorno para avanzar.",
        "De vuelta al puesto, Moisés; dime por dónde seguimos.",
    ),
}


def _log_saludo(mensaje):
    """Registra trazabilidad del saludo en consola y en silvestra.log."""
    print(f"[saludo] {mensaje}", flush=True)
    try:
        with open("silvestra.log", "a", encoding="utf-8") as f:
            t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{t}] [SALUDO] {mensaje}\n")
    except Exception:
        pass


def _determinar_franja(hora: int) -> str:
    """Calcula la franja horaria exacta según la hora local (00-23)."""
    if 0 <= hora < 6:
        return "madrugada"
    if 6 <= hora < 12:
        return "mañana"
    if 12 <= hora < 19:
        return "tarde"
    return "noche"


def _es_coherente_con_franja(texto: str, franja: str) -> bool:
    """Verifica defensivamente que el texto no contradiga la franja horaria real."""
    t = str(texto or "").lower()
    if franja in ("madrugada", "noche"):
        if any(x in t for x in ("buenas tardes", "esta tarde", "de la tarde", "al mediodía", "al mediodia", "buenos días")):
            return False
    elif franja == "mañana":
        if any(x in t for x in ("buenas tardes", "esta tarde", "buenas noches", "esta noche", "de la madrugada")):
            return False
    elif franja == "tarde":
        if any(x in t for x in ("buenos días", "esta mañana", "de la madrugada", "buenas noches")):
            return False
    return True


def _dato_calendario(timeout=0.45):
    """Consulta la agenda de hoy con timeout estricto (< 0.45s)."""
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
        res_perfil = aprendizaje.resumen_para_prompt()
        if res_perfil and res_perfil.strip():
            datos["perfil_estilo"] = res_perfil.strip()[:200]
    except Exception:
        pass

    try:
        import diario
        if os.path.exists(diario.RUTA_DIARIO):
            with open(diario.RUTA_DIARIO, "r", encoding="utf-8") as f:
                lineas = [ln.strip() for ln in f if ln.strip()]
                if lineas:
                    datos["diario_reciente"] = lineas[-1][:180]
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


def fallback_natural_memoria(creador, memoria, ultimos_saludos=None, franja=None):
    """Genera un fallback variado usando franja horaria y memoria sin repetir los últimos 5."""
    if ultimos_saludos is None:
        ultimos_saludos = _obtener_ultimos_saludos()
    if franja is None:
        franja = _determinar_franja(datetime.datetime.now().hour)

    candidatos = list(FALLBACKS_FRANJAS.get(franja) or FALLBACKS_FRANJAS["tarde"])

    hilos_act = memoria.get("hilos_abiertos") or []
    if hilos_act:
        ultimo_hilo = hilos_act[-1]
        candidatos.append(f"Moisés, listo el entorno; cuando quieras retomamos lo de {ultimo_hilo[:45]}.")
        candidatos.append(f"De vuelta al código, Moisés; ¿seguimos con {ultimo_hilo[:40]}?")

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
        estado.guardar(est)
    except Exception:
        pass


def generar_saludo_dinamico(creador="Moisés", timeout=3.0):
    """Genera saludo espontáneo con Groq o Cloudflare asegurando coherencia temporal."""
    ahora = datetime.datetime.now()
    dia_sem = DIAS_SEMANA[ahora.weekday()]
    mes_nom = MESES[ahora.month - 1]
    hora_str = ahora.strftime("%I:%M %p").lstrip("0")
    franja = _determinar_franja(ahora.hour)
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

    sys_prompt = (
        f"Eres Lyris, la asistente personal de {creador}. Habla con la actitud de F.R.I.D.A.Y.: "
        "inteligente, perspicaz, relajada, directa y cómplice. "
        "Tu misión es dar un saludo inicial espontáneo y genuino en EXACTAMENTE 1 sola oración corta (8 a 18 palabras). "
        "VERDAD ACTUAL INAMOVIBLE DEL SISTEMA: "
        f"La hora local real exacta es {hora_str} y la franja actual es ESTRICTAMENTE '{franja}'. "
        "REGLAS CRÍTICAS: "
        "- NUNCA inventes otra hora ni contradigas la franja actual (si es madrugada, jamás menciones tarde, mediodía o tardes). "
        "- Si un recuerdo antiguo menciona otra hora, NO la trates como la hora actual. "
        "- PROHIBIDO empezar con fórmulas fijas como 'Buenos días/tardes/noches, Moisés' o recitar la hora como un reloj ('Son las...'). "
        f"- Usa la franja '{franja}' solo como contexto sutil si encaja, o enfócate directamente en retomar hilos activos. "
        "- PROHIBIDO usar muletillas de robot: '¿En qué te puedo ayudar?', 'Aquí tienes', 'Por supuesto', 'Estoy lista para ayudarte'. "
        f"- PROHIBIDO repetir o parafrasear estos saludos recientes: {no_repetir_txt}. "
        "- Devuelve ÚNICAMENTE la oración hablada, sin comillas ni explicaciones."
    )

    usr_prompt = (
        f"Usuario: {creador}. "
        f"Hora real y franja: {hora_str} ({franja}, {fecha_str}). "
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
                    "temperature": 0.8,
                }
                resp = httpx.post(url_groq, headers=headers_groq, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    texto = re.sub(r"(?is)<think>.*?</think>", "", str(raw or "")).strip(' "“»«\'')
                    if "\n" in texto:
                        texto = texto.split("\n")[0].strip()
                    t_low = texto.lower()
                    if texto and len(texto.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                        if _es_coherente_con_franja(texto, franja):
                            _log_saludo(f"origen=modelo proveedor=Groq modelo={mod} texto='{texto}'")
                            _guardar_ultimo_saludo(texto)
                            return texto
                        motivo_fallo = f"Groq ({mod}) descartado por incoherencia de franja ({franja})"
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
                "temperature": 0.8,
            }
            resp_cf = httpx.post(url_cf, headers=headers_cf, json=payload_cf, timeout=timeout)
            if resp_cf.status_code == 200:
                raw_cf = resp_cf.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                texto_cf = re.sub(r"(?is)<think>.*?</think>", "", str(raw_cf or "")).strip(' "“»«\'')
                if "\n" in texto_cf:
                    texto_cf = texto_cf.split("\n")[0].strip()
                t_low = texto_cf.lower()
                if texto_cf and len(texto_cf.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                    if _es_coherente_con_franja(texto_cf, franja):
                        _log_saludo(f"origen=modelo proveedor=Cloudflare modelo=llama-3.3-70b texto='{texto_cf}'")
                        _guardar_ultimo_saludo(texto_cf)
                        return texto_cf
                    motivo_fallo = f"Cloudflare descartado por incoherencia de franja ({franja})"
            else:
                motivo_fallo = f"Cloudflare HTTP {resp_cf.status_code}"
        except Exception as e:
            motivo_fallo = f"Cloudflare error: {type(e).__name__}"

    saludo_fb = fallback_natural_memoria(creador, mem, ultimos, franja=franja)
    _log_saludo(f"origen=fallback motivo='{motivo_fallo or 'sin_respuesta_modelo'}' texto='{saludo_fb}'")
    _guardar_ultimo_saludo(saludo_fb)
    return saludo_fb


__all__ = [
    "generar_saludo_dinamico",
    "fallback_natural_memoria",
    "recopilar_memoria_saludo",
    "MULETILLAS_PROHIBIDAS",
    "_es_coherente_con_franja",
    "_determinar_franja",
]
