"""Detección local de palabra clave (Silvestra) usando Vosk offline.

Permite despertar a Silvestra cuando está descansando sin gastar cuota de Groq,
y ofrece el modo opcional 'siempre atenta' para encender la conversación por voz.
Utiliza gramática restringida de Kaldi para forzar la detección sobre fonemas afines
y comparte el micrófono de forma segura con oido.py usando su mismo bloqueo.
"""
import atexit
import difflib
import json
import os
import threading
import time
import unicodedata

import acciones
import estado

# Umbral mínimo para coincidencias difusas; las variantes conocidas van por lista exacta.
UMBRAL_RATIO = 0.55
OBJETIVO = "lyris"
OBJETIVO_SECUNDARIO = "silvestra"

# Palabras que nunca deben coincidir con la palabra clave para evitar bucles o falsos disparos
PALABRAS_EXCLUIDAS = {
    "silencio", "silenciosa", "silencioso", "silaba", "silabas",
    "silla", "sillon", "silbido", "silbato", "silicona", "simple",
    "libro", "libros", "libre", "libres",
}

# Lista de palabras candidatas para verificar contra el modelo Vosk
CANDIDATAS = [
    "lyris",
    "liris",
    "iris",
    "lira",
    "liras",
    "lirio",
    "lirios",
    "liria",
    "lyra",
    "sris",
    "srisla",
    "silvestra",
    "silvestre",
    "silvestri",
    "sylvestre",
    "silvia",
    "silvio",
    "silves",
    "silba",
    "vestra",
    "vestre",
    "sil",
    "estra",
]

# Variantes reales que Vosk small-es produce al oír "Lyris" o "Silvestra".
VARIANTES_LYRIS = {
    "lyris", "liris", "iris", "lira", "liras", "lirio", "lirios",
    "liria", "lyra", "sris", "srisla",
}
VARIANTES_SILVESTRA = {
    "silvestra", "silvestre", "silvestri", "sylvestre", "silvia",
    "silvio", "silves", "vestra", "vestre",
}
RUIDO_VOZ = {"unk", "[unk]", "..."}

RUTA_MODELO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "modelos",
    "vosk-model-small-es-0.42",
)


