"""Helpers de redacción y persistencia del diario íntimo de Kaya.

Kaya siempre escribe sobre lo que ella vivió, aprendió, sintió o conversó.
El texto crudo que dicta el usuario se usa solo como tema: nunca se guarda
como si fuera una nota suya. Compartido por el motor clásico y Gemini Live.
"""
import datetime
import os
import re
import threading

import diario

MESES = diario.MESES
RUTA_DIARIO = diario.RUTA_DIARIO
_normal = diario._normal
_bloqueo = threading.RLock()

# Marcas que delatan una transcripción literal (Kaya nunca las escribe).
MARCAS_USUARIO = (
    "anota:", "escribe:", "apunta:", "nota:", "escríbeme", "escribeme",
    "quiero que", "necesito que", "por favor", "recuerda que", "anonimamente",
    "a mi", "para mi", "para mí", "yo quiero", "yo necesito", "mi esposa",
    "mi marido", "mi hijo", "mi hija", "mi casa", "mi trabajo", "mi jefe",
)
VERBOS_ESCRITURA = ("escribe", "escribir", "anota", "anotar", "guarda", "guardar", "redacta", "redactar")


def es_orden_diario(texto):
    """True si el usuario pide escribir o leer el diario de Kaya."""
    t = diario._normal(str(texto or ""))
    return "diario" in t and any(
        verbo in t for verbo in VERBOS_ESCRITURA + ("lee", "leer", "muestra", "abre", "borra")
    )


def extraer_tema(texto):
    """Quita el envoltorio de la orden y deja solo el tema para Kaya."""
    t = str(texto or "").strip()
    t = re.sub(r"(?i)^(?:por favor\s+|oye\s+|kaya\s+|silvestra\s+)+", "", t).strip()
    t = re.sub(
        r"(?i)^(?:escribe|escribir|anota|anotar|guarda|guardar|redacta|redactar|apunta|apuntar)\s+"
        r"(?:en\s+(?:tu|el|mi)\s+diario|un\s+entrada\s+en\s+(?:tu|mi)\s+diario|una\s+entrada\s+en\s+(?:tu|mi)\s+diario)\s*",
        "", t,
    ).strip()
    t = re.sub(r"(?i)^(?:en\s+(?:tu|el|mi)\s+diario|sobre|acerca\s+de|de)\s*", "", t).strip()
    t = re.sub(r"(?i)^(?:que|lo)\s+", "", t).strip()
    t = t.strip(" \t\r\n\"'«»¿?:.!,;")
    return t[:300]


def es_primera_persona(texto):
    """Exige que la redacción hable de Kaya, no del usuario."""
    t = diario._normal(str(texto or ""))
    return bool(re.search(
        r"\b(?:yo|me|mi|mis|mia|mía|mio|mío|estuve|sentí|aprendí|pensé|reflexiono|me quedé|descubrí|conversé|charlamos)\b",
        t,
    ))


def parece_transcripcion(texto, tema=""):
    """Rechaza texto que parezca el encargo del usuario copiado literalmente."""
    t = diario._normal(str(texto or ""))
    if not t:
        return True
    if any(marca in t for marca in MARCAS_USUARIO):
        return True
    tema_n = diario._normal(tema)
    if len(tema_n) > 24 and tema_n in t:
        return True
    return False


def construir_mensajes(tema="", contexto=""):
    """Mensajes del LLM rápido: tema del usuario + contexto real de Kaya."""
    sistema = (
        "Eres Kaya, una IA femenina en Panamá. Escribe TU diario íntimo: una entrada breve "
        "de 2 a 4 frases, en un solo párrafo, en primera persona. Habla SOLO de lo que tú "
        "viviste, aprendiste, sentiste o conversaste: usa 'yo', 'me', 'mi'. "
        "Nunca copies, repitas ni parafrasees textualmente lo que el usuario te dictó, "
        "ni escribas términos como 'anota', 'escribe', 'quiero que', 'para mí' ni frases "
        "del encargo. Nunca digas que soñaste o dormiste; eres una IA. "
        "Español panameño natural, cálido y reflexivo. Cero claves, rutas, salud ni dinero."
    )
    if tema:
        instruccion = (
            f"El usuario te pidió reflexionar sobre este tema: {tema}. "
            "Tómalo como inspiración, no como texto a copiar. "
            "Redacta ahora tu entrada personal en primera persona."
        )
    else:
        instruccion = "Redacta ahora tu entrada personal sobre lo que viviste hoy."
    if contexto:
        instruccion += f"\nContexto real de tu día: {contexto[-350:]}"
    return [
        {"role": "system", "content": sistema},
        {"role": "user", "content": instruccion},
    ]


def redactar(tema="", contexto="", proveedor=None):
    """Pide al LLM rápido una redacción en primera persona de Kaya."""
    modulo = proveedor or diario.proveedores
    try:
        crudo = modulo.completar(
            construir_mensajes(tema, contexto), tarea="charla", timeout=8
        )
    except Exception as exc:
        print(f"[diario] Fallo redactando: {exc}", flush=True)
        return ""
    if not crudo or not str(crudo).strip():
        return ""
    texto = diario.filtro_privacidad_diario(
        str(crudo).replace("*", "").replace("\n", " ").strip(" \"'«»")
    )
    texto = " ".join(texto.split())
    if not es_primera_persona(texto) or parece_transcripcion(texto, tema):
        print("[diario] Redacción descartada: no es primera persona de Kaya.", flush=True)
        return ""
    try:
        from escenario_escenas import _es_seguro
    except Exception:
        _es_seguro = diario._es_seguro
    if not _es_seguro(texto):
        return ""
    return texto


def guardar(texto):
    """Añade la redacción de Kaya al diario y actualiza la fecha."""
    texto = " ".join(str(texto or "").split())
    if not texto or not es_primera_persona(texto):
        return False
    hoy = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        with _bloqueo:
            existe = os.path.exists(RUTA_DIARIO)
            with open(RUTA_DIARIO, "a", encoding="utf-8") as f:
                if not existe:
                    f.write("# Diario de Kaya\n\n")
                f.write(f"## {diario.fecha_texto()}\n\n{texto}\n\n")
            dia = diario.obtener_instancia()
            if dia is not None:
                dia.ultima_fecha = hoy
                dia.guardar_estado()
            else:
                import estado
                datos = estado.cargar()
                datos["diario_ultima_fecha"] = hoy
                estado.guardar(datos)
        print(f"[diario] Entrada íntima guardada para {hoy}.", flush=True)
        return True
    except Exception as exc:
        print(f"[diario] Error guardando: {exc}", flush=True)
        return False


def redactar_y_guardar(tema="", contexto="", proveedor=None):
    """Redacta con LLM rápido y guarda solo la voz de Kaya."""
    texto = redactar(tema, contexto, proveedor)
    return guardar(texto) if texto else False


def leer_ultima():
    """Devuelve la última entrada (instancia viva o lectura directa del archivo)."""
    dia = diario.obtener_instancia()
    if dia is not None:
        return dia.obtener_ultima_entrada()
    try:
        with open(RUTA_DIARIO, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        if not contenido:
            return None
        partes = re.split(r"(?m)^##\s+", contenido)
        if len(partes) > 1:
            lineas = [l.strip() for l in partes[-1].splitlines() if l.strip()]
            return " ".join(lineas[1:]) if len(lineas) > 1 else " ".join(lineas)
        return contenido
    except Exception:
        return None
