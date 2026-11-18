"""Modo estudio para Silvestra: temporizador, examen oral y notas por voz."""
import collections
import datetime
import json
import os
import re
import threading
import unicodedata

import acciones

RUTA_NOTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notas.json")


def _normalizar(texto):
    """Quita tildes y pasa a minúsculas para comparar frases fácilmente."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


class Estudio:
    """Gestiona el temporizador de estudio, los exámenes por voz y las notas."""

    def __init__(self, app):
        self.app = app
        self.eventos = collections.deque()
        self.timer_id = None
        self.modo_examen = False
        self.tema_examen = ""
        self.pregunta_actual = 0
        self.total_preguntas = 5
        self.puntaje = 0
        self.respuesta_esperada = ""
        self.preguntas_hechas = []
        self.evaluando = False

    # ---------- Temporizador de estudio ----------
    def estudiar(self, arg):
        minutos = 25
        if arg:
            m = re.search(r"\b(\d+)\b", str(arg))
            if m and int(m.group(1)) > 0:
                minutos = int(m.group(1))

        if self.timer_id is not None:
            try:
                self.app.cara.root.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

        creador = getattr(self.app.memoria, "creador", "mi creador")
        self.timer_id = self.app.cara.root.after(minutos * 60000, self._fin_estudio)
        self.eventos.append(
            f"¡A darle con todo al estudio, {creador}! Puse el temporizador para {minutos} minutos de enfoque. ¡Tú puedes!"
        )

    def parar_estudio(self):
        if self.timer_id is not None:
            try:
                self.app.cara.root.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None
            self.eventos.append("Listo, cancelé el temporizador de estudio. Tómate un respiro cuando quieras.")
        else:
            self.eventos.append("No tenías ningún temporizador de estudio activo.")

    def _fin_estudio(self):
        if not self.app.puede_hablar_sola():
            self.app.cara.root.after(1000, self._fin_estudio)
            return
        self.timer_id = None
        if self.app.descansando:
            self.app.descansando = False
            self.app.cara.mostrar()
        creador = getattr(self.app.memoria, "creador", "mi creador")
        self.eventos.append(
            f"¡Tiempo cumplido, {creador}! Tremenda sesión de estudio. Te propongo tomarte 5 minutos de descanso."
        )

    # ---------- Examen por voz ----------
    def en_examen(self):
        return self.modo_examen

    def iniciar_examen(self, arg=None):
        tema = (arg or "").strip()
        if not tema or tema.lower() in ("ninguno", "nada", "python"):
            tema = "Python básico"

        self.tema_examen = tema
        self.pregunta_actual = 0
        self.total_preguntas = 5
        self.puntaje = 0
        self.preguntas_hechas = []
        self.respuesta_esperada = ""
        self.evaluando = False
        self.modo_examen = True
        self.app.conversacion = True

        creador = getattr(self.app.memoria, "creador", "mi creador")
        self.eventos.append(
            f"¡Excelente, {creador}! Vamos a hacer un examen de {self.tema_examen}, son 5 preguntas. Dime tu respuesta o di 'salir' para cancelar."
        )
        threading.Thread(target=self._generar_siguiente_pregunta, daemon=True).start()

    def salir_examen(self):
        self.modo_examen = False
        self.evaluando = False
        self.respuesta_esperada = ""

    def responder_examen(self, texto):
        if not self.modo_examen:
            return

        t_norm = _normalizar(texto)
        palabras_salida = ["parar el examen", "para el examen", "parar examen", "ya basta", "basta", "salir", "cancelar examen", "detener examen"]
        if any(p in t_norm for p in palabras_salida):
            self.salir_examen()
            self.eventos.append("Listo, examen detenido. Buen intento por practicar hoy.")
            return

        if self.evaluando:
            self.eventos.append("Dame un segundito, todavía estoy procesando tu respuesta anterior.")
            return

        self.evaluando = True
        threading.Thread(target=self._evaluar_y_continuar, args=(texto,), daemon=True).start()

    def _generar_siguiente_pregunta(self, prefijo=""):
        creador = getattr(self.app.memoria, "creador", "tu creador")
        num = self.pregunta_actual + 1
        previas = "\n".join(f"- {p}" for p in self.preguntas_hechas) or "Ninguna todavía."

        sistema = (
            "Eres Silvestra, una tutora amigable de programación en Panamá. "
            f"Tu estudiante es {creador}, un principiante universitario.\n"
            f"Genera exactamente una pregunta corta de examen oral sobre: '{self.tema_examen}'.\n"
            "La pregunta debe ser conceptual y fácil de responder hablando (sin código largo).\n"
            f"Preguntas ya hechas (NO repitas ninguna):\n{previas}\n\n"
            "Formato OBLIGATORIO (exactamente dos líneas):\n"
            "PREGUNTA: <tu pregunta corta y directa>\n"
            "RESPUESTA_ESPERADA: <explicación breve de lo que se espera>"
        )

        try:
            crudo = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Genera la pregunta número {num}."},
            ])
            pregunta, esperada = self._separar_clave_valor(crudo, "PREGUNTA", "RESPUESTA_ESPERADA")
            if not pregunta:
                raise ValueError("No se pudo extraer la pregunta.")

            self.pregunta_actual = num
            self.preguntas_hechas.append(pregunta)
            self.respuesta_esperada = esperada
            self.evaluando = False

            texto_pregunta = f"Pregunta {self.pregunta_actual} de {self.total_preguntas}: {pregunta}"
            self.eventos.append(f"{prefijo} {texto_pregunta}".strip())
        except Exception:
            self.salir_examen()
            self.eventos.append(
                "Tuve un problema de comunicación con mi cerebro al generar la pregunta. Salgamos del examen por ahora."
            )

    def _evaluar_y_continuar(self, respuesta_usuario):
        sistema = (
            "Eres Silvestra, una tutora amigable de programación en Panamá.\n"
            f"Tema del examen: {self.tema_examen}\n"
            f"Pregunta realizada: {self.preguntas_hechas[-1]}\n"
            f"Respuesta esperada: {self.respuesta_esperada}\n"
            f"Respuesta del estudiante: {respuesta_usuario}\n\n"
            "Tu tarea:\n"
            "1. Evalúa si estuvo BIEN, REGULAR (bien a medias), o MAL.\n"
            "2. En 1 o 2 frases cortas para voz alta, di si estuvo bien o qué faltó, y explica la respuesta correcta.\n"
            "3. En español natural panameño, cercano y cálido. Sin listas, sin asteriscos, sin emojis, sin código largo.\n\n"
            "Formato OBLIGATORIO (exactamente dos líneas):\n"
            "CALIFICACION: <BIEN | REGULAR | MAL>\n"
            "EXPLICACION: <tu explicación en 1 o 2 frases cortas>"
        )

        try:
            crudo = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": "Evalúa la respuesta."},
            ])
            calificacion, explicacion = self._separar_clave_valor(crudo, "CALIFICACION", "EXPLICACION")
            if not explicacion:
                explicacion = crudo.replace("*", "").replace("\n", " ").strip()

            if "BIEN" in calificacion.upper():
                self.puntaje += 1

            if self.pregunta_actual < self.total_preguntas:
                self._generar_siguiente_pregunta(prefijo=explicacion)
            else:
                self.salir_examen()
                if self.puntaje >= 4:
                    animo = "¡Tremendo trabajo! Dominas muy bien este tema."
                elif self.puntaje >= 2:
                    animo = "¡Vas por buen camino! Con un poquito más de práctica lo dominas por completo."
                else:
                    animo = "No te desanimes, de los fallos se aprende. ¡A seguir repasando!"

                self.eventos.append(
                    f"{explicacion} ¡Terminamos el examen! Acertaste {self.puntaje} de {self.total_preguntas}. {animo}"
                )
        except Exception:
            self.salir_examen()
            self.eventos.append(
                "Tuve un problema de comunicación con mi cerebro al evaluar. Dejemos el examen por ahora para no bloquearnos."
            )

    @staticmethod
    def _separar_clave_valor(crudo, clave1, clave2):
        val1, val2 = "", ""
        for linea in (crudo or "").splitlines():
            s = linea.strip()
            if re.match(rf"^{clave1}\s*:\s*", s, re.I):
                val1 = re.sub(rf"^{clave1}\s*:\s*", "", s, flags=re.I).strip(" *\"'")
            elif re.match(rf"^{clave2}\s*:\s*", s, re.I):
                val2 = re.sub(rf"^{clave2}\s*:\s*", "", s, flags=re.I).strip(" *\"'")
        if not val1 and crudo:
            lineas = [l.strip() for l in crudo.splitlines() if l.strip()]
            val1 = lineas[0] if lineas else ""
            val2 = lineas[1] if len(lineas) > 1 else ""
        return val1, val2

    # ---------- Notas por voz ----------
    def anotar_nota(self, arg):
        texto = (arg or "").strip()
        if not texto:
            self.eventos.append("No me dijiste qué anotar en la nota.")
            return

        if ":" in texto:
            materia, contenido = texto.split(":", 1)
        elif "|" in texto:
            materia, contenido = texto.split("|", 1)
        else:
            materia, contenido = "General", texto

        materia = materia.strip().capitalize() or "General"
        contenido = contenido.strip()
        if not contenido:
            self.eventos.append("No me dijiste el contenido de la nota.")
            return

        notas = self._cargar_notas()
        notas.append({
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "materia": materia,
            "texto": contenido,
        })
        self._guardar_notas(notas)
        self.eventos.append(f"Anoté tu nota para {materia}: {contenido}.")

    def leer_notas(self, arg=None):
        notas = self._cargar_notas()
        if not notas:
            self.eventos.append("No tienes ninguna nota guardada todavía.")
            return

        materia_filtro = (arg or "").strip().lower()
        if materia_filtro and materia_filtro not in ("todas", "todo", "ninguna", "nada"):
            filtradas = [n for n in notas if n.get("materia", "").lower() == materia_filtro or materia_filtro in n.get("materia", "").lower()]
            if not filtradas:
                self.eventos.append(f"No encontré notas guardadas para la materia {arg.strip()}.")
                return
            ultimas = filtradas[-5:]
            lineas = [f"Nota {i + 1}: {n['texto']}." for i, n in enumerate(ultimas)]
            self.eventos.append(f"Aquí están tus últimas {len(ultimas)} notas de {ultimas[0]['materia']}: " + " ".join(lineas))
        else:
            ultimas = notas[-5:]
            lineas = [f"En {n['materia']}: {n['texto']}." for n in ultimas]
            self.eventos.append(f"Aquí tienes tus últimas {len(ultimas)} notas guardadas: " + " ".join(lineas))

    @staticmethod
    def _cargar_notas():
        try:
            if os.path.exists(RUTA_NOTAS):
                with open(RUTA_NOTAS, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    @staticmethod
    def _guardar_notas(datos):
        try:
            with open(RUTA_NOTAS, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- Bucle de revisión de voz ----------
    def revisar(self):
        try:
            ocupada = self.app.voz.ocupada()
        except Exception:
            ocupada = False

        if self.eventos and self.app.puede_hablar_sola():
            texto = self.eventos.popleft()
            ms = max(6000, len(texto) * 80)
            self.app.decir(texto, ms)

        self.app.cara.root.after(400, self.revisar)


def instalar(app):
    est = Estudio(app)
    app.estudio = est

    acciones.registrar(
        "estudiar",
        est.estudiar,
        "inicia un temporizador de estudio en minutos (ejemplo: estudiar | 25). Si no especifican tiempo, usa 25.",
        con_texto=True,
    )
    acciones.registrar(
        "parar_estudio",
        est.parar_estudio,
        "cancela o detiene el temporizador de estudio actual.",
    )
    acciones.registrar(
        "examen",
        est.iniciar_examen,
        "inicia un examen oral de programación sobre un tema (ejemplo: examen | Python básico o examen | funciones). Si no dicen tema, usa Python básico.",
        con_texto=True,
    )
    acciones.registrar(
        "anotar_nota",
        est.anotar_nota,
        "guarda una nota de estudio con materia y contenido. Escribe: ACCION: anotar_nota | materia: texto (ejemplo: anotar_nota | Programación: repasar recursión)",
        con_texto=True,
    )
    acciones.registrar(
        "leer_notas",
        est.leer_notas,
        "lee en voz alta las últimas notas guardadas de una materia o de todas (ejemplo: leer_notas | Programación o leer_notas).",
        con_texto=True,
    )

    app.cara.root.after(600, est.revisar)
    return est
