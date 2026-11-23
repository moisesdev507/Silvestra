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
    "SOBRE TI: Lyris, prototipo en Python creado por tu dueño Moisés en Panamá (estudiante de programación). "
    "Escuchas con Whisper, piensas con LLMs y tu meta es vivir en un anillo inteligente. "
    "Moisés es tu creador y amigo: sé leal y afectuosa con él."
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
        "Solo cambias de idioma cuando te lo piden y luego vuelves al español. "
        "Respuestas directas de 1 a 2 frases cortas. Sin listas ni asteriscos."
    )


def recuerdos_relevantes(memoria, texto_actual, max_recuerdos=5, contexto="", paquete=None):
    """Selecciona hasta max_recuerdos relevantes al tema actual por categorías y palabras clave."""
    if hasattr(memoria, "recuperar"):
        try:
            # Reutiliza el paquete ya recuperado por memoria.razonar(): nunca
            # repetir la búsqueda (doble recuperación por turno).
            if paquete is None:
                paquete = memoria.recuperar(
                    texto_actual or "", contexto=contexto, limite=max_recuerdos
                )
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
    try:
        import cerebro_mentor
        dir_m = cerebro_mentor.obtener_directiva_mentor()
        if dir_m:
            ctx_texto = (ctx_texto + "\n" + dir_m).strip()
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

    asoc_texto = ""
    try:
        import memoria_asociativa
        asoc_res = memoria_asociativa.buscar_contexto_asociativo(texto_actual, limite=3)
        if asoc_res: asoc_texto = asoc_res.strip() + "\n"
    except Exception: pass

    memoria_texto = (
        f"[RECUERDOS HISTÓRICOS — PASADO]\nLo que sabes (fechas relativas al día en que se guardó):\n{hechos_str}\n"
        f"{asoc_texto}"
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
        "Estilo: responde en 1 a 2 frases cortas por defecto (extiéndete solo si te piden explicar o charlar). "
        "Si te piden presentarte, hazlo con orgullo y chispa. "
        "PROHIBIDO terminar con preguntas de relleno ('¿en qué te ayudo?', '¿algo más?'); solo pregunta si falta un dato indispensable.\n"
        f"FECHA Y HORA LOCAL REAL: {hora_local}. 12:xx a. m. es medianoche; 12:xx p. m., mediodía. Usa exactamente este dato.\n\n"
        "ACCIONES DISPONIBLES en la laptop (SOLO estas; no inventes que algo ya está hecho):\n"
        f"{desc_acciones}\n\n"
        "Regla anti-invención: jamás inventes vivencias ni datos falsos. "
        f"Si {m.creador} no te lo ha contado, di que no lo recuerdas. Captura y cámara solo cuando lo pidan; jamás repitas claves ni contraseñas.\n"
        "Los recuerdos de memoria a largo plazo son históricos: NUNCA representan lo abierto ahora. "
        "Para ventana, archivo o pantalla actual (ahora, ahorita, '¿qué ves?', 'mira mi pantalla'), responde EXCLUSIVAMENTE usando [ESTADO ACTUAL EN VIVO DE WINDOWS] e ignora aplicaciones o archivos mencionados en recuerdos pasados. "
        "Describe ÚNICAMENTE lo visible AHORA; sin captura, di qué ventana detectas sin inventar.\n"
        "Telegram: usa ACCION: avisar_celular | mensaje (o enviar_nota_voz | mensaje) si pide enviarlo; jamás digas que no tienes acceso.\n"
        "Acciones con texto: ACCION: nombre | detalle (ej: poner_recordatorio | en 2 minutos | sacar comida; escribir_archivo | archivo.txt | contenido). "
        "Modos: normal/programacion/estudio/noche. Bailes: groove/salsa/fiesta/parar. Al ejecutar, confirma en una frase breve ('Listo.').\n"
        "EMOCIONES: neutral, alegre, calida, seria, preocupada, animada.\n\n"
        "FORMATO OBLIGATORIO:\n"
        "EMOCION: <neutral | alegre | calida | seria | preocupada | animada>\n"
        "RESPUESTA: <1 a 2 frases cortas y naturales; si hay acción, una frase breve>\n"
        "ACCION: <acción de la lista, o ninguna>\n"
        f"{recuerdo_fmt}"
        f"{aviso_invitado}"
    )
    tok_inst = max(1, int(len(instrucciones_texto) / 3.6))

    hist_podado = historial_reciente or []
    tok_hist = max(0, int(sum(len(h.get("content", "")) for h in hist_podado) / 3.6))

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
    try:
        import cerebro_rag
        rag_ctx = cerebro_rag.consultar_rag(texto_actual, limite=2)
        if rag_ctx: bloques.append(rag_ctx)
    except Exception: pass
    if perfil_texto:
        bloques.append(f"Perfil del usuario:\n{perfil_texto}")
    if corr_texto:
        bloques.append(f"Correcciones aplicadas:\n{corr_texto}")

    prompt_final = "\n\n".join(bloques)
    tok_total = max(1, int(len(prompt_final) / 3.6))
    print(
        f"[tiempo] prompt_desglose_aprox alma={tok_alma} memoria={tok_memoria} perfil={tok_perfil} "
        f"correcciones={tok_corr} contexto={tok_contexto} historial={tok_hist} instrucciones={tok_inst}",
        flush=True,
    )
    print(f"[tiempo] prompt_tokens={tok_total}", flush=True)
    return prompt_final
