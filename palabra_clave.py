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

# Umbral de similitud difflib y palabra objetivo (fácilmente modificables)
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


def coincide_palabra(texto, objetivo=OBJETIVO, umbral=UMBRAL_RATIO):
    """Comprueba si alguna palabra reconocida es afín al nombre objetivo, descartando falsos positivos."""
    if not texto:
        return False
    t = normalizar(texto)
    for c in ",.!?;:-_\"'()[]":
        t = t.replace(c, " ")
    palabras = [p for p in t.split() if p not in ("unk", "[unk]")]
    if not palabras:
        return False

    prefijos = ("lyri", "liri", "lyr", "iris", "lira", "liras", "sris", "silvest", "sylvest", "silvi")
    for i, p in enumerate(palabras):
        if p in PALABRAS_EXCLUIDAS:
            continue
        if p.startswith(prefijos):
            return True
        if difflib.SequenceMatcher(None, p, objetivo).ratio() >= umbral:
            return True
        if difflib.SequenceMatcher(None, p, OBJETIVO_SECUNDARIO).ratio() >= umbral:
            return True
        if i + 1 < len(palabras):
            par = p + palabras[i + 1]
            if par in PALABRAS_EXCLUIDAS:
                continue
            if par.startswith(prefijos):
                return True
            if difflib.SequenceMatcher(None, par, objetivo).ratio() >= umbral:
                return True
            if difflib.SequenceMatcher(None, par, OBJETIVO_SECUNDARIO).ratio() >= umbral:
                return True
    return False


class PalabraClave:
    def __init__(self, app):
        self.app = app
        self.vivo = True
        self.siempre_atenta = estado.cargar().get("palabra_clave", False)
        self.modelo = None
        self.gramatica = ""
        self.palabras_validas = []
        self.hilo = None
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
        if not self.modelo or not self.vivo:
            return False
        # Escuchar si está descansando O si está en modo siempre_atenta (sin conversación activa)
        activo = self.app.descansando or (self.siempre_atenta and not self.app.conversacion)
        if not activo:
            return False
        # Detener si la voz está ocupada, si Whisper graba o si no puede hablar sola
        if self.app.voz.ocupada() or self.app.escuchando or not self.app.puede_hablar_sola():
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
        ultimo_log = ""

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

                        detectado = False
                        if rec.AcceptWaveform(bytes(datos)):
                            res = json.loads(rec.Result() or "{}")
                            texto = res.get("text", "").strip()
                            if texto and texto != ultimo_log:
                                print(f"[vosk] final: {texto}", flush=True)
                                ultimo_log = texto
                            if self._coincide(texto):
                                detectado = True
                        else:
                            res = json.loads(rec.PartialResult() or "{}")
                            texto = res.get("partial", "").strip()
                            if texto and texto != ultimo_log:
                                print(f"[vosk] parcial: {texto}", flush=True)
                                ultimo_log = texto
                            if self._coincide(texto):
                                detectado = True

                        if detectado:
                            print(f"[vosk] ¡Palabra clave detectada!: {texto}", flush=True)
                            rec.Reset()
                            ultimo_log = ""
                            self._disparar()
                            time.sleep(0.5)
                            break
            except Exception as e:
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

    def _disparar(self):
        # Solo enviar evento a la cola de la app. NO tocar Qt desde este hilo.
        if getattr(self.app, "musica_activa", False):
            return
        if self.app.descansando:
            self.app.cola.put(("despertar", None))
        elif self.siempre_atenta and not self.app.conversacion:
            self.app.cola.put(("alternar_conversacion", "palabra_clave_vosk"))

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
