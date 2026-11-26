"""Herramientas cognitivas compartidas por Gemini Live y la voz clásica.

Reutiliza el RAG local, el grafo vivo y el orquestador de resúmenes existente;
no duplica motores ni depende de Qt en el arranque clásico.
"""
import re
import threading

import cerebro_grafo
import cerebro_rag
import resumen
import resumen_media
import resumen_web


def consultar_conocimiento_local(consulta, ruta=""):
    """Indexa si hace falta y busca en documentos locales y en el grafo vivo."""
    texto = str(consulta or "").strip()
    if not texto:
        return "No me dijiste qué quieres buscar en tu conocimiento local."
    if str(ruta or "").strip():
        try:
            ok, detalle = cerebro_rag.indexar_ruta(str(ruta).strip())
            if not ok:
                return f"No pude indexar esa ruta: {detalle}"
        except Exception as exc:
            return f"No pude indexar esa ruta: {type(exc).__name__}"
    partes = []
    try:
        rag = cerebro_rag.consultar_rag(texto, limite=3)
        if rag:
            partes.append(rag.strip())
    except Exception:
        pass
    try:
        relaciones = cerebro_grafo.consultar_relaciones(texto, limite=6)
        vistos, lineas = set(), []
        for rel in relaciones or []:
            linea = f"- {rel.get('sujeto', '')} {rel.get('relacion', '')}: {rel.get('objeto', '')}"
            if linea not in vistos:
                vistos.add(linea)
                lineas.append(linea)
        if lineas:
            partes.append("[GRAFO DE RELACIONES]\n" + "\n".join(lineas))
    except Exception:
        pass
    if not partes:
        return "No encontré nada en tus documentos locales ni en el grafo sobre eso."
    return "\n\n".join(partes)[:1600]


def resumir_enlace_o_video(url):
    """Resume una página web o un video de YouTube con el orquestador real."""
    valor = str(url or "").strip()
    if not valor:
        return "No me diste ningún enlace para resumir."
    url_limpia = resumen_web.limpiar_url(valor)
    objetivo = url_limpia or valor
    try:
        if resumen_media.es_enlace_youtube(objetivo):
            texto, error = resumen_media.obtener_subtitulos_youtube(objetivo)
            titulo = f"Video YouTube {objetivo}"
        else:
            if not url_limpia:
                return "No encontré una dirección web válida en lo que me dijiste."
            html, error = resumen_web.descargar_pagina(url_limpia)
            texto = resumen_web.extraer_texto_html(html) if html and not error else ""
            titulo = url_limpia
    except Exception as exc:
        return f"No pude abrir ese enlace: {type(exc).__name__}"
    if error == "REQUIERE_LIBRERIA":
        return "Para resumir ese video necesito la librería ligera youtube-transcript-api."
    if error:
        return f"No pude resumir el enlace: {error}"
    if not texto or len(str(texto).strip()) < 50:
        return "El enlace no trae suficiente texto para hacer un resumen."
    try:
        return resumen.procesar_resumen_texto(None, str(texto), titulo_origen=titulo)
    except Exception as exc:
        return f"No pude generar el resumen: {type(exc).__name__}"


def declaraciones():
    """Declaraciones Function Calling de Live (importación diferida de genai)."""
    from google.genai import types

    return [
        types.FunctionDeclaration(
            name="consultar_conocimiento_local",
            description=(
                "Busca en los documentos locales indexados y en el grafo de conocimiento vivo. "
                "Úsala para preguntas sobre proyectos, archivos, notas o hechos ya aprendidos."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "consulta": types.Schema(type="STRING", description="Qué buscar."),
                    "ruta": types.Schema(type="STRING", description="Carpeta a indexar antes de buscar, si aplica."),
                },
                required=["consulta"],
            ),
        ),
        types.FunctionDeclaration(
            name="resumir_enlace_o_video",
            description=(
                "Descarga y resume una página web o un video de YouTube. "
                "Úsala cuando el usuario pida resumir un enlace, una web o un video."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "url": types.Schema(type="STRING", description="Enlace https o video de YouTube."),
                },
                required=["url"],
            ),
        ),
    ]


def despachar(nombre, args=None):
    """Despacha las dos herramientas nuevas; None si el nombre no corresponde."""
    datos = args or {}
    if nombre == "consultar_conocimiento_local":
        return consultar_conocimiento_local(
            str(datos.get("consulta", "")), str(datos.get("ruta", "")))
    if nombre == "resumir_enlace_o_video":
        return resumir_enlace_o_video(str(datos.get("url", "")))
    return None


def _separar(texto):
    bruto = str(texto or "").strip()
    ruta = ""
    hallazgo = re.search(r"\bruta\s*[:=]\s*(.+)$", bruto, re.I)
    if hallazgo:
        ruta = hallazgo.group(1).strip()
        bruto = bruto[:hallazgo.start()].strip()
    return bruto, ruta


def accion_consultar(texto):
    """Adaptador de Celeste para la acción viva 'consultar_conocimiento'."""
    consulta, ruta = _separar(texto)
    return consultar_conocimiento_local(consulta, ruta)


def accion_resumir(texto, app=None):
    """Adaptador de Celeste; con app responde por la cola sin bloquear la UI."""
    if app is None:
        return resumir_enlace_o_video(texto)
    url = str(texto or "").strip()

    def tarea():
        resultado = resumir_enlace_o_video(url)
        try:
            app.cola.put(("hablar", resultado))
        except Exception:
            pass

    threading.Thread(target=tarea, daemon=True, name="cerebro-resumen").start()
    return "Voy a abrir ese enlace y te digo lo importante."


__all__ = [
    "consultar_conocimiento_local", "resumir_enlace_o_video",
    "declaraciones", "despachar", "accion_consultar", "accion_resumir",
]
