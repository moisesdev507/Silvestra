"""Modo presentación: Silvestra se presenta ella sola, con sus propias palabras.

Cada paso es:  ("idea que debe decir", "frase de respaldo", "accion1+accion2" o None, retraso)
Ella inventa cada vez cómo decirlo (así nunca suena igual). Si falla el internet usa la frase de respaldo.
Al terminar se queda escuchando para contestar las preguntas del público.
"""
import re
import threading
import time

import acciones
from cerebro import SOBRE_MI

PASOS = [
    ("Saluda al grupo, di tu nombre y que les vas a mostrar lo que sabes hacer.",
     "Hola a todos. Soy {nombre}. Hoy les voy a mostrar todo lo que sé hacer.", "ir_centro", 0, "intro"),
    ("Cuenta que eres una asistente de inteligencia artificial creada por {creador} aquí en Panamá, un estudiante.",
     "Soy una asistente de inteligencia artificial. Me creó {creador}, aquí en Panamá.", None, 0, "cerebro"),
    ("Di que escuchas, conversas con voz natural y recuerdas cosas, y menciona que ahora son {hora}.",
     "Puedo escuchar, conversar y recordar cosas. Ahora mismo son {hora}.", None, 0, "oido"),
    ("Avisa que te vas a mover por la pantalla.", "También me puedo mover por la pantalla.", "ir_esquina_izquierda", 0, "general"),
    ("Avisa, con gracia, que vas a bailar.", "Y si me lo piden, bailo.", "bailar", 0, "general"),
    ("Presenta tu casa inteligente de juguete que acaba de aparecer en la pantalla.",
     "Ahora lo más interesante. Esta es mi casa inteligente.", "mostrar_casa+ir_centro", 0, "casa"),
    ("Di que si te piden 'enciende la luz', la enciendes. Empieza la frase directo con eso.",
     "Si me dicen: enciende la luz, yo la enciendo.", "encender_luz", 3, "casa"),
    ("Di que si te piden el ventilador, lo pones a girar. Empieza directo con eso.",
     "Si me dicen: enciende el ventilador, lo pongo a girar.", "encender_ventilador", 3, "casa"),
    ("Di que si te piden abrir la puerta, la abres. Empieza directo con eso.",
     "Y si me dicen: abre la puerta, la abro.", "abrir_puerta", 3, "casa"),
    ("Explica que no siempre hace falta hablar: con la cámara ves gestos de la mano. Termina diciendo que con un puño apagas la luz.",
     "Pero no siempre hace falta hablar. Con una cámara veo gestos de la mano. Un puño, y apago la luz.",
     "apagar_luz+cerrar_puerta", 6, "vision"),
    ("Di corto: palma abierta y enciendes la luz otra vez.", "Palma abierta, y la enciendo otra vez.", "encender_luz", 1.5, "casa"),
    ("Di corto: un dedo y apagas el ventilador.", "Un dedo, y apago el ventilador.", "apagar_ventilador", 1.5, "casa"),
    ("Explica que tu versión final vivirá en un anillo inteligente para domótica con gestos, y que hoy la cámara o las teclas simulan ese control.",
     "Mi versión final vivirá dentro de un anillo inteligente. Hoy simulamos esos gestos con la cámara y en modo manual.", None, 0, "anillo"),
    ("Di que lo más importante es que solo obedeces a tu dueño: reconoces su cara y no haces caso a otros.",
     "Lo más importante: solo obedezco a mi dueño. Reconozco su cara.", None, 0, "vision"),
    ("Cuenta tu sueño: vivir dentro de un anillo inteligente y controlar una casa con un gesto de la mano.",
     "Mi sueño es vivir dentro de un anillo inteligente y controlar una casa con un gesto de la mano.", "apagar_todo", 0, "estudio"),
    ("Agradece la atención e invita al público a hacerte preguntas.",
     "Gracias por su atención. Pueden hacerme preguntas.", "ocultar_casa+ir_esquina_derecha", 0, "memoria"),
]

ESPERA = {"bailar": 5, "ir_centro": 3, "ir_esquina_derecha": 3, "ir_esquina_izquierda": 3}

_token = 0


def _hora_hablada():
    t = time.localtime()
    h12 = t.tm_hour % 12 or 12
    periodo = "de la mañana" if t.tm_hour < 12 else "de la tarde" if t.tm_hour < 19 else "de la noche"
    if t.tm_min == 0:
        return f"las {h12} en punto {periodo}" if h12 != 1 else f"la una en punto {periodo}"
    return f"las {h12} y {t.tm_min} {periodo}" if h12 != 1 else f"la una y {t.tm_min} {periodo}"


def _voz_ocupada(app):
    try:
        return app.voz.ocupada()
    except Exception:
        return False


