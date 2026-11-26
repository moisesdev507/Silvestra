"""Herramientas adicionales de Gemini Live con paridad respecto al motor clásico.

Incluye visión de pantalla, portapapeles, ventanas, procesos, HUD y multimedia.
Se importa desde live_herramientas.py.
"""
import asyncio
from typing import Any, Dict

import capacidades_extra as cap
from live_herramientas_declaraciones import declaraciones_extra

ETIQUETA_BROMA = "[BROMA_INTERNA]"


async def despachar(nombre: str, args: Dict[str, Any]) -> Any:
    """Ejecuta una herramienta extra en un hilo para no bloquear el audio de Live."""
    loop = asyncio.get_running_loop()
    args = args or {}
    if nombre == "revisar_pantalla":
        return await loop.run_in_executor(
            None, cap.revisar_pantalla, str(args.get("pregunta", ""))
        )
    if nombre == "leer_portapapeles":
        return await loop.run_in_executor(None, cap.leer_portapapeles_en_vivo)
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
    if nombre == "gestionar_correo":
        import correo_unificado as cu
        return await loop.run_in_executor(
            None, cu.gestionar, str(args.get("accion", "")),
            str(args.get("destinatario", "")), str(args.get("asunto", "")),
            str(args.get("cuerpo", "")),
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
    if nombre == "guardar_broma_interna":
        return await loop.run_in_executor(
            None, guardar_broma_interna,
            str(args.get("broma", "")), str(args.get("contexto", "")),
        )
    if nombre == "agendar_seguimiento":
        return await loop.run_in_executor(
            None, agendar_seguimiento, str(args.get("tema", "")),
            str(args.get("contexto", "")), args.get("horas_espera", 24),
        )
    import herramientas_cerebro
    resultado = herramientas_cerebro.despachar(nombre, args)
    return resultado if resultado is not None else None


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
    try:
        import memoria_unificada
        ok = memoria_unificada.recordar(
            dato, texto_usuario=f"Recuerda que {dato}", canal="voz",
            fuente="orden_explicita")
    except Exception:
        ok = False
    return f"Listo, guardé en memoria: {dato}" if ok else "No pude guardar ese dato de forma segura."


def consultar_memoria(tema):
    """Busca en SQLite, JSON legado y Supabase con un solo usuario_id."""
    if _memoria_principal() is None:
        return "Todavía no tengo la memoria lista."
    try:
        import memoria_unificada
        return memoria_unificada.consultar(str(tema or "").strip() or None)
    except Exception:
        return "No pude consultar la memoria compartida en este momento."


def olvidar_dato(tema):
    """Borra recuerdos del tema indicado de la memoria compartida."""
    mem = _memoria_principal()
    if mem is None:
        return "Todavía no tengo la memoria lista."
    dato = str(tema or "").strip()
    if not dato:
        return "No me dijiste qué dato quieres que olvide."
    return mem.olvidar(dato)


def guardar_broma_interna(broma, contexto=""):
    """Guarda una broma recurrente en la Memoria real con etiqueta propia."""
    mem = _memoria_principal()
    if mem is None:
        return "Todavía no tengo la memoria lista."
    dato = str(broma or "").strip()[:180]
    if not dato:
        return "No me dijiste qué broma quieres que guarde."
    contenido = ETIQUETA_BROMA + " " + dato
    ctx = str(contexto or "").strip()[:80]
    if ctx:
        contenido += f" (contexto: {ctx})"
    # Sin texto_usuario: 'guarda' dispararía la directiva y perdería la etiqueta.
    ok = mem.recordar(contenido, origen="explicito", fuente="orden_explicita")
    return f"Listo, guardé nuestra broma: {dato}" if ok else "No pude guardar esa broma de forma segura."


def agendar_seguimiento(tema, contexto="", horas_espera=24):
    """Programa un seguimiento real en la tabla kaya_seguimientos."""
    try:
        import ciclo_sueno_kaya
        uid = getattr(_memoria_principal(), "usuario_id", "local")
        ok = ciclo_sueno_kaya.agendar(tema, contexto, horas_espera, uid)
    except Exception:
        ok = False
    return (f"Listo, te lo retomo en {horas_espera} horas." if ok
            else "No pude agendar ese seguimiento de forma segura.")


def ejecutar_por_texto(texto: str) -> Any:
    """Atajo para órdenes en lenguaje natural dentro de ejecutar_accion_local."""
    try:
        return cap.detectar_y_ejecutar(texto)
    except Exception:
        return None


__all__ = [
    "declaraciones_extra", "despachar", "ejecutar_por_texto",
    "recordar_dato", "consultar_memoria", "olvidar_dato", "guardar_broma_interna",
    "agendar_seguimiento",
]
