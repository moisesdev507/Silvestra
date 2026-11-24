"""Motor agéntico de herramientas locales encadenadas.

Enrutamiento híbrido: consultas directas se resuelven al instante con datos
reales; las etiquetas ``[[TOOL:nombre|argumento]]`` permiten al modelo encadar
herramientas en un bucle controlado de hasta 2 rondas.
"""
import re
import unicodedata

import dev_copiloto as dev
import google_workspace as google
import memoria_persistente as memoria
import busqueda_web as web
import vision_pantalla as vision

LIMITE = 1600
_ETIQUETA = re.compile(
    r"\[\[TOOL:([A-Za-z_][A-Za-z0-9_]*)\s*\|?\s*([^\]]*)\]\]", re.I)


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _guardar_memoria(argumento):
    partes = str(argumento or "").split("|", 2)
    if len(partes) == 3:
        categoria, clave, valor = partes
    else:
        categoria, clave, valor = "general", "agente_" + str(argumento)[:40], str(argumento)
    fila = memoria.guardar_recuerdo(categoria, clave, valor)
    return "Guardado: " + (fila["valor"] if fila else "no se pudo guardar")


def _crear_evento(argumento):
    """Crea un evento: ``titulo|fecha_iso|duracion`` (fecha opcional)."""
    partes = str(argumento or "").split("|", 2)
    titulo = partes[0].strip()
    fecha = partes[1].strip() if len(partes) > 1 else ""
    duracion = partes[2].strip() if len(partes) > 2 else 60
    return google.crear_evento_calendario(titulo, fecha, duracion)


CATALOGO = {
    "estado_git": dev.estado_git,
    "descubrir_proyectos": dev.descubrir_proyectos,
    "buscar_codigo": dev.buscar_codigo,
    "estado_entorno_dev": dev.estado_entorno_dev,
    "abrir_en_vscode": dev.abrir_en_vscode,
    "buscar_memoria": memoria.buscar_recuerdos,
    "guardar_memoria": _guardar_memoria,
    "telemetria_pc": dev.telemetria_pc,
    "agenda_hoy": google.agenda_hoy,
    "crear_evento": _crear_evento,
    "resumen_correos": google.resumen_correos,
    "buscar_drive": google.buscar_drive,
    "buscar_web": web.buscar_web,
    "ver_pantalla": vision.analizar_pantalla,
}


def _formatear(nombre, datos):
    if isinstance(datos, bool):
        return "abierto en VS Code" if datos else "no se pudo abrir VS Code"
    if nombre == "descubrir_proyectos" and isinstance(datos, list):
        texto = " | ".join(f"{p.get('nombre')} ({p.get('stack')})"
                           for p in datos[:8] if isinstance(p, dict))
    elif isinstance(datos, dict):
        texto = datos.get("texto") or "; ".join(
            f"{k}: {v}" for k, v in list(datos.items())[:6])
    elif isinstance(datos, list):
        if datos and isinstance(datos[0], dict):
            texto = " | ".join(str(p.get("fragmento") or p.get("nombre")
                                    or p.get("valor") or p) for p in datos[:5])
        else:
            texto = ", ".join(str(p) for p in datos[:8])
    else:
        texto = str(datos)
    return (" ".join(str(texto or "").split()) or "sin datos")[:900]


def ejecutar(nombre, argumento=""):
    """Ejecuta una herramienta del catálogo y devuelve texto compacto."""
    funcion = CATALOGO.get(str(nombre or "").strip().lower())
    if funcion is None:
        return f"Herramienta desconocida: {nombre}"
    try:
        return _formatear(str(nombre).strip().lower(), funcion(argumento or ""))
    except Exception as exc:
        return f"Error en {nombre}: {type(exc).__name__}"


def _nombre_de(texto):
    bajo = _norm(texto)
    for proyecto in dev.descubrir_proyectos():
        if _norm(proyecto["nombre"]) in bajo:
            return proyecto["nombre"]
    return ""


def _clave_busqueda(texto):
    palabras = [p for p in re.findall(r"\w+", _norm(texto)) if len(p) >= 5]
    return max(palabras, key=len) if palabras else "def"