def normalizar(texto):
    """Quita tildes, convierte a minúsculas y elimina caracteres especiales."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _es_candidata(palabra, objetivo, umbral):
    """Acepta solo variantes conocidas o coincidencias difusas estrictas."""
    if not palabra or palabra in RUIDO_VOZ or palabra in PALABRAS_EXCLUIDAS:
        return False
    if len(palabra) < 3:
        return False
    if palabra in VARIANTES_LYRIS or palabra in VARIANTES_SILVESTRA:
        return True
    if palabra == objetivo:
        return True
    if len(palabra) < 4:
        return False
    limite = max(umbral, 0.72)
    return (difflib.SequenceMatcher(None, palabra, objetivo).ratio() >= limite
            or difflib.SequenceMatcher(None, palabra, OBJETIVO_SECUNDARIO).ratio() >= limite)


def coincide_palabra(texto, objetivo=OBJETIVO, umbral=UMBRAL_RATIO):
    """Comprueba si el texto contiene una variante válida del wake-word."""
    if not texto:
        return False
    t = normalizar(texto)
    for c in ",.!?;:-_\"'()[]":
        t = t.replace(c, " ")
    palabras = [p for p in t.split() if p not in RUIDO_VOZ]
    if not palabras:
        return False
    objetivo = normalizar(objetivo)
    for i, p in enumerate(palabras):
        if _es_candidata(p, objetivo, umbral):
            return True
        if i + 1 < len(palabras) and _es_candidata(p + palabras[i + 1], objetivo, umbral):
            return True
    return False


class PalabraClave:
    def __init__(self, app):
        self.app = app
        self.vivo = True
        self.siempre_atenta = estado.cargar().get("palabra_clave", True)
        self.modelo = None
        self.gramatica = ""
        self.palabras_validas = []
        self.hilo = None
        self._log_escuchando = False
        self._cargar_modelo()

    def _cargar_modelo(self):
        try:
            import vosk

            vosk.SetLogLevel(-1)
            if os.path.exists(RUTA_MODELO):
                self.modelo = vosk.Model(RUTA_MODELO)
                # Verificar qué palabras candidatas existen en el vocabulario del modelo
                self.palabras_validas = [
                    p for p in CANDIDATAS if self.modelo.vosk_model_find_word(p) != -1
                ]
                print(
                    f"[vosk] Palabras disponibles en el modelo: {self.palabras_validas}",
                    flush=True,
                )
                # Gramática restringida: solo palabras válidas + [unk]
                self.gramatica = json.dumps(self.palabras_validas + ["[unk]"])
            else:
                print(f"[vosk] Modelo no encontrado en {RUTA_MODELO}", flush=True)
        except Exception as e:
            print("[vosk] Error cargando Vosk:", str(e)[:120], flush=True)

    def activar(self):
        self.siempre_atenta = True
        est = estado.cargar()
        est["palabra_clave"] = True
        estado.guardar(est)
        self.app.cara.decir("Modo siempre atenta activado.", 3000)

    def desactivar(self):
        self.siempre_atenta = False
        est = estado.cargar()
        est["palabra_clave"] = False
        estado.guardar(est)
        self.app.cara.decir("Modo siempre atenta desactivado.", 3000)

    def debe_escuchar(self):
        if getattr(self.app, "voz_silenciada", False):
            return False
        if not self.modelo or not self.vivo:
            return False
        # Escuchar si está descansando O si está en modo siempre_atenta (sin conversación activa)
        descansando = getattr(self.app, "descansando", False)
        conversacion = getattr(self.app, "conversacion", False)
        activo = descansando or (self.siempre_atenta and not conversacion)
        if not activo:
            return False
        # Solo bloqueos reales: voz ocupada o Whisper grabando. El modo estudio NO bloquea.
        voz_ocupada = self.app.voz.ocupada() if hasattr(self.app, "voz") and hasattr(self.app.voz, "ocupada") else False
        if voz_ocupada or getattr(self.app, "escuchando", False):
            return False
        return True

    def iniciar(self):
        if self.hilo is None:
            self.hilo = threading.Thread(target=self._bucle, daemon=True)
            self.hilo.start()

    def _bucle(self):
        try:
            import sounddevice as sd
            import vosk
        except ImportError:
            print("[vosk] Faltan librerías sounddevice o vosk", flush=True)
            return

        rate = 16000
        bloque = int(rate * 0.1)  # 1600 muestras = 100 ms

        while self.vivo:
            if not self.debe_escuchar():
                time.sleep(0.2)
                continue

            # Adquirir el candado del micrófono ANTES de abrir cualquier stream en PortAudio
            adquirido = self.app.oido.bloqueo.acquire(timeout=0.3)
            if not adquirido:
                time.sleep(0.1)
                continue

            try:
                if not self.vivo or not self.debe_escuchar():
                    continue

                if not self._log_escuchando:
                    self._log_escuchando = True
                    print("[palabra_clave] escuchando 'Lyris' (Vosk offline)", flush=True)

                # kaldiRecognizer con gramática restringida
                if self.gramatica:
                    rec = vosk.KaldiRecognizer(self.modelo, rate, self.gramatica)
                else:
                    rec = vosk.KaldiRecognizer(self.modelo, rate)

                with sd.RawInputStream(
                    samplerate=rate, blocksize=bloque, dtype="int16", channels=1
                ) as flujo:
                    while self.vivo and self.debe_escuchar():
                        datos, _ = flujo.read(bloque)
                        if not datos:
                            continue

                        if rec.AcceptWaveform(bytes(datos)):
                            texto = json.loads(rec.Result() or "{}").get("text", "")
                        else:
                            texto = json.loads(rec.PartialResult() or "{}").get("partial", "")
                        texto = (texto or "").strip()
                        if texto and self._coincide(texto):
                            rec.Reset()
                            self._disparar(texto)
                            time.sleep(0.5)
                            break
            except Exception:
                time.sleep(0.2)
            finally:
                self.app.oido.bloqueo.release()
                time.sleep(0.05)

    def _coincide(self, texto):
        if not texto:
            return False
        objetivo = normalizar(self.app.memoria.nombre or OBJETIVO)
        if not objetivo:
            objetivo = OBJETIVO
        return coincide_palabra(texto, objetivo, UMBRAL_RATIO)

    def _disparar(self, texto=""):
        # Solo enviar evento a la cola de la app. NO tocar Qt desde este hilo.
        if getattr(self.app, "voz_silenciada", False):
            return
        if getattr(self.app, "musica_activa", False):
            return
        if self.app.descansando:
            evento = ("despertar", None)
        elif self.siempre_atenta and not self.app.conversacion:
            evento = ("alternar_conversacion", "palabra_clave_vosk")
        else:
            return
        if texto:
            print(f"[palabra_clave] candidata '{texto}' -> {evento[0]}", flush=True)
        self.app.cola.put(evento)

    def detener(self):
        self.vivo = False
        if self.hilo and self.hilo.is_alive() and threading.current_thread() != self.hilo:
            try:
                self.hilo.join(timeout=0.4)
            except Exception:
                pass


def instalar(app):
    detector = PalabraClave(app)
    acciones.registrar(
        "activar_palabra_clave",
        detector.activar,
        "activa el modo siempre atenta para que Silvestra encienda la conversación al escuchar su nombre.",
    )
    acciones.registrar(
        "desactivar_palabra_clave",
        detector.desactivar,
        "desactiva el modo siempre atenta de la palabra clave.",
    )

    # Detener el hilo antes de que Qt destruya su dispatcher
    if hasattr(app, "cara") and hasattr(app.cara, "app"):
        try:
            app.cara.app.aboutToQuit.connect(detector.detener)
        except Exception:
            pass
    atexit.register(detector.detener)

    detector.iniciar()
    return detector
