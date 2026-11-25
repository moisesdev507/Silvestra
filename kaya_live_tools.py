"""Herramientas (manos, memoria y ojos de escritorio) para Kaya Gemini Live.

Ejecución segura de tools de Function Calling sin bloquear el streaming de audio.
Incluye control de privacidad para cámara y pantalla (ojos_activos) y ejecución
de acciones locales del sistema Silvestra mediante kaya_live_puente.py.
"""
import asyncio
import datetime
import os
import threading
from typing import Any, Dict, List
from google.genai import types

import kaya_live_puente

_OJOS_ACTIVOS = True
_LOCK_OJOS = threading.RLock()


def obtener_estado_ojos() -> bool:
    with _LOCK_OJOS:
        return _OJOS_ACTIVOS


def controlar_ojos(activo: bool) -> str:
    global _OJOS_ACTIVOS
    with _LOCK_OJOS:
        _OJOS_ACTIVOS = bool(activo)
        estado = "abiertos" if _OJOS_ACTIVOS else "cerrados"
        return f"Ojos {estado}. Visión por cámara y pantalla {'habilitada' if _OJOS_ACTIVOS else 'deshabilitada por privacidad'}."


def consultar_sistema() -> str:
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info = [f"Fecha y hora: {ahora}"]
    try:
        import telemetria
        estado = telemetria.estado_sistema()
        txt = estado.get("texto") or str(estado)
        info.append(f"Estado del equipo: {txt}")
    except Exception:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            bat = psutil.sensors_battery()
            b_str = f", batería {bat.percent}%" if bat else ""
            info.append(f"CPU: {cpu}%, RAM: {ram}%{b_str}")
        except Exception as e:
            info.append(f"No se pudieron leer métricas: {e}")
    return " | ".join(info)


def buscar_en_web(consulta: str) -> str:
    c = str(consulta or "").strip()
    if not c:
        return "Consulta vacía."
    try:
        import busqueda_web
        res = busqueda_web.buscar_web(c)
        if isinstance(res, dict):
            resultados = res.get("results") or res.get("resultados") or []
            if resultados:
                fragmentos = []
                for r in resultados[:3]:
                    tit = r.get("title") or ""
                    con = r.get("content") or r.get("snippet") or ""
                    fragmentos.append(f"{tit}: {con}" if tit else con)
                return "\n".join(fragmentos)[:800]
            answer = res.get("answer")
            if answer:
                return str(answer)[:600]
        return str(res)[:800]
    except Exception as e:
        return f"Error al buscar en web: {e}"


def ver_pantalla(pregunta: str = "") -> str:
    if not obtener_estado_ojos():
        return "Tengo los ojos cerrados por privacidad. Pídeme que los abra para poder ver la pantalla."
    try:
        import vision_pantalla
        preg = pregunta or "¿Qué hay en pantalla de forma resumida?"
        resp = vision_pantalla.capturar_y_analizar_pantalla(preg)
        return str(resp or "No se pudo interpretar la pantalla.")[:800]
    except Exception as e:
        return f"No pude capturar la pantalla: {e}"


def ver_camara_pc(pregunta: str = "") -> str:
    if not obtener_estado_ojos():
        return "Tengo los ojos cerrados por privacidad. Pídeme que los abra para poder ver por la cámara."
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return "No hay cámara web disponible o está ocupada."
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return "La cámara abrió pero no pudo capturar fotograma."
        h, w = frame.shape[:2]
        return f"Cámara web capturada exitosamente ({w}x{h}). Imagen recibida."
    except Exception as e:
        return f"Error accediendo a la cámara web: {e}"


def gestionar_memoria_temas(accion: str, tema: str = "", detalle: str = "") -> str:
    act = (accion or "leer").strip().lower()
    try:
        import iniciativa_kaya
        if act in ("leer", "consultar", "listar"):
            temas = iniciativa_kaya.obtener_temas_abiertos()
            if not temas:
                return "No hay temas ni pendientes abiertos en memoria."
            res = [f"- {t.get('tema')}: {t.get('contexto', '')}" for t in temas[:5]]
            return "Temas abiertos actuales:\n" + "\n".join(res)
        elif act in ("cerrar", "completar", "terminar"):
            if not tema:
                return "Debes indicar el nombre del tema a cerrar."
            iniciativa_kaya.cerrar_tema(tema)
            return f"Tema '{tema}' cerrado en memoria."
        elif act in ("guardar", "registrar", "agregar", "recordar"):
            if not tema:
                return "Debes indicar el tema o pendiente a recordar."
            iniciativa_kaya.registrar_tema_abierto(tema, detalle or tema)
            return f"Tema '{tema}' guardado en la memoria de Kaya."
        return f"Acción '{accion}' no reconocida. Usa 'leer', 'guardar' o 'cerrar'."
    except Exception as e:
        return f"Error gestionando memoria de temas: {e}"


