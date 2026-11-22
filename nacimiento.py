"""Ciclo de vida, nacimiento, saludo inicial y renacer de Silvestra."""
import threading
import time

from cerebro import ahora_texto
import estado
import hilos


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


def saludar(app):
    """Lanza la generación del saludo inicial contextual en un hilo secundario."""
    threading.Thread(target=generar_saludo, args=(app,), daemon=True).start()


def generar_saludo(app):
    """Genera un saludo dinámico y cálido con Groq según la hora, el tiempo pasado y pendientes."""
    est = estado.cargar()
    ultima_vez = est.get("ultima_vez")
    ultimo_saludo = est.get("ultimo_saludo", "")
    tiempo_txt = estado.tiempo_transcurrido_texto(ultima_vez)
    hora_actual = time.localtime().tm_hour
    if 5 <= hora_actual < 12:
        saludo_hora = "Buenos días"
        emocion_saludo = "alegre"
    elif 12 <= hora_actual < 19:
        saludo_hora = "Buenas tardes"
        emocion_saludo = "calida"
    else:
        saludo_hora = "Buenas noches"
        emocion_saludo = "calida"
    creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
    nombre = getattr(getattr(app, "memoria", None), "nombre", "Lyris") or "Lyris"
    frase_fija = f"{saludo_hora}, {creador}. Soy {nombre}. Lista para lo que necesites."
    try:
        sistema = (
            f"Eres {nombre}, asistente de {creador}.\n"
            f"Momento actual: {ahora_texto()}.\n"
            f"Tiempo transcurrido desde la última vez que hablaron: {tiempo_txt}.\n"
            f"Saludo anterior (OBLIGATORIO: NO repitas este saludo ni su estructura):\n{ultimo_saludo or 'Ninguno'}\n"
            f"Hilos y temas pendientes: {hilos.resumen()}.\n\n"
            "Genera un saludo inicial cálido, natural y cercano en español panameño (sin exagerar modismos).\n"
            "Reglas OBLIGATORIAS:\n"
            f"1. Saludo según la hora: Si mencionas la hora o franja, debe ser '{saludo_hora}' (NUNCA digas 'buenos días' si es tarde o noche).\n"
            "2. De 1 a 2 frases cortas (máximo 25 palabras), aptas para decir en voz alta.\n"
            "3. Solo menciona recordatorios si realmente hay alguno pendiente o recién vencido en tus notas.\n"
            "4. Sin asteriscos, sin listas, sin comillas, sin emojis.\n"
            "Responde ÚNICAMENTE con el saludo que dirás en voz alta."
        )
        saludo = app.cerebro._pedir([
            {"role": "system", "content": sistema},
            {"role": "user", "content": "Saluda a tu creador."},
        ])
        limpio = saludo.replace("*", "").replace("\n", " ").strip("\"' ")
        if not limpio:
            raise ValueError("Saludo vacío")
        est["ultima_vez"] = time.time()
        est["ultimo_saludo"] = limpio
        estado.guardar(est)
        app.cola.put(("saludo_inicial", (limpio, emocion_saludo)))
    except Exception:
        est["ultima_vez"] = time.time()
        est["ultimo_saludo"] = frase_fija
        estado.guardar(est)
        app.cola.put(("saludo_inicial", (frase_fija, emocion_saludo)))
    finally:
        try:
            import cerebro_proactivo
            m = cerebro_proactivo.obtener_motor_proactivo()
            m.ultimo_aviso = time.time()
            import datetime
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
