"""Descomposición y síntesis ligeras para el conector agéntico."""
import os
import re

import agente_herramientas as ah


def archivo(nombre):
    """Normaliza nombres mal transcritos y conserva solo el basename."""
    n = str(nombre or "archivo.txt").strip().strip("'\"")
    n = re.sub(r"\.(?:tgit|tequisde|tequiste|txtt|t\s*x\s*t)$", ".txt", n, flags=re.I)
    n = os.path.basename(n.replace(" ", "_"))
    return (n if "." in n else n + ".txt").lower()


def contenido(desc):
    """Contenido determinista y seguro cuando no se consulta al LLM."""
    limpio = re.sub(r"\s+", " ", str(desc or "")).strip(" .")
    return f"Notas de la tarea: {limpio or 'puntos pendientes'}."


def tiempo(orden, objetivo):
    """Extrae el tiempo y deja el resto como texto del recordatorio."""
    pat = (r"(en\s+(?:\d+|un|una|uno|dos|tres|cinco|diez|quince|veinte|treinta)\s*"
           r"(?:minutos?|mins?|horas?|h\b)|mañana(?:\s+a\s+las\s+\d+)?|a\s+las\s+\d+)")
    m = re.search(pat, orden, re.I)
    cuando = m.group(0).strip() if m else "en 5 minutos"
    resto = orden if not m else orden[:m.start()] + " " + orden[m.end():]
    resto = re.sub(
        r"\b(?:avísame|avisame|recuérdame|recuerdame|recuerda|que|de|para|sobre|por favor)\b",
        "", resto, flags=re.I).strip(" ,.;")
    return f"{cuando} | {resto or 'revisar ' + objetivo}"


def planificar(texto):
    """Devuelve [(herramienta, argumento)] o una lista vacía."""
    t = str(texto or "").strip()
    m = re.match(r"^(?:accion\s*:\s*)?([a-z_][a-z0-9_]*)\s*\|\s*(.+)$", t, re.I)
    if m:
        nom = m.group(1).lower()
        return [(nom, m.group(2).strip())] if ah.obtener(nom, ah.catalogo(True)) else []

    m = re.search(
        r"(?:crea|crear|llea|lea|escribe|escribir|guarda|guardar|haz)\s+"
        r"(?:(?:el|la|un|una)\s+)?(?:archivo\s+)?(?:llamado\s+|nombrado\s+)?"
        r"([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)\s*(?:con\s+)?(.*?)\s+y\s+"
        r"(?:(?:luego|despues|después|ademas|además)\s+)?"
        r"(?:recuérdame|recuerdame|recuerda(?:me)?|avísame|avisame|"
        r"pon(?:\s+un)?\s+recordatorio|alarma)\s+(.*)", t, re.I)
    if m:
        arc = archivo(m.group(1))
        return [
            ("escribir_archivo", f"{arc} | {contenido(m.group(2))}"),
            ("poner_recordatorio", tiempo(m.group(3), arc)),
        ]

    sep = r"\s+y\s+(?:luego|despues|después|ademas|además)\s+|\s*&&\s*"
    if not re.search(sep, t, re.I):
        return []
    pasos = []
    for frag in re.split(sep, t, flags=re.I):
        f = frag.strip()
        if re.search(r"\b(?:crea|llea|lea|escribe|guarda)\b.*\b(?:archivo|txt|py|md)\b", f, re.I):
            m_a = re.search(r"([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)", f)
            nom = archivo(m_a.group(1)) if m_a else "nota.txt"
            pasos.append(("escribir_archivo", f"{nom} | {contenido(f)}"))
        elif re.search(r"\b(?:recuerda|avisame|recordatorio|alarma)\b", f, re.I):
            pasos.append(("poner_recordatorio", tiempo(f, "la tarea")))
    return pasos[:3]


def catalogo(pasos):
    """Catálogo real más el recordatorio sintético si hace falta."""
    items = ah.catalogo(True)
    if "poner_recordatorio" in {n for n, _ in pasos} and not ah.obtener("poner_recordatorio", items):
        items.append(ah.Herramienta(
            "poner_recordatorio", "programa un recordatorio", ("texto",),
            ("silvestra_activa",), ("respuesta_al_usuario",), "medio"))
    return items


def sintetizar(pasos, ejecutados, resultado, indice):
    """Convierte los resultados observados en una respuesta hablada única."""
    if resultado.cancelado:
        return "Cancelé la ejecución a mitad del proceso; no hice cambios adicionales."
    if resultado.motivo in ("confirmacion_no_disponible", "confirmacion_rechazada"):
        nom = pasos[min(indice["actual"], len(pasos) - 1)][0]
        return f"No ejecuté {nom} porque no recibí confirmación."
    detalles = []
    for i, (nom, _) in enumerate(pasos):
        item = ejecutados.get(i)
        if not item or not item[1]:
            continue
        if nom == "escribir_archivo":
            m = re.search(r"'([^']+)'", item[2])
            detalles.append(f"guardé '{m.group(1) if m else 'el archivo'}' con su contenido")
        elif nom == "poner_recordatorio":
            detalles.append("programé tu recordatorio")
        elif nom in ("activar_hud", "abrir_hud"):
            detalles.append("activé el HUD en la tablet")
        else:
            detalles.append(f"completé {nom}")
    if not detalles:
        return "No pude completar la solicitud; no ejecuté ninguna acción."
    if len(detalles) == len(pasos):
        return f"Listo. {', y '.join(detalles)} con éxito."
    return f"Pude completar {len(detalles)} de {len(pasos)} pasos; el resto no se ejecutó."