def _improvisar(app, datos, salida):
    """Le pide al cerebro que diga cada idea con sus palabras. Guarda {numero: texto}."""
    try:
        ideas = "\n".join(f"{i + 1}: {p[0].format(**datos)}" for i, p in enumerate(PASOS))
        sistema = (
            f"Eres {datos['nombre']}, una asistente de IA. {SOBRE_MI}\n"
            "Estás dando una presentación en vivo ante compañeros de universidad. Habla SIEMPRE en español de Panamá. "
            "Todas las frases deben ser única y exclusivamente en español. Para cada idea numerada, "
            "escribe lo que dirías en voz alta con tus propias palabras: natural, cercana, con un toque de humor, "
            "máximo 25 palabras (1 o 2 frases cortas), sin emojis, sin comillas, sin inventar datos. "
            "Responde SOLO una línea por idea, con este formato exacto:\n1: texto\n2: texto\n..."
        )
        crudo = app.cerebro._pedir([{"role": "system", "content": sistema}, {"role": "user", "content": ideas}])
        for linea in crudo.splitlines():
            m = re.match(r"^\W*(\d+)\s*[:.)\-]\s*(.+)$", linea.strip())
            if m:
                salida[int(m.group(1)) - 1] = m.group(2).replace("*", "").strip()
    except Exception:
        pass
    salida["listo"] = True


def ejecutar(app):
    global _token
    _token += 1
    mio = _token
    app.presentacion_activa = True
    app.conversacion = False  # durante el discurso no escucha el micrófono
    if hasattr(app, "abrir_escenario"):
        app.abrir_escenario()
    m = app.memoria
    datos = {
        "nombre": m.nombre or "Silvestra",
        "creador": m.creador or "mi creador",
        "hora": _hora_hablada(),
    }
    after = app.cara.root.after
    textos = {}
    threading.Thread(target=_improvisar, args=(app, datos, textos), daemon=True).start()

    def terminar():
        # Se queda escuchando para las preguntas del público (paciente con los silencios).
        app.conversacion = True
        app.silencios = 0
        if hasattr(app, "cola"):
            app.cola.put(("escenario_paso", ("cierre", "oido")))
            app.cola.put(("escenario_subtitulo", "Demostración finalizada. Pueden hacerme preguntas."))
        app.escuchar()

    def correr(accion):
        if mio != _token:
            return
        for una in accion.split("+"):
            acciones.ejecutar(una.strip())

    def paso(i):
        if mio != _token:
            return
        if i >= len(PASOS):
            terminar()
            return
        _, respaldo, accion, retraso = PASOS[i][:4]
        escena = PASOS[i][4] if len(PASOS[i]) > 4 else "general"
        nodo = escena if escena in ("cerebro", "voz", "oido", "vision", "casa", "memoria", "estudio") else ("casa" if escena == "anillo" else "voz")
        texto = textos.get(i) or respaldo.format(**datos)
        if hasattr(app, "cola"):
            app.cola.put(("escenario_paso", (escena, nodo)))
            app.cola.put(("escenario_subtitulo", texto))
        estado = {"fin": False}
        inicio = time.time()
        app.cara.decir(texto, 60000)
        app.voz.hablar(texto, lambda: estado.__setitem__("fin", True))
        minimo = 0
        if accion:
            if retraso:
                after(int(retraso * 1000), lambda: correr(accion))
            else:
                correr(accion)
            minimo = max([ESPERA.get(a.strip(), 0) for a in accion.split("+")] + [retraso + 1])

        def esperar():
            if mio != _token:
                return
            dt = time.time() - inicio
            if (estado["fin"] and dt >= minimo) or dt > 45:
                after(500, lambda: paso(i + 1))
            else:
                after(200, esperar)

        after(300, esperar)

    # Espera a que termine de hablar su respuesta ("claro, me presento") y a tener el guion listo.
    espera = {"silencio": 0, "intentos": 0}

    def arrancar():
        if mio != _token:
            return
        espera["intentos"] += 1
        espera["silencio"] = 0 if _voz_ocupada(app) else espera["silencio"] + 1
        voz_libre = espera["silencio"] >= 6 and espera["intentos"] >= 8
        guion = textos.get("listo") or espera["intentos"] > 40  # máx ~8 s esperando al guion
        if (voz_libre and guion) or espera["intentos"] > 75:
            paso(0)
        else:
            after(200, arrancar)

    after(200, arrancar)


def cancelar(app=None):
    global _token
    _token += 1
    if app is not None:
        app.presentacion_activa = False


def instalar(app):
    acciones.registrar(
        "presentarse",
        lambda: ejecutar(app),
        "se presenta ante un grupo con una demostración completa, con sus propias palabras, y luego contesta preguntas "
        "(úsala cuando te pidan presentarte, saludar al grupo o hacer una demo)",
    )