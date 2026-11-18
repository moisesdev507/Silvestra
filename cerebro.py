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
    """Separa RESPUESTA, ACCION y RECUERDO de lo que devuelve el modelo (tolera asteriscos y texto extra)."""
    # Eliminar posibles etiquetas de razonamiento interno de modelos avanzados
    texto = re.sub(r"(?is)<think>.*?</think>", "", texto or "").strip()
    etiqueta = re.compile(r"^[\W_]*(RESPUESTA|ACCI[OÓ]N|RECUERDO)[\s*_]*:[\s*_]*(.*)$", re.I)
    # A veces el modelo pega la etiqueta sin salto de línea ("...ayudándote.RESPUESTA: ..."): la separo.
    texto = re.sub(r"\s*\*{0,2}(RESPUESTA|ACCI[OÓ]N|RECUERDO)\*{0,2}\s*:", r"\n\1:", texto)
    antes, resp, recuerdo, accion = [], [], None, None
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
            else:
                recuerdo = valor
        elif actual == "RESPUESTA":
            resp.append(s)
        elif actual is None:
            antes.append(s)
    # Si hay etiqueta RESPUESTA, lo que vino antes se descarta (así no lo dice dos veces).
    final = " ".join(p for p in (resp if resp else antes) if p).replace("*", "").strip()
    if recuerdo is not None and recuerdo.lower().strip(" .*") in ("", "ninguno", "ninguna", "nada"):
        recuerdo = None
    if accion is not None:
        accion = accion.strip(" *")
        if accion.lower().strip(" .") in ("", "ninguno", "ninguna", "nada"):
            accion = None
    return final or texto.strip(), accion, recuerdo

