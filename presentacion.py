"""Modo presentación: Silvestra se presenta ella sola, con sus propias palabras.

Cada paso es:  ("idea que debe decir", "frase de respaldo", "accion1+accion2" o None, retraso)
Ella inventa cada vez cómo decirlo (así nunca suena igual). Si falla el internet usa la frase de respaldo.
Al terminar se queda escuchando para contestar las preguntas del público.
"""
import os
import re
import threading
import time
import unicodedata

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

EMOCIONES_PASO = {
    0: "animada",  # Saludo inicial y bienvenida
    1: "animada",  # Presentación de su origen
    2: "seria",    # Explicación de capacidades y hora
    3: "animada",  # Demostración de movimiento en pantalla
    4: "animada",  # Baile con gracia
    5: "animada",  # Presentación de la casa inteligente
    6: "seria",    # Demostración comando luz
    7: "seria",    # Demostración comando ventilador
    8: "seria",    # Demostración comando puerta
    9: "seria",    # Explicación técnica de cámara y gestos
    10: "seria",   # Gesto palma
    11: "seria",   # Gesto un dedo
    12: "seria",   # Explicación técnica del anillo inteligente y domótica
    13: "seria",   # Seguridad biométrica y reconocimiento del dueño
    14: "animada", # Sueño a futuro
    15: "animada", # Despedida y preguntas del público
}

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
        emocion_paso = EMOCIONES_PASO.get(i, "animada" if i in (0, 1, 3, 4, 5, 14, 15) else "seria")
        app.cara.decir(texto, 60000)
        app.voz.hablar(texto, lambda: estado.__setitem__("fin", True), emocion=emocion_paso)
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


def detectar_orden_presentacion(texto):
    """Detecta si el usuario pide a Lyris presentarse o describir sus capacidades."""
    if not texto:
        return False
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    limpio = "".join(c for c in t if unicodedata.category(c) != "Mn")
    patrones = [
        r"\b(?:presentate|presentese|quien\s+eres|quien\s+sos)\b",
        r"\bque\s+(?:puedes|sabes)\s+hacer\b",
        r"\b(?:hablame|cuentame)\s+(?:un\s+poco\s+)?de\s+ti\b",
        r"\bpresentate\s+ante\b",
    ]
    return any(re.search(p, limpio) for p in patrones)


def recopilar_metricas_en_vivo(app=None):
    """Obtiene métricas reales del sistema sin exponer datos privados."""
    nombre = "Lyris"
    creador = "Moisés"
    if app and hasattr(app, "memoria"):
        m = app.memoria
        nombre = getattr(m, "nombre", None) or nombre
        creador = getattr(m, "creador", None) or creador

    total_habilidades = 0
    try:
        import json
        reg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "habilidades_aprendidas", "registro.json")
        if os.path.exists(reg_path):
            with open(reg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                total_habilidades = len([h for h in data.get("habilidades", {}).values() if h.get("aprobada", True)])
    except Exception:
        pass

    total_relaciones = 0
    try:
        import cerebro_grafo
        relaciones = cerebro_grafo.consultar_relaciones(creador)
        total_relaciones = len(relaciones)
    except Exception:
        pass

    return {
        "nombre": nombre,
        "creador": creador,
        "habilidades": total_habilidades,
        "grafo_relaciones": total_relaciones,
    }


def generar_presentacion_dinamica(app=None):
    """Genera una presentación elocuente y actualizada de Lyris retornando (texto, emocion)."""
    info = recopilar_metricas_en_vivo(app)
    nom = info["nombre"]
    creador = info["creador"]
    nhab = info["habilidades"]

    texto_llm = None
    if app and hasattr(app, "cerebro") and hasattr(app.cerebro, "_pedir"):
        try:
            prompt = (
                f"Eres {nom}, asistente modular de IA desarrollada por {creador}. "
                f"Cuentas con {nhab} habilidades aprendidas, visión de pantalla, RAG local y HUD LAN para tablet. "
                "Preséntate de forma profesional, dinámica y elocuente en 2 oraciones concisas (máximo 40 palabras). "
                "Sin emojis ni viñetas, en tono seguro y orgulloso."
            )
            res = app.cerebro._pedir([
                {"role": "system", "content": "Eres una IA asistente profesional y concisa."},
                {"role": "user", "content": prompt}
            ])
            if res and len(res.strip()) > 20:
                texto_llm = res.strip().replace('"', '')
        except Exception:
            texto_llm = None

    if texto_llm:
        return (texto_llm, "orgullosa")

    hab_txt = f", {nhab} habilidades prácticas aprendidas" if nhab > 0 else ""
    fallback = (
        f"Hola, soy {nom}, la asistente de inteligencia artificial personal desarrollada por {creador}. "
        f"Cuento con visión de pantalla en vivo, memoria relacional continua{hab_txt} "
        "y un entorno multimodal conectado a tu tablet para colaborar contigo en cada proyecto."
    )
    return (fallback, "orgullosa")
