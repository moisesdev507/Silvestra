"""Declaraciones de herramientas extra de Gemini Live (texto intacto)."""
from typing import List
from google.genai import types


def declaraciones_extra() -> List[types.FunctionDeclaration]:
    """Declaraciones de las capacidades locales añadidas a Gemini Live."""
    import herramientas_cerebro
    return [
        types.FunctionDeclaration(
            name="revisar_pantalla",
            description=(
                "Mira la pantalla del usuario en tiempo real y responde qué ventana está abierta, "
                "qué texto o error se ve y qué parece estar haciendo. Úsala cuando pidan mirar, "
                "revisar, describir o explicar la pantalla."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "pregunta": types.Schema(
                        type="STRING",
                        description="Qué debe revisar o responder sobre la pantalla (ej. 'lee el error', 'qué ventana está abierta').",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="leer_portapapeles",
            description="Lee el texto que el usuario tiene copiado en el portapapeles para analizarlo, resumirlo o explicarlo.",
            parameters=types.Schema(type="OBJECT", properties={}),
        ),
        types.FunctionDeclaration(
            name="listar_ventanas",
            description="Lista las ventanas visibles abiertas en Windows con su título y cuál está activa.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "limite": types.Schema(type="INTEGER", description="Máximo de ventanas a listar (por defecto 12)."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="ventana_activa",
            description="Indica el título de la ventana que el usuario tiene en primer plano.",
            parameters=types.Schema(type="OBJECT", properties={}),
        ),
        types.FunctionDeclaration(
            name="listar_procesos",
            description="Lista los procesos o programas que están corriendo en la PC, opcionalmente filtrados por nombre.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "nombre": types.Schema(type="STRING", description="Filtro opcional por nombre del proceso."),
                    "limite": types.Schema(type="INTEGER", description="Máximo de procesos a listar (por defecto 12)."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="activar_hud",
            description="Activa el HUD remoto en la tablet del usuario y devuelve la dirección de acceso.",
            parameters=types.Schema(type="OBJECT", properties={}),
        ),
        types.FunctionDeclaration(
            name="control_multimedia",
            description="Pausa, reanuda, adelanta o retrocede la música o el video que esté reproduciéndose.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "orden": types.Schema(type="STRING", description="Orden de reproducción (ej. 'pausa', 'siguiente canción', 'anterior')."),
                },
                required=["orden"],
            ),
        ),
        types.FunctionDeclaration(
            name="recordar_dato",
            description=(
                "Guarda en la memoria permanente de Kaya un dato importante que el usuario "
                "dijo sobre su vida, familia, gustos, trabajo, estudios o proyectos. "
                "Úsala cuando pidan 'recuerda esto' o cuando cuenten algo duradero."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "hecho": types.Schema(
                        type="STRING",
                        description="Hecho concreto y explícito a recordar (una sola frase).",
                    ),
                },
                required=["hecho"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_memoria",
            description=(
                "Consulta la memoria permanente compartida y responde con honestidad qué recuerda "
                "Kaya sobre el usuario o sobre un tema concreto."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "tema": types.Schema(
                        type="STRING",
                        description="Tema a consultar; deja vacío o usa 'mí' para lo que sabe del usuario.",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="olvidar_dato",
            description="Borra de la memoria permanente los recuerdos relacionados con un tema que el usuario pida olvidar.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "tema": types.Schema(
                        type="STRING",
                        description="Tema o dato concreto que debe olvidarse.",
                    ),
                },
                required=["tema"],
            ),
        ),
        types.FunctionDeclaration(
            name="guardar_broma_interna",
            description=(
                "Guarda en la memoria compartida una broma recurrente, un apodo entre Kaya y "
                "el usuario o un código propio que ya se volvió costumbre. Úsala cuando "
                "inventen o repitan un chiste interno."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "broma": types.Schema(
                        type="STRING",
                        description="Broma, apodo o código propio en una frase breve.",
                    ),
                    "contexto": types.Schema(
                        type="STRING",
                        description="Situación en la que surge o se usa la broma (opcional).",
                    ),
                },
                required=["broma"],
            ),
        ),
        types.FunctionDeclaration(
            name="agendar_seguimiento",
            description=(
                "Agenda un seguimiento amable sobre un tema real que el usuario mencionó, "
                "para retomarlo más adelante con naturalidad (no para recordar datos inventados)."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "tema": types.Schema(
                        type="STRING",
                        description="Tema concreto y real que conviene retomar después.",
                    ),
                    "contexto": types.Schema(
                        type="STRING",
                        description="Contexto breve en que surgió el tema (opcional).",
                    ),
                    "horas_espera": types.Schema(
                        type="NUMBER",
                        description="Horas a esperar antes de retomarlo (por defecto 24).",
                    ),
                },
                required=["tema"],
            ),
        ),
        types.FunctionDeclaration(
            name="gestionar_correo",
            description=(
                "Gestiona Gmail: 'leer' revisa correos recientes; 'preparar' crea borrador SIN enviar; "
                "'confirmar' envía tras aprobación explícita; 'cancelar' descarta."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "accion": types.Schema(type="STRING", description="leer, preparar, confirmar o cancelar"),
                    "destinatario": types.Schema(type="STRING", description="Correo del destinatario (preparar)."),
                    "asunto": types.Schema(type="STRING", description="Asunto del correo (preparar)."),
                    "cuerpo": types.Schema(type="STRING", description="Mensaje del correo (preparar)."),
                },
                required=["accion"],
            ),
        ),
        types.FunctionDeclaration(
            name="escribir_en_diario",
            description=(
                "Escribe una entrada breve en el diario íntimo de Kaya, en primera persona y con su propia voz. "
                "El tema es solo inspiración: nunca copies ni guardes el texto literal del usuario."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "tema": types.Schema(
                        type="STRING",
                        description="Tema, vivencia o conversación sobre la que Kaya debe reflexionar en su diario.",
                    ),
                },
                required=["tema"],
            ),
        ),
    ] + herramientas_cerebro.declaraciones()


__all__ = ["declaraciones_extra"]
