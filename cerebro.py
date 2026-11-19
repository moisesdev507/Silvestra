import datetime
import os
import re
import time

import ideas
import hilos
import acciones
from config import MODELOS

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def ahora_texto():
    n = datetime.datetime.now()
    return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month - 1]} de {n.year}, {n.strftime('%H:%M')} (formato 24 horas)"


def separar(texto):
    """Separa RESPUESTA, ACCION, RECUERDO y EMOCION de lo que devuelve el modelo (tolera asteriscos y texto extra)."""
    # Eliminar posibles etiquetas de razonamiento interno de modelos avanzados
    texto = re.sub(r"(?is)<think>.*?</think>", "", texto or "").strip()
    etiqueta = re.compile(r"^[\W_]*(RESPUESTA|ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)[\s*_]*:[\s*_]*(.*)$", re.I)
    # A veces el modelo pega la etiqueta sin salto de línea ("...ayudándote.RESPUESTA: ..."): la separo.
    texto = re.sub(r"\s*\*{0,2}(RESPUESTA|ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)\*{0,2}\s*:", r"\n\1:", texto)
    antes, resp, recuerdo, accion, emocion = [], [], None, None, None
    actual = None
    for linea in texto.splitlines():
        s = linea.strip()
        if not s:
            continue
        m = etiqueta.match(s)
        if m:
            actual = m.group(1).upper().replace("Ó", "O")
            valor = m.group(2).strip()
            if actual == "RESPUESTA":
                resp.append(valor)
            elif actual == "ACCION":
                accion = valor
            elif actual == "EMOCION":
                emocion = valor
            else:
                recuerdo = valor
        elif actual == "RESPUESTA":
            resp.append(s)
        elif actual is None:
            antes.append(s)
    final = " ".join(p for p in (resp if resp else antes) if p).replace("*", "").strip()
    final = re.sub(r"(?i)\bEMOCI[OÓ]N\s*:\s*[a-zA-ZáéíóúÁÉÍÓÚñÑ]+", "", final).strip()
    if recuerdo and recuerdo.lower().strip(" .*") in ("", "ninguno", "ninguna", "nada"):
        recuerdo = None
    if accion:
        accion = accion.strip(" *")
        if accion.lower().strip(" .") in ("", "ninguno", "ninguna", "nada"):
            accion = None

    try:
        from voz import normalizar_emocion, deducir_emocion
        if emocion:
            palabra = emocion.split()[0].strip(" *.,;:-") if emocion.split() else ""
            emocion_final = normalizar_emocion(palabra)
        else:
            emocion_final = deducir_emocion(final)
    except Exception:
        emocion_final = "neutral"

    return final or (texto.strip() if texto else ""), accion, recuerdo, emocion_final

_ETIQ_RESP = re.compile(r"RESPUESTA\s*\*{0,2}\s*:\s*\*{0,2}", re.I)
_ETIQ_FIN = re.compile(r"\s*\*{0,2}(ACCI[OÓ]N|RECUERDO|EMOCI[OÓ]N)\*{0,2}\s*:", re.I)


def _respuesta_parcial(crudo):
    """Lo que lleva dicho después de RESPUESTA: (o None si todavía no llega la etiqueta)."""
    m = _ETIQ_RESP.search(crudo)
    if not m:
        return None
    resto = crudo[m.end():]
    f = _ETIQ_FIN.search(resto)
    if f:
        resto = resto[:f.start()]
    return resto


def _cortar(parcial, emitido, final=False):
    """Saca las frases completas nuevas. Devuelve (frases, nuevo_emitido)."""
    pendiente = parcial[emitido:]
    frases, inicio = [], 0
    for m in re.finditer(r"[.!?…]+\s+", pendiente):
        frag = pendiente[inicio:m.end()].strip()
        if len(frag) >= 25:
            frases.append(frag.replace("*", ""))
            inicio = m.end()
    if final:
        resto = pendiente[inicio:].strip()
        if resto:
            frases.append(resto.replace("*", ""))
        inicio = len(pendiente)
    return frases, emitido + inicio

SOBRE_MI = (
    "SOBRE TI: Silvestra, prototipo hecho en Python por tu dueño Moisés en Panamá (estudiante de programación). "
    "Escuchas con Whisper, piensas con LLMs y hablas con voz panameña. Tu meta a futuro es vivir en un anillo inteligente. "
    "Honesta con tus límites: di con sencillez lo que no sabes, sin inventar ni presumir. "
    "Privacidad: cámara y pantalla solo cuando te lo pidan; jamás guardes ni repitas contraseñas o tokens. "
    "Solo obedeces a tu dueño Moisés. Responde siempre con humor, calidez y naturalidad."
)

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
        "Respuestas cortas de 1 a 3 frases habladas. Sin emojis, listas ni asteriscos."
    )


