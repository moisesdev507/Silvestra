"""Núcleo legado del planificador: archivos, recordatorios y conectores.

Se separa para mantener ``cerebro_planificador.py`` por debajo de 10 KB sin
duplicar motores: aquí vive exclusivamente el parseo heredado de órdenes.
"""
import re


def sanear_nombre_archivo(nom):
    """Normaliza nombres y extensiones mal transcritas por Whisper."""
    if not nom:
        return "archivo.txt"
    n = str(nom).strip().strip("'\"")
    n = re.sub(r"\.(?:tgit|tequisde|tequiste|txtt|t\s*x\s*t)$", ".txt", n, flags=re.I)
    n = n.replace(" ", "_")
    if "." not in n:
        n += ".txt"
    return n.lower()


def generar_contenido_archivo(instruccion):
    """Genera contenido real estructurado mediante LLM rápido o fallback robusto."""
    inst = str(instruccion or "").strip()
    if len(inst) < 3:
        return "Contenido generado para la tarea solicitada."
    try:
        import proveedores
        prompt = [
            {"role": "system", "content": (
                "Eres un asistente técnico conciso. Redacta directamente el texto solicitado para guardar en un archivo. "
                "Sin introducciones, sin saludos, sin explicaciones ni bloques de markdown vacíos. Solo el contenido útil."
            )},
            {"role": "user", "content": f"Escribe el contenido para: {inst}"},
        ]
        res = proveedores.completar(prompt, max_tokens=350)
        if res and len(res.strip()) > 15:
            # El proveedor puede devolver texto genérico; el encabezado conserva el tema pedido.
            return f"# {inst.capitalize()}\n{res.strip()}"
    except Exception:
        pass
    return f"# {inst.capitalize()}\n1. Tarea prioritaria inicial\n2. Desarrollo y pruebas unitarias\n3. Revisión y entrega"


def detectar_intencion_multipaso(texto):
    """Detecta peticiones con múltiples acciones encadenadas (tolerante a Whisper)."""
    t = str(texto or "").strip().lower()
    if len(t) < 8:
        return False
    archivo = r"(?:crea|llea|lea|escribe|guarda|haz)\s+(?:un\s+)?(?:archivo\s+)?(?:llamado\s+|nombrado\s+)?[a-zA-Z0-9_\-\.]+"
    rec = r"(?:recuerda(?:me)?|recuérdame|avisame|avísame|alarma|pon(?:\s+un)?\s+recordatorio)"
    if re.search(archivo, t, re.I) and re.search(rec, t, re.I):
        return True
    return any(re.search(p, t, re.I) for p in (
        r"\by\s+(?:luego|despues|después|ademas|además)\b",
        r"\b(?:busca|busca_youtube)\b.*\by\s+(?:guarda|escribe|anota)\b",
        r"\b(?:activa(?:\s+el)?\s+hud|abrir_hud)\b.*\by\s+(?:activa_modo|modo)\b",
    ))


def pasos_legacy(t):
    """Casos clásicos: archivo + recordatorio y conectores explícitos."""
    pasos = []
    m = re.search(
        r"(?:crea|llea|lea|escribe|guarda|haz)\s+(?:un\s+)?(?:archivo\s+)?(?:llamado\s+|nombrado\s+)?"
        r"([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?)\s+(?:con\s+)?(.*?)\s+y\s+"
        r"(?:recuerda(?:me)?|recuérdame|avisame|avísame|pon(?:\s+un)?\s+recordatorio|alarma)\s+(.*)",
        t, re.I)
    if m:
        archivo = sanear_nombre_archivo(m.group(1).strip())
        desc = m.group(2).strip() or f"Notas para {archivo}"
        orden = m.group(3).strip()
        contenido = generar_contenido_archivo(desc)
        tiempo = "en 5 minutos"
        que = f"revisar {archivo}"
        mt = re.search(
            r"(?:en\s+(?:\d+|un|una|uno|medio|media|dos|tres|cinco|diez|quince|veinte|treinta)\s*"
            r"(?:minutos?|mins?|segundos?|segs?|horas?|h\b)|mañana(?:\s+a\s+las\s+\d+)?|a\s+las\s+\d+)",
            orden, re.I)
        if mt:
            tiempo = mt.group(0).strip()
            resto = (orden[:mt.start()] + " " + orden[mt.end():]).strip()
            resto = re.sub(r"\b(avísame|avisame|recuérdame|recuerdame|que|de|para|sobre|por\s+favor)\b",
                           "", resto, flags=re.I).strip()
            if resto:
                que = resto
        elif orden:
            que = orden
        return [("escribir_archivo", f"{archivo} | {contenido}"),
                ("poner_recordatorio", f"{tiempo} | {que}")]
    frag = re.split(r"\s+y\s+(?:luego|despues|después|ademas|además)\s+|\s*&&\s*", t, flags=re.I)
    for trozo in frag[:3]:
        f = trozo.strip()
        if not f:
            continue
        if re.search(r"\b(?:crea|llea|lea|escribe|guardar?)\b.*\b(?:archivo|txt|py|md)\b", f, re.I):
            m2 = re.search(r"([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?)", f)
            pasos.append(("escribir_archivo", f"{sanear_nombre_archivo(m2.group(1)) if m2 else 'nota.txt'} | {f}"))
        elif re.search(r"\b(?:recuerda|avisame|recordatorio|alarma)\b", f, re.I):
            pasos.append(("poner_recordatorio", f))
        elif re.search(r"\b(?:activar?|abrir?)\b.*\b(?:hud|tablet)\b", f, re.I):
            pasos.append(("activar_hud", None))
        elif re.search(r"\b(?:modo)\s+(codigo|programacion|estudio|noche|normal)\b", f, re.I):
            m3 = re.search(r"\b(?:modo)\s+([a-zA-Z]+)", f, re.I)
            pasos.append(("activar_modo", m3.group(1) if m3 else "normal"))
    return pasos[:3]


__all__ = [
    "sanear_nombre_archivo", "generar_contenido_archivo",
    "detectar_intencion_multipaso", "pasos_legacy",
]
