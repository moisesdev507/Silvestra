"""Búsqueda semántica por categorías, sinónimos y resumen de memoria antigua."""
import re
import unicodedata

STOPWORDS = {
    "que", "para", "por", "con", "del", "las", "los", "una", "uno", "unos",
    "unas", "como", "esta", "este", "estos", "estas", "pero", "mas", "muy",
    "dime", "sabes", "sobre", "esto", "hacer", "hola", "silvestra", "favor",
    "algo", "nada", "todo", "todos", "todas", "donde", "cuando", "quien",
    "cual", "cuales", "gusta", "gustar", "tengo", "tiene", "tienen", "buenos",
    "dias", "saber", "recuerdas", "recuerda", "cuenta", "cuentame", "de", "la",
    "el", "en", "al", "mi", "mis", "tu", "tus", "su", "sus", "yo", "me", "te"
}

CATEGORIAS = {
    "familia": {
        "mama", "madre", "papa", "padre", "hermano", "hermana", "hermanito",
        "abuelo", "abuela", "tio", "tia", "primo", "prima", "familia", "pariente",
        "hijo", "hija", "esposa", "esposo", "novia", "novio", "pareja", "mascota",
        "perro", "gato"
    },
    "trabajo": {
        "trabajo", "trabajar", "labor", "laborar", "empleo", "oficina", "empresa",
        "jefe", "sueldo", "salario", "chamba", "programador", "desarrollador",
        "codigo", "puesto", "cargo", "profesion", "carrera", "negocio", "cliente",
        "dev", "software"
    },
    "comida": {
        "comida", "comer", "cena", "cenar", "almuerzo", "almorzar", "desayuno",
        "desayunar", "plato", "receta", "cocinar", "restaurante", "pizza", "sushi",
        "pasta", "pastas", "carne", "pollo", "arroz", "postre", "fruta", "dulce",
        "cafe", "te", "beber", "bebida"
    },
    "planes": {
        "plan", "planes", "meta", "metas", "objetivo", "futuro", "sueno", "manana",
        "viaje", "viajar", "cita", "examen", "estudiar", "prueba", "vacaciones",
        "salida", "evento", "curso", "universidad", "graduacion"
    },
    "proyectos": {
        "proyecto", "proyectos", "silvestra", "software", "app", "aplicacion",
        "invento", "prototipo", "bot", "sistema", "python", "programa", "codigo",
        "anillo", "hardware", "repositorio", "github"
    },
}


