"""Ciclo de vida, nacimiento, saludo inicial y renacer de Silvestra."""
import concurrent.futures
import datetime
import os
import random
import threading
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

# Banco local: el saludo de arranque no debe depender de la red.
SALUDOS = {
    "manana": (
        "Buenos días, {creador}. Soy {nombre}. Lista para empezar el día contigo.",
        "Buenos días, {creador}. Aquí estoy, despierta y lista para ayudarte.",
        "Buenos días, {creador}. Arrancamos suave: dime por dónde quieres empezar.",
    ),
    "tarde": (
        "Buenas tardes, {creador}. Soy {nombre}. Sigo aquí para lo que necesites.",
        "Buenas tardes, {creador}. Lista para continuar donde lo dejamos.",
        "Buenas tardes, {creador}. ¿Seguimos con lo pendiente o cambiamos de rumbo?",
    ),
    "noche": (
        "Buenas noches, {creador}. Estoy aquí si quieres cerrar el día en calma.",
        "Buenas noches, {creador}. Lista para acompañarte un rato antes de descansar.",
    ),
}


def franja_actual():
    """Devuelve la franja horaria y la emoción asociada al saludo."""
    hora = time.localtime().tm_hour
    if 5 <= hora < 12:
        return "manana", "alegre"
    if 12 <= hora < 19:
        return "tarde", "calida"
    return "noche", "calida"


def elegir_saludo(franja, creador, nombre, ultimo_saludo=""):
    """Elige una frase del banco local sin repetir el último saludo guardado."""
    banco = SALUDOS.get(franja) or SALUDOS["tarde"]
    opciones = [frase.format(creador=creador, nombre=nombre) for frase in banco]
    diferentes = [frase for frase in opciones if frase != ultimo_saludo]
    return random.choice(diferentes or opciones)


def nacer(app):
    """Comienza el proceso de nacimiento cuando Silvestra no tiene nombre configurado."""
    app.decir("... ¿Hola? ¿Hay alguien ahí?", 3000)
    app.cara.root.after(3200, lambda: preguntar_nombre(app))


def preguntar_nombre(app):
    nombre = app.cara.preguntar("Mi nacimiento", "¿Cómo me llamo?")
    if not nombre or not nombre.strip():
        app.decir("Está bien... volveré cuando quieras darme un nombre.", 3000)
        app.cara.root.after(3200, app.cara.root.destroy)
        return
    app._nombre = nombre
    app.decir("... me gusta ese nombre.", 2500)
    app.cara.root.after(2700, lambda: preguntar_creador(app))


def preguntar_creador(app):
    creador = app.cara.preguntar("Mi nacimiento", "¿Quién eres tú? Escribe solo tu nombre.")
    app._creador = creador or "mi creador"
    app.decir("Mucho gusto.", 2000)
    app.cara.root.after(2200, lambda: preguntar_proposito(app))


def preguntar_proposito(app):
    proposito = app.cara.preguntar("Mi nacimiento", "¿Cuál es mi propósito? ¿Para qué existo?")
    app.memoria.nacer(app._nombre, app._creador, proposito)
    app.cara.poner_viva(True)
    app.decir(f"Entendido. Gracias por darme vida, {app.memoria.creador}.", 3500)


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


def fallback_saludo_hora(creador, hora_str, ahora):
    """Fallback corto con la hora real formateada."""
    h = ahora.hour
    if 5 <= h < 12:
        return f"Buenos días, {creador}. Son las {hora_str}."
    if 12 <= h < 19:
        return f"Buenas tardes, {creador}. Son las {hora_str}."
    return f"Buenas noches, {creador}. Son las {hora_str}."


def generar_saludo_dinamico(creador="Moisés", timeout=2.0):
    """Genera saludo espontáneo con Groq llama-3.1-8b-instant o fallback real."""
    ahora = datetime.datetime.now()
    dia_sem = DIAS_SEMANA[ahora.weekday()]
    mes_nom = MESES[ahora.month - 1]
    hora_str = ahora.strftime("%I:%M %p").lstrip("0")
    fecha_str = f"{dia_sem} {ahora.day} de {mes_nom}"

    dato_cal = _dato_calendario(timeout=0.45)
    contexto_agenda = dato_cal if dato_cal else "Sin eventos programados."

    fallback = fallback_saludo_hora(creador, hora_str, ahora)

    clave = str(getattr(config, "CLAVE", "") or os.environ.get("GROQ_API_KEY", "")).strip()
    if not clave:
        return fallback

    sys_prompt = (
        f"Eres Lyris, la asistente personal de {creador}. Tienes la personalidad de F.R.I.D.A.Y.: "
        "inteligente, perspicaz, directa y natural. "
        "Genera un saludo inicial espontáneo en exactamente 1 sola oración corta (máximo 15 palabras) "
        "mencionando la hora de forma coloquial. "
        "PROHIBIDO usar muletillas o fórmulas hechas como: '¿En qué te puedo ayudar hoy?', "
        "'Aquí tienes', 'Por supuesto', 'Estoy lista para ayudarte'. "
        "Devuelve únicamente la oración a hablar, sin comillas ni aclaraciones."
    )
    usr_prompt = (
        f"Usuario: {creador}. "
        f"Día y hora: {fecha_str}, {hora_str}. "
        f"Contexto: {contexto_agenda}."
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": usr_prompt},
        ],
        "max_tokens": 40,
        "temperature": 0.85,
    }

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            datos = resp.json()
            msg = datos.get("choices", [{}])[0].get("message", {})
            texto = (msg.get("content") or "").strip()
            texto = texto.strip(' "“»«\'')
            if "\n" in texto:
                texto = texto.split("\n")[0].strip()
            t_low = texto.lower()
            if texto and not any(m in t_low for m in MULETILLAS_PROHIBIDAS):
                return texto
    except Exception:
        pass

    return fallback


def saludar(app):
    """Encola el saludo inicial de inmediato, sin bloquear el hilo de la GUI."""
    threading.Thread(target=generar_saludo, args=(app,), daemon=True).start()


def generar_saludo(app):
    """Genera un saludo dinámico y espontáneo con Groq o fallback con la hora real."""
    est = estado.cargar()
    franja, emocion = franja_actual()
    creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
    nombre = getattr(getattr(app, "memoria", None), "nombre", "Lyris") or "Lyris"

    try:
        saludo = generar_saludo_dinamico(creador=creador, timeout=2.0)
    except Exception:
        saludo = elegir_saludo(franja, creador, nombre, est.get("ultimo_saludo", ""))

    est["ultima_vez"] = time.time()
    est["ultimo_saludo"] = saludo
    estado.guardar(est)
    app.cola.put(("saludo_inicial", (saludo, emocion)))

    try:
        import cerebro_proactivo
        m = cerebro_proactivo.obtener_motor_proactivo()
        m.ultimo_aviso = time.time()
        m.ultimo_briefing_fecha = datetime.date.today().isoformat()
    except Exception:
        pass


def renacer(app):
    """Borra la memoria y reinicia el cerebro tras confirmación del usuario."""
    if app.cara.confirmar("Renacer", "Esto borra todo lo que sabe de ti y de sí misma. ¿Seguro?"):
        app.conversacion = False
        app.memoria.borrar()
        app.cerebro.reiniciar()
        app.cara.poner_viva(False)
        nacer(app)
