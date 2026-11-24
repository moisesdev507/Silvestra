"""Generación de habla espontánea para Kaya: saludos vivos y micro-reacciones sin clichés."""
import datetime
import random
import threading
import time

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _franja_y_emocion():
    hora = datetime.datetime.now().astimezone().hour
    if 5 <= hora < 12:
        return "mañana", "alegre", "buenos días"
    elif 12 <= hora < 19:
        return "tarde", "calida", "buenas tardes"
    else:
        return "noche", "tranquila", "buenas noches"


def _tema_reciente(app):
    try:
        mem = getattr(app, "memoria", None)
        if mem and hasattr(mem, "listar_recuerdos"):
            recuerdos = mem.listar_recuerdos(limite=3)
            if recuerdos:
                return recuerdos[0].get("valor", "")[:45]
    except Exception:
        pass
    return ""


def generar_saludo_espontaneo(app, al_generar=None):
    """Genera una frase de saludo viva y personalizada usando el carril rápido del cerebro."""
    def _tarea():
        franja, emocion, saludo_base = _franja_y_emocion()
        creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
        tema = _tema_reciente(app)

        frase = None
        cerebro = getattr(app, "cerebro", None)
        if cerebro and hasattr(cerebro, "_pedir"):
            try:
                dia_str = DIAS[datetime.datetime.now().astimezone().weekday()]
                prompt_sistema = (
                    f"Eres Kaya, la compañera y amiga personal de {creador} en Panamá. "
                    "Hablas con calidez, cercanía, personalidad propia y chispa panameña natural. "
                    "Genera exactamente 1 sola frase corta y espontánea para saludarlo al encender tu sistema. "
                    "PROHIBIDO usar clichés de chatbot o mayordomo ('sistemas en línea', 'lista para servirte', 'en qué te ayudo', 'cómo puedo asistirte'). "
                    f"Contexto: es {dia_str}, {saludo_base}." + (f" Tema reciente: {tema}." if tema else "")
                )
                mensajes = [
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": "Salúdame de forma natural al iniciar el día o la tarde."}
                ]
                resp = cerebro._pedir(mensajes, tarea="charla")
                if resp and isinstance(resp, str):
                    limpio = resp.strip().strip('"').strip("'")
                    if limpio and len(limpio) >= 10:
                        frase = limpio
            except Exception:
                frase = None

        if not frase:
            frase = fallback_saludo_offline(creador)

        if callable(al_generar):
            al_generar(frase, emocion)
        elif app and hasattr(app, "cola"):
            app.cola.put(("saludo_inicial", (frase, emocion)))

    threading.Thread(target=_tarea, daemon=True).start()


def fallback_saludo_offline(creador="Moisés"):
    """Frases offline cercanas y cálidas sin frases robóticas ni clichés."""
    franja, _, saludo_base = _franja_y_emocion()
    opciones = [
        f"Hola {creador}, {saludo_base}. ¿Todo listo por acá?",
        f"Qué xopa {creador}, {saludo_base}. ¿En qué andamos hoy?",
        f"Hola {creador}, qué bueno verte por aquí. Lista cuando me digas.",
        f"{saludo_base.capitalize()}, {creador}. Qué gusto tenerte por aquí.",
        f"Buenas {creador}. Ya ando por aquí atenta a lo que necesites."
    ]
    return random.choice(opciones)


def micro_reaccion(tipo="pausa"):
    """Micro-reacciones humanas ante eventos internos (pausa, silencio, reanudación)."""
    if tipo == "pausa":
        return random.choice(["Te escucho, dime.", "Dime, te presto atención.", "Aquí estoy, cuéntame."])
    elif tipo == "silencio":
        return random.choice(["Listo, me callo.", "Me quedo calladita.", "Entendido, silencio."])
    elif tipo == "reanudar":
        return random.choice(["Aquí sigo.", "De vuelta.", "Te escucho."])
    return "Listo."