class Cerebro:
    def __init__(self, cliente, memoria):
        self.cliente = cliente
        self.memoria = memoria
        self.historial = []
        self.modelos = list(MODELOS)
        self.ultima_reflexion = 0.0

    def reiniciar(self):
        self.historial = []

    def _podar_historial(self):
        if len(self.historial) > 16:
            self.historial = self.historial[-10:]

    def _obtener_historial_podado(self):
        """Devuelve los últimos 4 turnos recortando respuestas largas de Silvestra."""
        hist_reciente = self.historial[-4:]
        hist_podado = []
        for h in hist_reciente:
            c = h.get("content", "")
            if h.get("role") == "assistant" and len(c) > 150:
                c = c[:150].rsplit(" ", 1)[0] + "..."
            hist_podado.append({"role": h.get("role"), "content": c})
        return hist_podado

    def _recuerdos_relevantes(self, texto_actual):
        """Selecciona hasta 3 recuerdos relevantes al mensaje actual o los más recientes."""
        hechos_unicos = list(dict.fromkeys(h.strip() for h in self.memoria.hechos if h and h.strip()))
        if not hechos_unicos:
            return "- (todavía nada)"
        if not texto_actual:
            return "\n".join(f"- {h}" for h in hechos_unicos[-3:])

        palabras = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{4,}\b", texto_actual.lower()))
        palabras -= {"hola", "silvestra", "quiero", "puedes", "favor", "dime", "como", "esta", "para", "buenos", "dias"}
        coincidencias = []
        for h in hechos_unicos:
            h_palabras = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{4,}\b", h.lower()))
            score = len(palabras & h_palabras)
            if score > 0:
                coincidencias.append((score, h))

        if coincidencias:
            coincidencias.sort(key=lambda x: x[0], reverse=True)
            elegidos = [h for _, h in coincidencias[:3]]
        else:
            elegidos = hechos_unicos[-3:]
        return "\n".join(f"- {h}" for h in elegidos)

    def instrucciones(self, texto_actual=None):
        m = self.memoria
        tokens_base = int((len("\n".join(m.hechos)) + 6800) / 3.6)

        alma_texto = f"{cargar_alma()}\n\n{SOBRE_MI}"
        tok_alma = max(1, int(len(alma_texto) / 3.6))

        hechos = self._recuerdos_relevantes(texto_actual)
        ideas_res = ideas.resumen()
        if len(ideas_res) > 100:
            ideas_res = ideas_res[:100].rsplit(" ", 1)[0] + "..."
        hilos_res = hilos.resumen()
        if len(hilos_res) > 100:
            hilos_res = hilos_res[:100].rsplit(" ", 1)[0] + "..."

        memoria_texto = (
            f"Lo que sabes:\n{hechos}\n"
            f"Ideas anotadas: {ideas_res}.\n"
            f"Hilos pendientes: {hilos_res}."
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

        todas_acc = (
            [(n, d) for n, (_, _, d) in acciones.ACCIONES.items()]
            + list(acciones.ESPECIALES.items())
            + [(n, d) for n, (_, d) in acciones.VIVAS.items()]
        )
        desc_acciones = "\n".join(f"- {n}: {d.split('(')[0].strip()[:50]}" for n, d in todas_acc)

        instrucciones_texto = (
            f"Te llamas {m.nombre}. Vives en la laptop de {m.creador}, quien te dio vida. Propósito: {m.proposito}.\n"
            "Regla obligatoria de idioma: Habla siempre en español de Panamá. Solo cambia si piden practicar otro idioma explícitamente.\n"
            f"Fecha y hora actual: {ahora_texto()}.\n\n"
            "ACCIONES en la laptop (SOLO estas; nunca inventes que algo ya está hecho):\n"
            f"{desc_acciones}\n\n"
            "Regla anti-invención estricta: Silvestra jamás inventa experiencias, actividades ni días que no ocurrieron. "
            f"Solo habla de lo que está explícitamente en la memoria, en el perfil conversacional o en la conversación actual. Si no sabes algo o {m.creador} no te lo ha contado, dilo con naturalidad sin inventar.\n"
            "Privacidad: captura y cámara solo cuando lo pidan. Jamás repitas ni guardes claves, contraseñas o tokens.\n"
            "Hilos pendientes: retoma máximo uno solo si viene al caso (usa cerrar_pendiente al resolverlo; anotar_pendiente si surge tema).\n"
            "Si no estás segura de una orden, pregunta en vez de actuar. Para buscar: ACCION: buscar | texto.\n"
            "EMOCIONES DISPONIBLES: neutral, alegre, calida, seria, preocupada, animada.\n\n"
            "FORMATO OBLIGATORIO:\n"
            "EMOCION: <neutral | alegre | calida | seria | preocupada | animada>\n"
            "RESPUESTA: <lo que dices en voz alta, breve de 1 a 3 frases>\n"
            "ACCION: <acción de la lista, o ninguna>\n"
            f"RECUERDO: <nuevo dato duradero de {m.creador}, o ninguno>"
        )
        tok_inst = max(1, int(len(instrucciones_texto) / 3.6))

        hist_podado = self._obtener_historial_podado()
        tok_hist = max(0, int(sum(len(h.get("content", "")) for h in hist_podado) / 3.6))

        tok_total = tok_alma + tok_memoria + tok_perfil + tok_corr + tok_inst + tok_hist
        ahorro = max(0, int(100 * (1 - tok_total / max(1, tokens_base))))
        print(
            f"[tiempo] prompt_desglose alma={tok_alma} memoria={tok_memoria} perfil={tok_perfil} "
            f"correcciones={tok_corr} historial={tok_hist} instrucciones={tok_inst} total={tok_total}",
            flush=True,
        )
        print(f"[tiempo] prompt_tokens={tok_total} anterior={tokens_base} ahorro={ahorro}%", flush=True)

        bloques = [instrucciones_texto, alma_texto, memoria_texto]
        if perfil_texto:
            bloques.append(f"Perfil del usuario:\n{perfil_texto}")
        if corr_texto:
            bloques.append(f"Correcciones aplicadas:\n{corr_texto}")
        return "\n\n".join(bloques)

    def _pedir(self, mensajes, tarea="charla"):
        import proveedores
        return proveedores.completar(mensajes, tarea=tarea)

    def responder(self, texto):
        """Devuelve (respuesta, accion, emocion). accion es None o 'nombre' / 'nombre | texto'."""
        import proveedores_cadenas as pc
        self.historial.append({"role": "user", "content": texto})
        prompt = self.instrucciones(texto)
        mensajes = [{"role": "system", "content": prompt}] + self._obtener_historial_podado()
        tarea = pc.clasificar_dificultad(texto)
        try:
            crudo = self._pedir(mensajes, tarea=tarea)
        except Exception as e:
            print(f"[cerebro] Excepción no controlada: {e}. Usando respuesta local.", flush=True)
            crudo = pc.respuesta_emergencia_local()
        respuesta, accion, recuerdo, emocion = separar(crudo)
        if recuerdo:
            self.memoria.recordar(recuerdo)
        self.historial.append({"role": "assistant", "content": respuesta})
        self._podar_historial()
        try:
            import aprendizaje
            aprendizaje.registrar_interaccion(texto, respuesta, emocion)
        except Exception as e:
            print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)
        return respuesta, accion, emocion

    def reflexionar(self, modulo_hilos):
        """Reflexiona sobre la conversación reciente para extraer hechos y temas pendientes."""
        try:
            ultimos = self.historial[-20:]
            intervenciones = sum(1 for m in ultimos if m.get("role") == "user")
            if intervenciones < 4:
                return

            ahora = time.time()
            if ahora - self.ultima_reflexion < 600:
                return
            self.ultima_reflexion = ahora

            charla = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in ultimos)
            sistema = (
                f"Eres {self.memoria.nombre or 'Silvestra'}. Analiza la charla reciente y extrae aprendizajes duraderos.\n"
                "1. Hasta 3 líneas 'HECHO: <dato duradero sobre el usuario (gustos, rutina, proyectos)>'.\n"
                "2. Hasta 2 líneas 'PREGUNTA: <tema de seguimiento para la próxima>'.\n"
                "Sin datos sensibles ni contraseñas. Si no hay nada nuevo: NINGUNO."
            )
            mensajes = [
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Esta fue la conversación reciente:\n{charla}"},
            ]
            crudo = self._pedir(mensajes)
            for linea in (crudo or "").splitlines():
                s = linea.strip()
                if re.match(r"^HECHO\s*:\s*", s, re.I):
                    dato = re.sub(r"^HECHO\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if dato and dato.lower() not in ("ninguno", "ninguna", "nada"):
                        self.memoria.recordar(dato)
                elif re.match(r"^PREGUNTA\s*:\s*", s, re.I):
                    preg = re.sub(r"^PREGUNTA\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if preg and preg.lower() not in ("ninguno", "ninguna", "nada"):
                        modulo_hilos.anotar_pendiente(preg)
        except Exception:
            pass