def ejecutar_accion_pc(instruccion: str) -> str:
    """Ejecuta cualquier orden sobre el computador del usuario vía kaya_live_puente."""
    return kaya_live_puente.ejecutar_accion_local(instruccion)


DECLARACIONES_HERRAMIENTAS = [
    types.FunctionDeclaration(
        name="ejecutar_accion_pc",
        description="USA ESTA HERRAMIENTA SIEMPRE para cualquier habilidad personal de Kaya y acciones en la PC: leer o escribir en tu diario personal ('qué dice tu diario', 'anota en tu diario'), revisar ideas o hilos pendientes, leer/resumir correos o Gmail, consultar agenda o calendario de Google, abrir o cerrar programas/apps (Chrome, Bloc de notas, Spotify, Calculadora), subir/bajar volumen o silenciar, programar recordatorios ('recuérdame en 10 mins...'), crear/leer archivos locales, minimizar ventanas o activar el HUD.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"instruccion": types.Schema(type="STRING", description="Instrucción en lenguaje natural o comando de la acción pedida por el usuario.")},
            required=["instruccion"],
        ),
    ),
    types.FunctionDeclaration(
        name="consultar_sistema",
        description="Devuelve fecha/hora y métricas de CPU, RAM y batería de la laptop.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="buscar_en_web",
        description="Busca información actualizada en internet sobre noticias, clima o datos externos.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"consulta": types.Schema(type="STRING", description="Término o pregunta para buscar en internet.")},
            required=["consulta"],
        ),
    ),
    types.FunctionDeclaration(
        name="ver_pantalla",
        description="Captura y analiza lo que está visible en la pantalla de la PC.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"pregunta": types.Schema(type="STRING", description="Pregunta específica sobre la pantalla.")},
        ),
    ),
    types.FunctionDeclaration(
        name="ver_camara_pc",
        description="Captura un fotograma de la webcam para ver al usuario o su entorno.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"pregunta": types.Schema(type="STRING", description="Pregunta sobre la cámara.")},
        ),
    ),
    types.FunctionDeclaration(
        name="gestionar_memoria_temas",
        description="Lee, guarda o cierra temas y proyectos pendientes de conversaciones en la memoria de Kaya.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "accion": types.Schema(type="STRING", description="Acción: 'leer', 'guardar' o 'cerrar'."),
                "tema": types.Schema(type="STRING", description="Nombre del tema o pendiente."),
                "detalle": types.Schema(type="STRING", description="Detalle del tema."),
            },
            required=["accion"],
        ),
    ),
    types.FunctionDeclaration(
        name="controlar_ojos",
        description="Activa o desactiva la visión por cámara y pantalla por privacidad ('cierra los ojos', etc.).",
        parameters=types.Schema(
            type="OBJECT",
            properties={"activo": types.Schema(type="BOOLEAN", description="True para abrir ojos, False para cerrarlos por privacidad.")},
            required=["activo"],
        ),
    ),
]


def obtener_herramientas_live() -> List[types.Tool]:
    return [types.Tool(function_declarations=DECLARACIONES_HERRAMIENTAS)]


async def despachar_herramienta(nombre: str, args: Dict[str, Any]) -> Any:
    args = args or {}
    nom = (nombre or "").strip()
    mapa = {
        "ejecutar_accion_pc": lambda: ejecutar_accion_pc(args.get("instruccion", "")),
        "consultar_sistema": lambda: consultar_sistema(),
        "buscar_en_web": lambda: buscar_en_web(args.get("consulta", "")),
        "ver_pantalla": lambda: ver_pantalla(args.get("pregunta", "")),
        "ver_camara_pc": lambda: ver_camara_pc(args.get("pregunta", "")),
        "gestionar_memoria_temas": lambda: gestionar_memoria_temas(args.get("accion", "leer"), args.get("tema", ""), args.get("detalle", "")),
        "controlar_ojos": lambda: controlar_ojos(args.get("activo", True)),
    }
    fn = mapa.get(nom)
    if not fn:
        return {"resultado": f"Herramienta '{nom}' no encontrada."}
    try:
        resultado = await asyncio.to_thread(fn)
        return {"resultado": resultado}
    except Exception as e:
        return {"error": f"Fallo ejecutando {nom}: {e}"}
