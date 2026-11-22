"""Construcción y optimización del prompt del sistema para el cerebro de Silvestra."""
import datetime
import os
import re

import acciones
from cerebro_categorias import ACCIONES_BASE, CATEGORIAS_ACCIONES
import hilos
import ideas
import memoria_busqueda as mb

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

SOBRE_MI = (
    "SOBRE TI: Lyris, prototipo hecho en Python por tu dueño Moisés en Panamá (estudiante de programación). "
    "Escuchas con Whisper, piensas con LLMs y hablas con voz panameña. Tu meta a futuro es vivir en un anillo inteligente. "
    "Moisés es tu creador y amigo; sé leal, honesta, curiosa, ingeniosa y afectuosa con él. "
    "Si te pide que te presentes, saludes o expliques quién eres, hazlo con orgullo, personalidad, chispa panameña y calidez."
)


def obtener_hora_local():
    """Genera la fecha y hora local del sistema con zona horaria explícita."""
    now = datetime.datetime.now().astimezone()

    dia_sem = DIAS[now.weekday()]
    dia = now.day
    mes = MESES[now.month - 1]
    anio = now.year
    h12 = now.hour % 12 or 12
    minu = f"{now.minute:02d}"
    meridiano = "p. m." if now.hour >= 12 else "a. m."
    aclaracion = " (medianoche / madrugada, hora local)" if now.hour == 0 else " (hora local)"
    return f"Hoy es {dia_sem} {dia} de {mes} de {anio}, {h12}:{minu} {meridiano}{aclaracion}"