def detectar_intencion(consulta):
    """Devuelve pares (herramienta, argumento) para peticiones directas."""
    texto = _norm(consulta)
    if not texto:
        return []
    acciones = []
    if any(x in texto for x in ("git", "rama", "repositorio", "commit", "status")):
        acciones.append(("estado_git", ""))
    if any(x in texto for x in ("proyectos", "proyecto", "repositorios")):
        acciones.append(("descubrir_proyectos", ""))
    if any(x in texto for x in ("puerto", "puertos", "proceso", "procesos", "escuchando")):
        acciones.append(("estado_entorno_dev", ""))
    if any(x in texto for x in ("recuerdas", "recuerdos", "memoria", "guardaste", "sabes de")):
        acciones.append(("buscar_memoria", str(consulta)))
    if any(x in texto for x in ("bateria", "cpu", "ram", "disco", "telemetria")):
        acciones.append(("telemetria_pc", ""))
    if any(x in texto for x in ("codigo", "funcion", "busca en el", "error de")):
        acciones.append(("buscar_codigo", _clave_busqueda(consulta)))
    if "abrir" in texto and any(x in texto for x in ("vscode", "visual studio", "codigo")):
        acciones.append(("abrir_en_vscode", _nombre_de(consulta)))
    if any(x in texto for x in ("agendar", "agenda una", "crear evento",
                               "crear un evento", "programar entrega")):
        acciones.append(("crear_evento", str(consulta)))
    elif any(x in texto for x in ("agenda", "calendario", "reunion", "reuniones")):
        acciones.append(("agenda_hoy", ""))
    if any(x in texto for x in ("correo", "correos", "gmail", "bandeja")):
        acciones.append(("resumen_correos", ""))
    if any(x in texto for x in ("drive", "documento", "documentos")):
        acciones.append(("buscar_drive", str(consulta)))
    if any(x in texto for x in ("busca en internet", "buscar en internet", "busca en la web",
                                "buscar en la web", "busca en google", "noticias", "noticia",
                                "clima", "tiempo en", "precio de", "precio del", "cotizacion",
                                "quien gano", "partido de", "resultado de", "que paso con",
                                "documentacion de", "ultimas noticias")):
        acciones.append(("buscar_web", str(consulta)))
    if any(x in texto for x in ("mira mi pantalla", "mira la pantalla", "ves mi pantalla",
                                "ves la pantalla", "que ves", "lee este error", "que error tengo",
                                "que error sale", "analiza la pantalla", "analiza mi pantalla",
                                "que tengo en pantalla", "que hay en pantalla")):
        acciones.append(("ver_pantalla", str(consulta)))
    return acciones[:3]


def contexto_para_cerebro(consulta):
    """Bloque corto de datos reales para ``contexto_adicional`` (o "")."""
    intenciones = [p for p in detectar_intencion(consulta)
                   if p[0] != "abrir_en_vscode"]
    if not intenciones:
        return ""
    lineas = ["[HERRAMIENTAS LOCALES]"]
    for nombre, argumento in intenciones:
        lineas.append(f"{nombre}: {ejecutar(nombre, argumento)[:420]}")
    return "\n".join(lineas)[:LIMITE]


def responder_directo(consulta):
    """Respuesta ejecutiva inmediata, o ``None`` si no corresponde al router."""
    intenciones = detectar_intencion(consulta)
    if not intenciones:
        return None
    partes = [f"{nombre}: {ejecutar(nombre, argumento)}"
              for nombre, argumento in intenciones]
    return "Datos reales: " + " | ".join(partes)[:1000]


def limpiar_para_voz(texto):
    """Elimina prefijos técnicos tipo 'Datos reales: <herramienta>:' antes de hablar."""
    t = str(texto or "").strip()
    t = re.sub(r"^datos\s+reales:\s*", "", t, flags=re.I).strip()
    herramientas = "|".join(re.escape(k) for k in CATALOGO.keys())
    t = re.sub(rf"^({herramientas}):\s*", "", t, flags=re.I).strip()
    return t


def parsear_tags(texto):
    """Extrae (herramienta, argumento) de las etiquetas ``[[TOOL:...]]``."""
    return [(m.group(1).lower(), (m.group(2) or "").strip())
            for m in _ETIQUETA.finditer(str(texto or ""))]


def limpiar_tags(texto):
    """Quita etiquetas de herramientas para que nunca sean habladas."""
    return re.sub(r"\s*\[\[TOOL:[^\]]*\]\]\s*", " ", str(texto or "")).strip()


def ejecutar_bucle(texto, respond_fn=None, max_rondas=2):
    """Encadena herramientas hasta 2 rondas; ``respond_fn`` aporta la siguiente salida."""
    actual = str(texto or "")
    rondas = max(1, min(2, int(max_rondas or 2)))
    datos, usados, vuelta = [], [], 0
    ejecutadas = set()
    while vuelta < rondas:
        etiquetas = parsear_tags(actual)
        if vuelta == 0:
            etiquetas = detectar_intencion(limpiar_tags(actual)) + etiquetas
        if not etiquetas:
            break
        vuelta += 1
        for nombre, argumento in etiquetas:
            if (nombre, argumento) in ejecutadas:
                continue
            ejecutadas.add((nombre, argumento))
            datos.append({"herramienta": nombre, "argumento": argumento,
                          "resultado": ejecutar(nombre, argumento)})
            usados.append(nombre)
        if respond_fn is None:
            break
        try:
            actual = str(respond_fn(_resumen(datos)) or "")
        except Exception:
            break
    return {"respuesta": limpiar_tags(actual), "datos": datos,
            "rondas": vuelta, "herramientas": usados}


def _resumen(datos):
    return "\n".join(f"{d['herramienta']}: {d['resultado'][:420]}" for d in datos)[:LIMITE]


def post_llm(crudo, respuesta, al_frase=None):
    """Ejecuta etiquetas del texto ya recibido y devuelve la respuesta limpia."""
    if not parsear_tags(crudo):
        return respuesta
    resultado = ejecutar_bucle(crudo, None, 2)
    limpio = limpiar_tags(respuesta) or resultado["respuesta"]
    if al_frase and resultado["datos"] and limpio and limpio != respuesta:
        try:
            al_frase(limpio[:400])
        except Exception:
            pass
    return limpio


__all__ = ["CATALOGO", "ejecutar", "detectar_intencion", "contexto_para_cerebro",
           "responder_directo", "limpiar_para_voz", "parsear_tags", "limpiar_tags",
           "ejecutar_bucle", "post_llm"]