def normalizar(texto):
    """Convierte a minúsculas y quita acentos."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def extraer_palabras_clave(texto):
    """Extrae palabras relevantes excluyendo stopwords."""
    norm = normalizar(texto)
    palabras = set(re.findall(r"\b[a-z]{3,}\b", norm))
    return palabras - STOPWORDS


def identificar_categorias(palabras):
    """Determina qué categorías temáticas corresponden a las palabras dadas."""
    cats = set()
    for cat, terminos in CATEGORIAS.items():
        if palabras & terminos:
            cats.add(cat)
    return cats


def buscar_recuerdos(hechos, texto_actual, max_recuerdos=5, resumenes_tematicos=None):
    """Puntúa y selecciona los recuerdos más relevantes usando palabras clave y categorías."""
    hechos_unicos = list(dict.fromkeys(h.strip() for h in hechos if h and h.strip()))
    if not hechos_unicos:
        return [], 0

    if not texto_actual or not str(texto_actual).strip():
        elegidos = hechos_unicos[-max_recuerdos:]
        return elegidos, len(elegidos)

    palabras_q = extraer_palabras_clave(texto_actual)
    cats_q = identificar_categorias(palabras_q)

    # Si no hay palabras clave tras el filtro, retornar los más recientes
    if not palabras_q and not cats_q:
        elegidos = hechos_unicos[-max_recuerdos:]
        return elegidos, len(elegidos)

    scored = []
    total_hechos = len(hechos_unicos)
    for idx, h in enumerate(hechos_unicos):
        h_norm = normalizar(h)
        h_words = extraer_palabras_clave(h_norm)

        # 1. Coincidencias exactas de palabras
        coincidencias_directas = palabras_q & h_words
        score = len(coincidencias_directas) * 4.0

        # 2. Coincidencias temáticas por categoría
        for cat in cats_q:
            score += len(h_words & CATEGORIAS[cat]) * 2.0

        # 3. Coincidencia de subcadenas si hay palabras compuestas
        for pq in palabras_q:
            if len(pq) >= 4 and pq in h_norm:
                score += 1.5

        # 4. Pequeño factor de frescura (los más recientes desempatan arriba)
        score += (idx / max(1, total_hechos)) * 0.2

        if score > 0.5:
            scored.append((score, h))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        elegidos = [h for _, h in scored[:max_recuerdos]]
    else:
        elegidos = []

    # Si hay resúmenes temáticos antiguos que coinciden con las categorías consultadas
    if resumenes_tematicos and isinstance(resumenes_tematicos, dict) and cats_q:
        for cat in cats_q:
            if cat in resumenes_tematicos and resumenes_tematicos[cat]:
                res_txt = f"[Resumen temático {cat.capitalize()}]: {resumenes_tematicos[cat]}"
                if res_txt not in elegidos and len(elegidos) < max_recuerdos:
                    elegidos.append(res_txt)

    return elegidos, len(elegidos)


def clasificar_hecho_en_categoria(hecho):
    """Clasifica un hecho individual en la categoría temática más adecuada."""
    words = extraer_palabras_clave(hecho)
    mejor_cat = "otros"
    max_pts = 0
    for cat, terms in CATEGORIAS.items():
        pts = len(words & terms)
        if pts > max_pts:
            max_pts = pts
            mejor_cat = cat
    return mejor_cat


def resumir_memoria_antigua(memoria, pedir_fn=None):
    """Cuando hay más de 200 recuerdos, resume los viejos en un párrafo por tema."""
    hechos = memoria.datos.get("hechos", [])
    if len(hechos) <= 200:
        return False

    # Conservar los 150 más recientes detallados y resumir los anteriores
    corte = len(hechos) - 150
    viejos = hechos[:corte]
    recientes = hechos[corte:]

    grupos = {}
    for h in viejos:
        cat = clasificar_hecho_en_categoria(h)
        grupos.setdefault(cat, []).append(h)

    resumenes = memoria.datos.get("resumenes_tematicos", {})
    if not isinstance(resumenes, dict):
        resumenes = {}

    for cat, items in grupos.items():
        if not items:
            continue
        bloque_items = "\n".join(f"- {h}" for h in items)
        if pedir_fn:
            try:
                sistema = (
                    "Eres un sintetizador de memoria conciso y 100% verídico. "
                    f"Sintetiza los siguientes hechos antiguos del usuario sobre el tema '{cat}' en un único "
                    "párrafo breve y fluido (máximo 3 frases). "
                    "NO inventes datos, conserva nombres propios, fechas y gustos reales."
                )
                mensajes = [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": bloque_items},
                ]
                parrafo = pedir_fn(mensajes, tarea="charla")
                if parrafo and len(parrafo.strip()) > 10:
                    prev = resumenes.get(cat, "")
                    resumenes[cat] = f"{prev} {parrafo.strip()}".strip()
                    continue
            except Exception as e:
                print(f"[memoria] resumen con LLM no disponible ({e}), usando síntesis local", flush=True)

        # Síntesis local compacta si no hay LLM
        hechos_limpios = [re.sub(r"^\[[^\]]+\]\s*", "", x).strip() for x in items]
        sintesis = " ".join(f"{h.rstrip('.')}." for h in hechos_limpios[:6])
        prev = resumenes.get(cat, "")
        resumenes[cat] = f"{prev} {sintesis}".strip()

    memoria.datos["hechos"] = recientes
    memoria.datos["resumenes_tematicos"] = resumenes
    memoria.guardar()
    print(f"[memoria] Compactados {len(viejos)} recuerdos antiguos en resúmenes temáticos.", flush=True)
    return True
