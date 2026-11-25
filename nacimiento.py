"""Ciclo de vida, nacimiento, saludo inicial y renacer de Silvestra."""
import datetime
import random
import threading
import time

import estado
import identidad_origen
from saludo_dinamico import (
    _guardar_ultimo_saludo,
    _log_saludo,
    _obtener_ultimos_saludos,
    fallback_natural_memoria,
    generar_saludo_dinamico,
)

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


def saludar(app):
    """Encola el saludo inicial de inmediato, sin bloquear el hilo de la GUI."""
    cl = getattr(app, "coordinador_live", None)
    if cl:
        for metodo in ("esta_live_activo", "es_modo_principal"):
            try:
                if getattr(cl, metodo)() is True:
                    return  # Gemini Live ya tiene el turno: el clásico no habla.
            except Exception:
                pass
    if identidad_origen.consumir_primer_despertar():
        saludo = identidad_origen.saludo_primer_despertar()
        _guardar_ultimo_saludo(saludo)
        if hasattr(app, "cola"):
            app.cola.put(("saludo_inicial", (saludo, "alegre")))
        elif hasattr(app, "decir"):
            app.decir(saludo, 4000)
        return
    try:
        import habla_espontanea
        habla_espontanea.generar_saludo_espontaneo(app)
    except Exception:
        threading.Thread(target=generar_saludo, args=(app,), daemon=True).start()


def generar_saludo(app_o_creador=None, creador=None):
    """Genera un saludo dinámico y espontáneo con memoria real o fallback variado."""
    franja, emocion = franja_actual()
    app = app_o_creador if hasattr(app_o_creador, "cola") else None
    if creador is None:
        if isinstance(app_o_creador, str):
            creador = app_o_creador
        else:
            creador = identidad_origen.nombre_usuario() or identidad_origen.USUARIO_SIN_NOMBRE

    try:
        saludo = generar_saludo_dinamico(creador=creador, timeout=3.0)
    except Exception as e:
        _log_saludo(f"origen=fallback excepcion='{e}'")
        saludo = fallback_natural_memoria(creador, {}, _obtener_ultimos_saludos())
        _guardar_ultimo_saludo(saludo)

    if app is not None and hasattr(app, "cola"):
        app.cola.put(("saludo_inicial", (saludo, emocion)))

    try:
        import cerebro_proactivo
        m = cerebro_proactivo.obtener_motor_proactivo()
        m.ultimo_aviso = time.time()
        m.ultimo_briefing_fecha = datetime.date.today().isoformat()
    except Exception:
        pass

    return saludo


def renacer(app):
    """Borra la memoria y reinicia el cerebro tras confirmación del usuario."""
    if app.cara.confirmar("Renacer", "Esto borra todo lo que sabe de ti y de sí misma. ¿Seguro?"):
        app.conversacion = False
        app.memoria.borrar()
        app.cerebro.reiniciar()
        app.cara.poner_viva(False)
        nacer(app)