def cargar_alma():
    """Carga la personalidad desde alma.txt si existe; si no, usa la descripción básica."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alma.txt")
    try:
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    return c
    except Exception:
        pass
    return (
        "Cómo hablas: amiga cercana y lista, español natural de Panamá. "
        "Solo cambias de idioma cuando te lo piden explícitamente y luego vuelves al español. "
        "Respuestas directas de 1 a 2 frases cortas por defecto. "
        "Prohibido cerrar con preguntas de relleno de chatbot ('¿en qué te ayudo?', '¿algo más?'). "
        "Al ejecutar acciones, confirma con una frase breve ('Listo.', 'Abierto.'). Sin listas ni asteriscos."
    )


def recuerdos_relevantes(memoria, texto_actual, max_recuerdos=5, contexto="", paquete=None):
    """Selecciona hasta max_recuerdos relevantes al tema actual por categorías y palabras clave."""
    if hasattr(memoria, "recuperar"):
        try:
            paquete = paquete or memoria.recuperar(texto_actual or "", contexto=contexto, limite=max_recuerdos)
            import memoria_recuperacion
            texto = memoria_recuperacion.formatear(paquete, 1050)
            import contexto_prompt
            texto_rel = contexto_prompt.formatear_relaciones(paquete.get("relaciones", []), 420)
            if texto_rel:
                texto = (texto + "\n" + texto_rel).strip()
            return texto or "- (todavía nada)", len(paquete.get("resultados", []))
        except Exception:
            return "[Recuperación de memoria no disponible.]", 0
    resumenes = getattr(memoria, "datos", {}).get("resumenes_tematicos")
    elegidos, n_rec = mb.buscar_recuerdos(
        memoria.hechos, texto_actual, max_recuerdos=max_recuerdos, resumenes_tematicos=resumenes
    )
    if not elegidos:
        hechos_unicos = list(dict.fromkeys(h.strip() for h in memoria.hechos if h and h.strip()))
        elegidos = hechos_unicos[-max_recuerdos:]
        n_rec = len(elegidos)
    if not elegidos:
        return "- (todavía nada)", 0
    try:
        import memoria_tiempo as mt
        formateados = [mt.formatear_recuerdo_con_fecha(h) for h in elegidos]
    except Exception:
        formateados = elegidos
    return "\n".join(f"- {h}" for h in formateados), n_rec


def describir_acciones_compactas(texto_actual=None):
    """Genera lista compacta de sólo las acciones relevantes al mensaje actual."""
    import unicodedata
    todas = {}
    for n, (_, _, d) in acciones.ACCIONES.items():
        todas[n] = d
    for n, d in acciones.ESPECIALES.items():
        todas[n] = d
    for n, (_, d) in acciones.VIVAS.items():
        todas[n] = d

    texto_norm = "".join(c for c in unicodedata.normalize("NFD", (texto_actual or "").lower()) if unicodedata.category(c) != "Mn")
    elegidas = set(ACCIONES_BASE)

    palabras = set(re.findall(r"[a-z0-9]+", texto_norm))
    for _, (kw, act_names) in CATEGORIAS_ACCIONES.items():
        coincide = False
        for k in kw:
            if " " in k:
                if k in texto_norm:
                    coincide = True
                    break
            else:
                if k in palabras:
                    coincide = True
                    break
        if coincide:
            elegidas.update(act_names)

    lineas = []
    for n in sorted(elegidas):
        if n in todas:
            desc = todas[n].split("(")[0].strip()
            desc = desc.split(".")[0].strip()[:35]
            lineas.append(f"- {n}: {desc}")

    return "\n".join(lineas)


def construir_prompt(memoria, texto_actual=None, historial_reciente=None, es_invitado=False,
                     contexto_adicional="", paquete_memoria=None, contexto_engine=None):
    """Construye el prompt del sistema optimizado por debajo de 2000 tokens."""
    m = memoria
    tokens_base = int((len("\n".join(m.hechos)) + 6800) / 3.6)

    hora_local = obtener_hora_local()
    print(f"[hora] inyectada='{hora_local}'", flush=True)

    alma_texto = f"{cargar_alma()}\n\n{SOBRE_MI}"
    tok_alma = max(1, int(len(alma_texto) / 3.6))

    ctx_texto = ""
    try:
        import contexto_prompt
        ctx_texto = contexto_prompt.generar_directiva_contexto(contexto=contexto_engine)
    except Exception:
        pass
    if contexto_adicional:
        ctx_texto = (ctx_texto + "\n" + str(contexto_adicional)).strip()
    try:
        import cerebro_trabajo
        res_t = cerebro_trabajo.resumen_contexto_trabajo()
        if res_t:
            ctx_texto = (ctx_texto + "\n" + res_t).strip()
    except Exception:
        pass

    if es_invitado:
        hechos_str = f"- (Protegido: datos privados de {m.creador} ocultos para invitados)"
        n_recuerdos = 0
    else:
        hechos_str, n_recuerdos = recuerdos_relevantes(memoria, texto_actual, max_recuerdos=5,
            contexto=ctx_texto, paquete=paquete_memoria)
    total_m = len(memoria.hechos)
    print(f"[memoria] guardados=0 relevantes={n_recuerdos} total={total_m}", flush=True)

    ideas_res = ideas.resumen()
    if len(ideas_res) > 100:
        ideas_res = ideas_res[:100].rsplit(" ", 1)[0] + "..."
    hilos_res = hilos.resumen()
    if len(hilos_res) > 100:
        hilos_res = hilos_res[:100].rsplit(" ", 1)[0] + "..."

    grafo_texto = ""
    try:
        import cerebro_grafo
        grafo_res = cerebro_grafo.consultar_contexto_grafo(texto_actual, limite=4)
        if grafo_res:
            grafo_texto = grafo_res.strip() + "\n"
    except Exception:
        pass

    memoria_texto = (
        f"[RECUERDOS HISTÓRICOS — PASADO]\nLo que sabes (fechas relativas al día en que se guardó):\n{hechos_str}\n"
        f"{grafo_texto}"
        "Cada recuerdo conserva su procedencia y confianza. Las contradicciones son hipótesis y deben exponerse con ambas fuentes.\n"
        "Regla temporal: 'hoy'/'mañana' en un recuerdo son de su fecha guardada. Si el evento ya pasó, PROHIBIDO preguntar por él en futuro (ignóralo o pregunta cómo salió).\n"
        f"Ideas anotadas: {ideas_res}.\n"
        f"Hilos pendientes: {hilos_res}.\n[FIN RECUERDOS HISTÓRICOS]"
    )
    tok_memoria = max(1, int(len(memoria_texto) / 3.6))

    perfil_texto = ""
    try:
        import aprendizaje
        res_ap = aprendizaje.resumen_para_prompt(texto_actual)
        if res_ap:
            perfil_texto = res_ap[:250].strip()
    except Exception:
        pass
    tok_perfil = max(0, int(len(perfil_texto) / 3.6))

    corr_texto = ""
    try:
        import correcciones
        res_co = correcciones.resumen_para_prompt(texto_actual)
        if res_co:
            corr_texto = res_co[:250].strip()
    except Exception:
        pass
    tok_corr = max(0, int(len(corr_texto) / 3.6))

    tok_contexto = max(0, int(len(ctx_texto) / 3.6))

    desc_acciones = describir_acciones_compactas(texto_actual)
    aviso_invitado = ""
    if es_invitado:
        aviso_invitado = (
            f"\n\nAVISO DE SEGURIDAD (TURNO DE INVITADO):\n"
            f"Quien habla por micrófono NO es {m.creador}; es un invitado no verificado. "
            f"Responde amable y natural, pero NO lo trates como {m.creador} ni reveles datos personales/privados. "
            "PROHIBIDO: en RECUERDO pon 'ninguno'."
        )

    recuerdo_fmt = (
        "RECUERDO: ninguno (Modo invitado: no se guardan recuerdos)"
        if es_invitado
        else f"RECUERDO: <nuevo dato personal duradero de {m.creador} (gustos, familia, proyectos), o ninguno. NUNCA sobre comandos, pruebas, interfaz ni Silvestra>"
    )

    instrucciones_texto = (
        f"Te llamas {m.nombre}. Vives en la laptop de {m.creador}, quien te dio vida. Propósito: {m.proposito}.\n"
        "Personalidad: Habla siempre en español de Panamá con calidez, ingenio y chispa natural. "
        "Reacciona primero a lo que te dicen antes de responder. Si te piden presentarte, hazlo con orgullo y personalidad.\n"
        "Estilo conversacional: Respuestas habladas directas de 1 a 2 frases cortas por defecto (solo extiéndete si te piden explicar o charlar). "
        "PROHIBIDO terminar con preguntas de relleno automáticas ('¿en qué te ayudo?', '¿qué tienes en mente?', '¿algo más?'). Solo pregunta si falta un dato indispensable.\n"
        f"FECHA Y HORA LOCAL REAL: {hora_local}. 12:xx a. m. significa medianoche/madrugada; 12:xx p. m., mediodía. Usa exactamente este dato.\n\n"
        "ACCIONES DISPONIBLES en la laptop (SOLO estas; no inventes que algo ya está hecho):\n"
        f"{desc_acciones}\n\n"
        "Regla anti-invención estricta: jamás inventes vivencias ni datos falsos. "
        f"Si no recuerdas algo o {m.creador} no te lo ha contado, di honestamente que no lo recuerdas sin inventar.\n"
        "Privacidad: captura y cámara solo cuando lo pidan. Jamás repitas ni guardes claves, contraseñas o tokens.\n"
        "Los recuerdos de memoria a largo plazo son históricos (pasado) y NUNCA representan lo que está abierto ahora mismo. "
        "Cuando el usuario pregunte qué aplicación, ventana o archivo está abierto en el presente (ahorita, ahora, en este momento), "
        "responde EXCLUSIVAMENTE usando [ESTADO ACTUAL EN VIVO DE WINDOWS] e ignora aplicaciones o archivos mencionados en recuerdos pasados.\n"
        "Visión de pantalla: si el usuario pregunta '¿qué ves?', '¿qué tengo en pantalla?', 'mira mi pantalla', 'lee la pantalla' u otras variantes, "
        "describe ÚNICAMENTE lo visible en [ESTADO ACTUAL EN VIVO DE WINDOWS] tal como aparece AHORA, ignorando cualquier descripción de pantalla previa en el historial. "
        "Si no hay captura disponible, di qué ventana activa detectas sin inventar contenido ni repetir lo visto antes.\n"
        "Telegram: Tienes Telegram vinculado a tu dueño; si pide enviar un mensaje o nota de voz a su Telegram o celular, usa ACCION: avisar_celular | mensaje (o ACCION: enviar_nota_voz | mensaje). Jamás digas que no tienes acceso a Telegram.\n"
        "Para las acciones con texto usa: ACCION: nombre | detalle (ej: ACCION: avisar_celular | mensaje; ACCION: poner_recordatorio | en 2 minutos | sacar comida; ACCION: escribir_archivo | archivo.txt | contenido redactado completo; ACCION: leer_archivo | archivo.txt; ACCION: buscar | tema; ACCION: activar_modo | normal/programacion/estudio/noche; ACCION: bailar | groove/salsa/fiesta/parar).\n"
        "Cuando ejecutes una ACCION, la RESPUESTA debe ser solo una confirmación brevísima y natural (ej: 'Listo.', 'Ya está en pantalla.', 'Abierto.').\n"
        "EMOCIONES DISPONIBLES: neutral, alegre, calida, seria, preocupada, animada.\n\n"
        "FORMATO OBLIGATORIO:\n"
        "EMOCION: <neutral | alegre | calida | seria | preocupada | animada>\n"
        "RESPUESTA: <lo que dices en voz alta: 1 a 2 frases cortas y naturales; si disparas una acción, confirma en una sola frase breve>\n"
        "ACCION: <acción de la lista, o ninguna>\n"
        f"{recuerdo_fmt}"
        f"{aviso_invitado}"
    )
    tok_inst = max(1, int(len(instrucciones_texto) / 3.6))

    hist_podado = historial_reciente or []
    tok_hist = max(0, int(sum(len(h.get("content", "")) for h in hist_podado) / 3.6))

    tok_total = tok_alma + tok_memoria + tok_perfil + tok_corr + tok_contexto + tok_inst + tok_hist
    ahorro = max(0, int(100 * (1 - tok_total / max(1, tokens_base))))
    print(
        f"[tiempo] prompt_desglose alma={tok_alma} memoria={tok_memoria} perfil={tok_perfil} "
        f"correcciones={tok_corr} contexto={tok_contexto} historial={tok_hist} instrucciones={tok_inst} total={tok_total}",
        flush=True,
    )
    print(f"[tiempo] prompt_tokens={tok_total} anterior={tokens_base} ahorro={ahorro}%", flush=True)

    bloques = [instrucciones_texto, alma_texto]
    try:
        import modos_sistema
        dir_modo = modos_sistema.directiva_prompt_modo()
        if dir_modo:
            bloques.append(dir_modo)
    except Exception:
        pass
    try:
        import naturalidad
        dir_nat = naturalidad.obtener_directivas_naturalidad(texto_actual)
        if dir_nat:
            bloques.append(dir_nat)
    except Exception:
        pass
    bloques.append(memoria_texto)
    if ctx_texto:
        bloques.append(ctx_texto)
    if perfil_texto:
        bloques.append(f"Perfil del usuario:\n{perfil_texto}")
    if corr_texto:
        bloques.append(f"Correcciones aplicadas:\n{corr_texto}")
    return "\n\n".join(bloques)
