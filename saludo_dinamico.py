"""Generador de saludo inicial espontáneo con briefing proactivo y calidez en tono panameño sutil.

Revisa en paralelo memoria, Gmail y Calendar sin bloquear el arranque.
Respeta estrictamente la franja horaria real del sistema sin inventar horas.
"""
import datetime
import os
import random
import re

import config
import estado
import httpx
import identidad_origen
import briefing_proactivo as bp

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
        "Qué xopa {creador}, seguimos activos en la madrugada; dime por dónde le damos.",
        "Buenas horas para avanzar en calma, {creador}; ¿qué atacamos primero?",
        "Todo en orden a esta hora, {creador}; listo el entorno cuando quieras arrancar.",
    ),
    "mañana": (
        "Buen día {creador}, qué xopa; todo despejado por acá para arrancar la jornada.",
        "Listo el entorno esta mañana, {creador}; dime con qué abrimos el turno.",
        "Todo listo por acá, {creador}; cuando digas nos ponemos en marcha.",
    ),
    "tarde": (
        "Qué xopa {creador}, de vuelta por acá esta tarde; ¿qué atacamos primero?",
        "Todo en orden esta tarde, {creador}; continuamos con el código cuando quieras.",
        "En línea y atenta esta tarde, {creador}; tú mandas con qué seguimos.",
    ),
    "noche": (
        "Qué xopa {creador}, todo en orden esta noche; ¿retomamos lo que teníamos pendiente?",
        "Sistemas listos para cerrar la jornada, {creador}; dime qué tenemos en radar.",
        "Aquí estoy contigo esta noche, {creador}; listos para avanzar cuando gustes.",
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


def fallback_natural_memoria(creador, briefing=None, ultimos_saludos=None, franja=None):
    """Genera un fallback variado usando franja horaria y briefing sin repetir los últimos 5."""
    if ultimos_saludos is None:
        ultimos_saludos = _obtener_ultimos_saludos()
    if franja is None:
        franja = _determinar_franja(datetime.datetime.now().hour)
    if briefing is None:
        briefing = {}

    candidatos = [
        frase.format(creador=creador)
        for frase in (FALLBACKS_FRANJAS.get(franja) or FALLBACKS_FRANJAS["tarde"])
    ]

    correo = briefing.get("correo")
    if correo and isinstance(correo, dict):
        candidatos.append(f"Qué xopa {creador}, vi un correo de {correo.get('remitente')}; cuando gustes le echamos un ojo.")

    evento = briefing.get("evento")
    if evento and isinstance(evento, dict):
        candidatos.append(f"{creador}, acuérdate que hoy tienes {evento.get('titulo')} a las {evento.get('hora')}.")

    hilo = briefing.get("hilo_activo")
    if hilo:
        candidatos.append(f"Qué xopa {creador}, todo listo; ¿retomamos lo de {hilo[:40]}?")

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


def generar_saludo_dinamico(creador=identidad_origen.USUARIO_SIN_NOMBRE, timeout=3.0):
    """Genera saludo espontáneo y cálido con briefing proactivo de Gmail/Calendar/Memoria."""
    perfil = identidad_origen.nombre_usuario()
    if perfil:
        creador = perfil
    ahora = datetime.datetime.now()
    franja = _determinar_franja(ahora.hour)
    hora_str = ahora.strftime("%I:%M %p").lstrip("0")

    briefing = bp.recopilar_briefing_arranque(timeout_total=1.2)
    ultimos = _obtener_ultimos_saludos()

    # Armar novedades destacadas
    novedades = []
    token_aviso = None
    if briefing.get("correo"):
        c = briefing["correo"]
        novedades.append(f"Correo pendiente de {c['remitente']} sobre '{c['asunto']}'")
        token_aviso = c.get("token")
    elif briefing.get("evento"):
        ev = briefing["evento"]
        novedades.append(f"Evento próximo hoy: {ev['titulo']} ({ev['hora']})")
        token_aviso = ev.get("token")

    if briefing.get("hilo_activo"):
        novedades.append(f"Proyecto/hilo abierto: {briefing['hilo_activo']}")
    elif briefing.get("recuerdo_reciente"):
        novedades.append(f"Recuerdo de trabajo: {briefing['recuerdo_reciente']}")

    novedades_txt = " | ".join(novedades) if novedades else "Sin avisos urgentes; continuar con normalidad."
    no_repetir_txt = " | ".join(f'"{s}"' for s in ultimos) if ultimos else "Ninguno aún."

    sys_prompt = (
        identidad_origen.bloque_identidad(creador) + "\n"
        + f"Eres {identidad_origen.NOMBRE}, la compañera y asistente personal de {creador}. "
        "Habla en un tono cálido, cercano, relajado y natural con un toque sutil de español panameño "
        "(puedes usar de forma natural un 'Qué xopa' casual, sin exagerar ni sonar forzada). "
        "Tu misión es dar un saludo inicial en 1 o 2 oraciones habladas breves (máximo 28 palabras en total). "
        "VERDAD ACTUAL INAMOVIBLE DEL SISTEMA: "
        f"La hora local real exacta es {hora_str} y la franja actual es ESTRICTAMENTE '{franja}'. "
        "REGLAS CRÍTICAS: "
        f"- NUNCA contradigas la franja actual '{franja}' (si es madrugada o noche, prohibido decir 'buenas tardes' o 'al mediodía'). "
        "- Si hay un correo relevante o evento en el briefing, menciónalo con naturalidad brevemente. "
        "- Si no hay avisos urgentes, saluda cálida y directamente invitando a retomar lo pendiente. "
        "- Cero asteriscos, cero listas, cero citas numéricas. "
        "- PROHIBIDO usar muletillas de robot: '¿En qué te puedo ayudar?', 'Aquí tienes', 'Por supuesto', 'Estoy lista para ayudarte'. "
        f"- PROHIBIDO repetir o parafrasear estos saludos recientes: {no_repetir_txt}. "
        "- Devuelve ÚNICAMENTE la frase hablada, sin comillas ni explicaciones."
    )

    usr_prompt = (
        f"Usuario: {creador}. "
        f"Franja: {franja} ({hora_str}). "
        f"Briefing proactivo: {novedades_txt}. "
        "Genera tu saludo cálido ahora."
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
                    "max_tokens": 60,
                    "temperature": 0.8,
                }
                resp = httpx.post(url_groq, headers=headers_groq, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    texto = re.sub(r"(?is)<think>.*?</think>", "", str(raw or "")).strip(' "“»«\'')
                    if "\n" in texto:
                        texto = " ".join(texto.splitlines()).strip()
                    t_low = texto.lower()
                    if texto and len(texto.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                        if _es_coherente_con_franja(texto, franja):
                            _log_saludo(f"origen=modelo proveedor=Groq modelo={mod} texto='{texto}'")
                            _guardar_ultimo_saludo(texto)
                            if token_aviso:
                                bp.registrar_alerta_avisada(token_aviso)
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
                "max_tokens": 60,
                "temperature": 0.8,
            }
            resp_cf = httpx.post(url_cf, headers=headers_cf, json=payload_cf, timeout=timeout)
            if resp_cf.status_code == 200:
                raw_cf = resp_cf.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                texto_cf = re.sub(r"(?is)<think>.*?</think>", "", str(raw_cf or "")).strip(' "“»«\'')
                if "\n" in texto_cf:
                    texto_cf = " ".join(texto_cf.splitlines()).strip()
                t_low = texto_cf.lower()
                if texto_cf and len(texto_cf.split()) >= 4 and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                    if _es_coherente_con_franja(texto_cf, franja):
                        _log_saludo(f"origen=modelo proveedor=Cloudflare modelo=llama-3.3-70b texto='{texto_cf}'")
                        _guardar_ultimo_saludo(texto_cf)
                        if token_aviso:
                            bp.registrar_alerta_avisada(token_aviso)
                        return texto_cf
                    motivo_fallo = f"Cloudflare descartado por incoherencia de franja ({franja})"
            else:
                motivo_fallo = f"Cloudflare HTTP {resp_cf.status_code}"
        except Exception as e:
            motivo_fallo = f"Cloudflare error: {type(e).__name__}"

    saludo_fb = fallback_natural_memoria(creador, briefing, ultimos, franja=franja)
    _log_saludo(f"origen=fallback motivo='{motivo_fallo or 'sin_respuesta_modelo'}' texto='{saludo_fb}'")
    _guardar_ultimo_saludo(saludo_fb)
    if token_aviso:
        bp.registrar_alerta_avisada(token_aviso)
    return saludo_fb


__all__ = [
    "generar_saludo_dinamico",
    "fallback_natural_memoria",
    "MULETILLAS_PROHIBIDAS",
    "_es_coherente_con_franja",
    "_determinar_franja",
]
