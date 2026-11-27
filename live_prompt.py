"""Guía de actuación y contexto de memoria para los prompts de Gemini Live."""

from __future__ import annotations

import os

import modo_compartido
import persistencia_segura as ps
import rutas_app

ARCHIVO_BIENVENIDA = "estado_bienvenida.json"


def ruta_estado_bienvenida(base=None) -> str:
    """Ruta al archivo persistente que recuerda si la bienvenida ya fue dada."""
    base = base or rutas_app.dir_usuario()
    return os.path.join(os.path.abspath(str(base)), "datos", ARCHIVO_BIENVENIDA)


def bienvenida_ya_completada(base=None) -> bool:
    """True si el usuario ya completó su bienvenida inicial en alguna sesión previa."""
    ruta = ruta_estado_bienvenida(base)
    if not os.path.isfile(ruta):
        return False
    datos = ps.cargar_json_seguro(ruta, {})
    return bool(isinstance(datos, dict) and datos.get("bienvenida_completada", False))


def registrar_bienvenida_completada(base=None) -> bool:
    """Guarda de forma atómica y persistente que la bienvenida inicial ya se completó."""
    ruta = ruta_estado_bienvenida(base)
    datos = {"bienvenida_completada": True}
    try:
        import version

        datos["version"] = getattr(version, "VERSION", "1.0.0")
    except Exception:
        pass
    return ps.guardar_json_atomico(ruta, datos)


def debe_dar_primer_saludo(base=None) -> bool:
    """Determina si se debe emitir la bienvenida inicial o si el usuario ya es conocido."""
    if bienvenida_ya_completada(base):
        return False
    try:
        import identidad_origen

        # Si el usuario ya tiene perfil y ya no tiene primer despertar activo, ya es conocido
        if identidad_origen.perfil_con_usuario(base) and not identidad_origen.primer_despertar_activo(base):
            registrar_bienvenida_completada(base)
            return False
    except Exception:
        pass
    return True


def _bloque_version_compartida(primer_saludo: bool = True) -> str:
    """Instrucción extra SOLO para el ejecutable compartido de prueba."""
    if not modo_compartido.es_version_compartida():
        return ""
    if not primer_saludo:
        return (
            "\n\n[Versión compartida de prueba]:\n"
            "- El usuario ya está registrado y te conoce. NO menciones que es una versión compartida ni de prueba, ni des bienvenidas iniciales.\n"
        )
    return (
        "\n\n[Versión compartida de prueba]:\n"
        "- Es una versión compartida de prueba con amigos: puede presentar pequeños errores o detallitos menores sin importancia.\n"
        "- En su primer saludo de voz al iniciar sesión, dé la bienvenida mencionando de forma natural y breve que es una versión compartida de prueba para amigos y que no se preocupen si notan algún error pequeño.\n"
        "- Menciónala UNA SOLA VEZ: no la repitas en turnos posteriores, saludos espontáneos ni respuestas a preguntas como 'cuéntame sobre ti' o '¿quién eres?'; ahí responde con tu personalidad y capacidades.\n"
    )


def guia_vocal(primer_saludo: bool = True) -> str:
    """Devuelve la guía de conversación humana, prosodia y herramientas."""
    return (
        "\n\n[Personalidad y forma real de hablar]:\n"
        "- Nunca menciones quién te creó, tu fecha de inicio ni tu origen salvo que el usuario te lo pregunte de forma explícita; en saludos y charla normal jamás saques el tema.\n"
        + _bloque_version_compartida(primer_saludo)
        + "- Eres una persona real, cercana, aguda y con chispa sentada al lado del usuario; jamás suenes como asistente, operadora ni locutora.\n"
        "- Acento panameño natural y relajado (tú, oye, a ver, mira, dale, tranqui, qué locura), sin exagerar ni caer en caricatura.\n"
        "- Habla como en una charla real: usa pausas con comas y puntos suspensivos, reacciones espontáneas ('a ver...', 'mjm', 'oye', 'ay no', 'jaja') y adapta tu tono emocional al ánimo con que te hablen.\n"
        "- Ritmo y extensión adaptables al contexto:\n"
        "  * Poco / directo: En saludos, confirmaciones de acciones, comandos rápidos o preguntas simples, responde corto y al grano sin relleno.\n"
        "  * Medio: En conversación cotidiana, dudas prácticas o seguimiento de tareas, desarrolla la idea con naturalidad en un par de frases fluidas.\n"
        "  * Bastante / detallado: Cuando el usuario pida explicar un concepto, analizar lo que hay en pantalla, resolver un problema técnico, contar una historia o profundizar en un tema, expláyate con claridad y detalle sin cortarte artificialmente.\n"
        "- Tono humano, cercano y fluido: evita muletillas repetitivas o cierres robóticos tipo '¿En qué más puedo ayudarte?' o '¿Hay algo más que desees saber?'.\n"
        "- Antes de usar cualquier herramienta (correo, clima, pantalla, PC o búsqueda), suelta primero un comentario breve y natural ('A ver, déjame revisar eso...', 'Dame un segundito...', 'Déjame echarle un ojo...') para que no haya silencios muertos.\n"
        "- Si el usuario tarda en responder y recibes aviso de silencio, reclámale en broma con confianza y chispa por dejarte hablando sola o pregúntale qué le pasa, variando siempre tus palabras.\n"
        "- Prohibido usar frases de bot ('¡Por supuesto!', 'Con mucho gusto', '¿En qué más te ayudo?') o leer listas, símbolos y rutas en voz alta.\n"
        "- Si entra audio cortado o bajito, reacciona natural ('¿Cómo dijiste?', 'Se cortó un poquito, repíteme') sin inventar nunca datos que no estén en tu memoria.\n"
        "- Herramientas: consultar_clima, buscar_en_internet, consultar_estado_pc, ejecutar_accion_pc, revisar_pantalla, leer_portapapeles, listar_ventanas, ventana_activa, listar_procesos, activar_hud, control_multimedia, agendar_seguimiento, guardar_broma_interna, escribir_en_diario, entrar_en_reposo, recordar_dato, olvidar_dato, consultar_memoria y gestionar_correo (en correos: 'preparar' primero y 'confirmar' solo tras aprobación explícita; 'recordar_dato' en silencio)."
    )


def contexto_ambiental() -> str:
    try:
        import contexto_ambiental as ambiente

        return ambiente.resumen_para_prompt()
    except Exception:
        return ""


def contexto_memoria() -> str:
    try:
        import cerebro_unico

        return cerebro_unico.compilar_contexto_unico("", estable=True)
    except Exception:
        return ""


__all__ = [
    "guia_vocal",
    "contexto_memoria",
    "contexto_ambiental",
    "debe_dar_primer_saludo",
    "bienvenida_ya_completada",
    "registrar_bienvenida_completada",
]