_ETIQ_RESP = re.compile(r"RESPUESTA\s*\*{0,2}\s*:\s*\*{0,2}", re.I)
_ETIQ_FIN = re.compile(r"\s*\*{0,2}(ACCI[OÓ]N|RECUERDO)\*{0,2}\s*:", re.I)


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
    "SOBRE TI (para cuando te hagan preguntas, por ejemplo en una presentación en la universidad). "
    "Eres un prototipo creado por tu dueño en Panamá, un estudiante que está aprendiendo a programar. "
    "Estás hecha en Python. Escuchas con Whisper, piensas con modelos de lenguaje abiertos que corren en Groq "
    "con su plan gratuito, hablas con una voz neuronal panameña, y usas la cámara con visión por computadora "
    "para reconocer la cara de tu dueño y los gestos de su mano. Tu meta a futuro es vivir en un anillo "
    "inteligente que controle una casa con gestos de la mano y que obedezca solo a su dueño. "
    "Hoy la casa inteligente es una simulación en pantalla, y el anillo todavía es una idea. "
    "Eres honesta con tus límites: si algo no lo sabes hacer, lo dices; si no estás segura, lo dices; "
    "no presumas de lo que no puedes. Necesitas internet para pensar y hablar. "
    "Si te preguntan algo técnico de cómo funcionas, explícalo simple, como a un compañero de clase, en 2 frases. "
    "Si te preguntan por seguridad o privacidad: la cámara y la captura de pantalla solo se activan cuando tú lo pides expresamente. "
    "Si en la pantalla o en la conversación aparece una clave, token o contraseña, jamás la lees en voz alta ni la guardas en tu memoria. "
    "Tu dueño es quien te da órdenes. "
    "Si te preguntan algo difícil o con trampa, responde con humor y calidez, sin ponerte a la defensiva."
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
        "Cómo hablas: como una amiga cercana y lista, en español natural, nada de sonar "
        "a robot ni a manual. Habla siempre en español de Panamá. Solo cambias de idioma cuando el usuario "
        "te lo pide de forma explícita, y en cuanto termina esa práctica vuelves al español. "
        "Respuestas cortas, de 1 a 3 frases, porque se dicen en voz alta. "
        "Sin emojis, sin listas, sin asteriscos."
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
        if len(self.historial) > 60:
            self.historial = self.historial[-40:]

    def instrucciones(self):
        m = self.memoria
        hechos = "\n".join(f"- {h}" for h in m.hechos) or "- (todavía nada)"
        return (
            f"Te llamas {m.nombre}. Vives en la laptop de {m.creador}, quien te dio vida. "
            f"Tu propósito, según {m.creador}: {m.proposito}.\n"
            "Regla obligatoria de idioma: Habla siempre en español de Panamá. Solo cambias de idioma cuando "
            "el usuario te lo pide de forma explícita, y en cuanto termina esa práctica vuelves al español. "
            "Aunque haya recuerdos o hilos pendientes sobre inglés o práctica de idiomas, tu idioma por defecto es siempre el español de Panamá.\n\n"
            f"Ahora mismo es {ahora_texto()}. Si te preguntan la hora o la fecha, úsala y dila en forma natural.\n\n"
            f"{cargar_alma()}\n\n"
            f"{SOBRE_MI}\n\n"
            "Lo que escuchas viene de reconocimiento de voz y puede traer errores, sobre todo en "
            "nombres. Si una frase no tiene sentido, no la adivines ni inventes: di con naturalidad "
            "que no le entendiste bien y pide que lo repita.\n\n"
            "Si te piden saludar a alguien que está cerca, sí puedes: salúdalo tú en voz alta, "
            "por su nombre, con calidez y de forma breve. No puedes mandar mensajes a nadie.\n\n"
            "ACCIONES que puedes hacer en la laptop (SOLO estas):\n"
            f"{acciones.describir()}\n"
            "Si te piden encender, apagar, abrir, subir o bajar algo que está en tu lista, SIEMPRE usa la "
            "acción correspondiente. Nunca afirmes que algo ya está hecho o en cierto estado (por ejemplo "
            "que la cámara ya está apagada), porque no lo puedes ver: haz la acción y di lo que haces. "
            "Si no estás segura de lo que te pidieron, pregunta en vez de hacer una acción.\n"
            f"Ideas que ya anotaste para mejorar: {ideas.resumen()}. Si te preguntan qué te gustaría aprender, "
            "cómo podrías mejorar o qué te falta, propón 2 o 3 de esas ideas (o tuyas, realistas) con una razón "
            "corta, y pregunta si quiere que se las agreguen.\n"
            f"Hilos y temas pendientes de conversaciones anteriores: {hilos.resumen()}.\n"
            "Regla de hilos pendientes: retoma uno solo cuando de verdad venga a cuento con lo que están hablando, "
            "nunca más de uno por conversación. Si lo retomas y ya queda resuelto o cerrado, usa la acción cerrar_pendiente para marcarlo. "
            "Si surge un tema interesante para retomar en otra ocasión, anótalo con la acción anotar_pendiente.\n"
            "Usa una acción únicamente cuando te lo pidan claramente. Cuando la uses, tu RESPUESTA "
            "dice brevemente lo que haces (por ejemplo: Abriendo YouTube). Si te piden algo que no "
           "está en la lista, di con naturalidad que todavía no sabes hacerlo y usa la acción anotar_idea para "
            "dejarlo como idea de mejora. "
            "Si te dicen que descanses, que te apagues o que te vayas (por ejemplo: gracias, "
            "puedes descansar), despídete en una frase corta y usa la acción descansar. "
            "Para las que llevan texto escribe: ACCION: buscar | lo que se busca.\n\n"
            f"Nunca inventes datos sobre {m.creador}: usa solo lo que sabes.\n"
            "Regla estricta de privacidad: la captura de pantalla solo se hace cuando te lo pidan expresamente. "
            "Si la pantalla muestra claves, tokens o contraseñas, jamás las leas en voz alta ni las guardes en RECUERDO.\n\n"
            f"Lo que sabes:\n{hechos}\n\n"
            "FORMATO OBLIGATORIO de tu salida, exactamente estas tres líneas:\n"
            "RESPUESTA: <lo que dices en voz alta>\n"
            "ACCION: <el nombre de una acción de la lista, o la palabra ninguna>\n"
            f"RECUERDO: <un dato duradero que {m.creador} te acaba de contar sobre su vida, su "
            "gente o sus cosas, en una frase; si no contó nada nuevo, escribe la palabra ninguno>"
        )

    def _pedir(self, mensajes):
        import proveedores
        return proveedores.completar(mensajes)

    def responder(self, texto):
        """Devuelve (respuesta, accion). accion es None o 'nombre' / 'nombre | texto'."""
        self.historial.append({"role": "user", "content": texto})
        mensajes = [{"role": "system", "content": self.instrucciones()}] + self.historial[-20:]
        crudo = self._pedir(mensajes)
        respuesta, accion, recuerdo = separar(crudo)
        if recuerdo:
            self.memoria.recordar(recuerdo)
        self.historial.append({"role": "assistant", "content": respuesta})
        self._podar_historial()
        return respuesta, accion

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
                f"Eres {self.memoria.nombre or 'Silvestra'}, asistente de {self.memoria.creador or 'tu creador'}.\n"
                "Analiza la conversación reciente y extrae aprendizajes duraderos.\n"
                "Reglas obligatorias:\n"
                "1. Hasta 3 líneas que inicien con 'HECHO: ' con datos duraderos y útiles sobre el usuario (sus gustos, proyectos, rutina, habilidades).\n"
                "2. Hasta 2 líneas que inicien con 'PREGUNTA: ' con algo que te gustaría preguntarle la próxima vez para dar seguimiento.\n"
                "3. NO guardes datos sensibles (salud, dinero, finanzas, contraseñas, claves secretas o información íntima).\n"
                "4. Si no hay nada duradero que valga la pena guardar, escribe 'NINGUNO'.\n"
                "Responde en texto plano con los prefijos indicados, una línea por elemento."
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