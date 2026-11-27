"""Generación de habla espontánea para Kaya: saludos vivos y micro-reacciones sin clichés."""
import datetime
import random
import threading
import time

import identidad_origen
import modo_compartido
import saludo_dinamico

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _usuario_actual(app, respaldo=None):
    """El perfil manda: un amigo es usuario, nunca se le llama creador."""
    perfil = identidad_origen.nombre_usuario()
    if perfil:
        return perfil
    return str(respaldo or identidad_origen.USUARIO_SIN_NOMBRE)


def _live_toma_turno(app) -> bool:
    """Evita que el motor clásico hable en paralelo con Gemini Live."""
    cl = getattr(app, "coordinador_live", None) if app else None
    if cl is None:
        return False
    for nombre in ("esta_live_activo", "es_modo_principal"):
        try:
            if getattr(cl, nombre)() is True:
                return True
        except Exception:
            pass
    return False


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
        import iniciativa_kaya
        resumen = iniciativa_kaya.resumen_compacto_temas()
        if resumen:
            return resumen
    except Exception:
        pass
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
    if _live_toma_turno(app):
        return
    def _tarea():
        franja, emocion, saludo_base = _franja_y_emocion()
        usuario = _usuario_actual(app)
        tema = _tema_reciente(app)

        frase = None
        cerebro = getattr(app, "cerebro", None)
        if cerebro and hasattr(cerebro, "_pedir"):
            try:
                dia_str = DIAS[datetime.datetime.now().astimezone().weekday()]
                prompt_sistema = (
                    identidad_origen.bloque_identidad(usuario) + "\n"
                    + f"Eres Kaya, la compañera y amiga personal de {usuario} en Panamá. "
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
            frase = fallback_saludo_offline(usuario)
        if modo_compartido.es_version_compartida():
            frase = saludo_dinamico.con_nota_version(frase)

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


def humanizar_resultado_accion(orden, resultado_crudo, app=None):
    """Pasa un dato crudo de hardware o acción local por el cerebro para darle voz natural de Kaya.
    
    Preserva estrictamente todas las cifras y métricas reales sin inventar ni usar clichés robóticos.
    """
    crudo = str(resultado_crudo or "").strip()
    if not crudo:
        return ""

    cerebro = getattr(app, "cerebro", None) if app else None
    if cerebro and hasattr(cerebro, "_pedir"):
        try:
            prompt_sistema = (
                identidad_origen.bloque_identidad(_usuario_actual(app)) + "\n"
                + f"Eres Kaya, la compañera personal de {_usuario_actual(app)} en Panamá. "
                "Comunica el siguiente resultado real del computador en exactamente 1 o 2 frases cortas habladas, "
                "con tono natural, fresco y cercano. "
                "REGLA CRÍTICA: Mantén con total precisión los números, porcentajes y cifras reales proporcionadas; "
                "PROHIBIDO inventar métricas, alterar números o agregar saludos/despedidas robóticas."
            )
            mensajes = [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Orden: '{orden}'. Datos reales: {crudo}"}
            ]
            resp = cerebro._pedir(mensajes, tarea="charla")
            if resp and isinstance(resp, str):
                limpio = resp.strip().strip('"').strip("'")
                if len(limpio) >= 12 and any(c.isdigit() for c in limpio if any(d.isdigit() for d in crudo)):
                    return limpio
        except Exception:
            pass

    # Fallback conversacional limpio que preserva intactos los datos
    prefijos = [
        "Mira, te cuento: ",
        "Por aquí veo que ",
        "El equipo anda así: ",
        "Revisando por acá: "
    ]
    return random.choice(prefijos) + crudo
