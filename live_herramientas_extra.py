"""Herramientas adicionales de Gemini Live con paridad respecto al motor clásico.

Incluye visión de pantalla, portapapeles, ventanas, procesos, HUD y multimedia.
Se importa desde live_herramientas.py para no acercar ese módulo al límite de 15 KB.
"""
import asyncio
from typing import Any, Dict, List

from google.genai import types

import capacidades_extra as cap


def declaraciones_extra() -> List[types.FunctionDeclaration]:
    """Declaraciones de las capacidades locales añadidas a Gemini Live."""
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
    ]


async def despachar(nombre: str, args: Dict[str, Any]) -> Any:
    """Ejecuta una herramienta extra en un hilo para no bloquear el audio de Live."""
    loop = asyncio.get_running_loop()
    args = args or {}
    if nombre == "revisar_pantalla":
        return await loop.run_in_executor(
            None, cap.revisar_pantalla, str(args.get("pregunta", ""))
        )
    if nombre == "leer_portapapeles":
        return await loop.run_in_executor(None, cap.leer_portapapeles)
    if nombre == "listar_ventanas":
        return await loop.run_in_executor(None, cap.listar_ventanas, args.get("limite", 12))
    if nombre == "ventana_activa":
        return await loop.run_in_executor(None, cap.ventana_activa)
    if nombre == "listar_procesos":
        return await loop.run_in_executor(
            None, cap.listar_procesos, str(args.get("nombre", "")), args.get("limite", 12)
        )
    if nombre == "activar_hud":
        return await loop.run_in_executor(None, cap.activar_hud)
    if nombre == "control_multimedia":
        return await loop.run_in_executor(
            None, cap.control_multimedia, str(args.get("orden", ""))
        )
    if nombre == "escribir_en_diario":
        import diario_intimo
        tema = str(args.get("tema", ""))
        return await loop.run_in_executor(
            None, lambda: diario_intimo.escribir(tema, app=None)
        )
    if nombre == "recordar_dato":
        return await loop.run_in_executor(None, recordar_dato, str(args.get("hecho", "")))
    if nombre == "consultar_memoria":
        return await loop.run_in_executor(None, consultar_memoria, str(args.get("tema", "")))
    if nombre == "olvidar_dato":
        return await loop.run_in_executor(None, olvidar_dato, str(args.get("tema", "")))
    return None


def _memoria_principal():
    """Instancia real compartida con la voz clásica; nunca crea una copia."""
    try:
        import memoria
        return memoria.instancia_principal()
    except Exception:
        return None


def recordar_dato(hecho):
    """Guarda un hecho explícito en la memoria compartida."""
    mem = _memoria_principal()
    if mem is None:
        return "Todavía no tengo la memoria lista."
    dato = str(hecho or "").strip()
    if not dato:
        return "No me dijiste qué dato quieres que recuerde."
    ok = mem.recordar(dato, origen="explicito", texto_usuario=f"Recuerda que {dato}",
                      fuente="orden_explicita")
    return f"Listo, guardé en memoria: {dato}" if ok else "No pude guardar ese dato de forma segura."


def consultar_memoria(tema):
    """Responde qué recuerda la instancia principal de Memoria."""
    mem = _memoria_principal()
    if mem is None:
        return "Todavía no tengo la memoria lista."
    return mem.consultar(str(tema or "").strip() or None)


def olvidar_dato(tema):
    """Borra recuerdos del tema indicado de la memoria compartida."""
    mem = _memoria_principal()
    if mem is None:
        return "Todavía no tengo la memoria lista."
    dato = str(tema or "").strip()
    if not dato:
        return "No me dijiste qué dato quieres que olvide."
    return mem.olvidar(dato)


def ejecutar_por_texto(texto: str) -> Any:
    """Atajo para órdenes en lenguaje natural dentro de ejecutar_accion_local."""
    try:
        return cap.detectar_y_ejecutar(texto)
    except Exception:
        return None


__all__ = [
    "declaraciones_extra", "despachar", "ejecutar_por_texto",
    "recordar_dato", "consultar_memoria", "olvidar_dato",
]
