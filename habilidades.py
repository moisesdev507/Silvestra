"""Habilidades extra de Silvestra: el clima, los recordatorios y la explicación de errores."""
import collections
import json
import os
import re
import threading
import urllib.request

import acciones

# Cambia esto por tu ciudad (latitud y longitud). Ejemplo: Ciudad de Panamá.
CIUDAD = "Ciudad de Panamá"
LAT = 8.98
LON = -79.52

CIELO = {
    0: "el cielo está despejado",
    1: "está mayormente despejado",
    2: "está parcialmente nublado",
    3: "está nublado",
    45: "hay neblina",
    48: "hay neblina",
    51: "hay llovizna",
    53: "hay llovizna",
    55: "hay llovizna",
    61: "hay lluvia ligera",
    63: "hay lluvia",
    65: "hay lluvia fuerte",
    80: "hay chubascos",
    81: "hay chubascos",
    82: "hay chubascos fuertes",
    95: "hay tormenta",
    96: "hay tormenta",
    99: "hay tormenta",
}


class Habilidades:
    def __init__(self, app):
        self.app = app
        self.eventos = collections.deque()

    # ---------- Clima ----------
    def clima(self):
        threading.Thread(target=self._clima, daemon=True).start()

    def _clima(self):
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}&current=temperature_2m,weather_code&timezone=auto"
        )
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                datos = json.load(r)["current"]
            grados = int(round(datos["temperature_2m"]))
            cielo = CIELO.get(int(datos["weather_code"]), "el cielo está variable")
            self.eventos.append(f"En {CIUDAD} hay {grados} grados y {cielo}.")
        except Exception:
            self.eventos.append("No pude revisar el clima. Creo que no tengo internet.")

    # ---------- Recordatorios ----------
    def recordar(self, arg):
        if hasattr(self.app, "recordatorios") and self.app.recordatorios:
            msg = self.app.recordatorios.agregar(arg)
            self.eventos.append(msg)
            return
        m = re.match(r"\s*(\d+)\s*\|?\s*(.*)", arg or "")
        if not m or int(m.group(1)) <= 0:
            self.eventos.append("No te entendí en cuántos minutos. Dímelo otra vez.")
            return
        minutos = int(m.group(1))
        texto = m.group(2).strip() or "lo que me pediste"
        self.app.cara.root.after(minutos * 60000, lambda: self._avisar(texto))

    def _avisar(self, texto):
        if not self.app.puede_hablar_sola():
            self.app.cara.root.after(1000, lambda: self._avisar(texto))
            return
        if self.app.descansando:
            self.app.descansando = False
            self.app.cara.mostrar()
        self.app.decir(f"{self.app.memoria.creador}, te recuerdo: {texto}.", 8000)

    # ---------- Explicar error del log ----------
    def explicar_error(self):
        threading.Thread(target=self._explicar_error, daemon=True).start()

    def _explicar_error(self):
        ruta_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra.log")
        if not os.path.exists(ruta_log):
            self.eventos.append("No encontré ningún archivo de registro silvestra.log para revisar.")
            return

        try:
            with open(ruta_log, "rb") as f:
                f.seek(0, os.SEEK_END)
                tam = f.tell()
                leer_tam = min(tam, 16384)
                f.seek(max(0, tam - leer_tam))
                bloque = f.read().decode("utf-8", errors="replace")
            lineas = bloque.splitlines(keepends=True)
            ultimas = lineas[-30:] if len(lineas) >= 30 else lineas
            texto_log = "".join(ultimas).strip()
        except Exception as e:
            self.eventos.append(f"No pude leer el registro: {str(e)[:80]}.")
            return

        if not texto_log:
            self.eventos.append("El archivo de registro está vacío. No hay ningún error reciente.")
            return

        creador = getattr(self.app.memoria, "creador", "mi creador")
        nombre = getattr(self.app.memoria, "nombre", "Silvestra")
        sistema = (
            f"Eres {nombre}, una asistente de inteligencia artificial creada por {creador} en Panamá. "
            "Tu creador es un estudiante que está aprendiendo a programar. "
            "Revisa las últimas 30 líneas de tu archivo de registro (silvestra.log) y explícale qué error ocurrió.\n"
            "Reglas obligatorias:\n"
            "1. Habla en español natural panameño, tono amable, sencillo y cercano.\n"
            "2. Explica en 1 a 3 frases cortas qué falló y en qué parte o archivo, si se nota.\n"
            "3. No uses tecnicismos complicados, ni código largo, ni asteriscos, ni comillas, ni listas, ni emojis.\n"
            "4. Si las líneas del registro NO muestran ningún error ni excepción (por ejemplo, solo líneas normales de tiempo o inicio), "
            "di claramente que todo se ve en orden y que no hay errores recientes en el registro."
        )

        try:
            explicacion = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Últimas líneas de silvestra.log:\n\n{texto_log}"},
            ])
            limpio = explicacion.replace("*", "").replace("\n", " ").strip()
            self.eventos.append(limpio)
        except Exception:
            # Respaldo sin internet o si falla la API
            linea_err = next(
                (l.strip() for l in reversed(ultimas) if "Error" in l or "Exception" in l or "Traceback" in l),
                None,
            )
            if linea_err:
                self.eventos.append(f"No pude conectar con mi cerebro, pero en el registro vi este fallo: {linea_err[:100]}.")
            else:
                self.eventos.append("No pude consultar a mi cerebro y a simple vista no veo ningún error en el registro.")

    # ---------- Hilo principal ----------
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
    h = Habilidades(app)
    try:
        import correo_unificado
        correo_unificado.registrar_acciones()
    except Exception:
        pass
    acciones.registrar(
        "clima",
        h.clima,
        "revisa el clima de ahora (tú NO sabes el clima: solo di que vas a revisarlo y no inventes datos)",
    )
    acciones.registrar(
        "recordar",
        h.recordar,
        "te avisa de algo dentro de unos minutos. Escribe: ACCION: recordar | minutos | qué recordar "
        "(ejemplo: recordar | 10 | tomar agua)",
        con_texto=True,
    )
    acciones.registrar(
        "explicar_error",
        h.explicar_error,
        "revisa las últimas líneas de silvestra.log para ver qué error ocurrió y explicarlo en voz alta "
        "(tú NO sabes cuál es el error: solo di una frase corta avisando que vas a revisar el registro y no inventes errores; "
        "úsala cuando pregunten qué error tienes, qué falló, cuál es el error o por qué hubo un fallo)",
    )
    try:
        import herramientas_cerebro as hc
        acciones.registrar(
            "consultar_conocimiento",
            hc.accion_consultar,
            "busca en documentos locales y en el grafo de conocimiento; escribe: "
            "consultar_conocimiento | qué buscas | ruta=opcional",
            con_texto=True,
        )
        acciones.registrar(
            "resumir_enlace",
            lambda texto: hc.accion_resumir(texto, app),
            "resume una página web o un video de YouTube; escribe: resumir_enlace | https://...",
            con_texto=True,
        )
        acciones.registrar(
            "plan_complejo",
            lambda texto: hc.ejecutar_plan_complejo(texto, app),
            "investiga y ejecuta en segundo plano una tarea de varios pasos; "
            "escribe: plan_complejo | qué quieres investigar o coordinar",
            con_texto=True,
        )
    except Exception:
        pass
    app.cara.root.after(500, h.revisar)
    return h