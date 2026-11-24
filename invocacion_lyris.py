"""Invocación natural de Lyris: un único pipeline de captura (oido + Silero VAD)."""
import re
import threading
import time

TIEMPO_ORDEN = 8.0
VARIANTES = {"lyris", "liris", "iris", "lyra", "liria", "lira", "lirio",
             "lirios", "silvestra", "silvestre"}
RELLENO = {"oye", "oiga", "hola", "hey", "bueno", "pues", "entonces", "buenas"}
_SEPARADOR = re.compile(r"[^\wáéíóúñü]+", re.UNICODE)


def palabras(texto):
    return [p for p in _SEPARADOR.split(str(texto or "").lower()) if p]


def contiene_lyris(texto):
    return any(p in VARIANTES for p in palabras(texto))


def extraer_orden(texto):
    salida = [p for p in palabras(texto) if p not in VARIANTES]
    while salida and salida[0] in RELLENO:
        salida.pop(0)
    return " ".join(salida)


def tiene_orden(texto):
    return any(len(p) >= 2 and p not in RELLENO for p in palabras(texto))


def permitir_transcripcion(app):
    vd = getattr(app, "voz_dueno", None)
    if vd is None or not getattr(vd, "activa", False):
        return True
    vd.evaluar_entrada_voz("")
    uv = getattr(vd, "ultima_verificacion", {})
    return (not getattr(vd, "modo_solo_dueno", False)
            or bool(uv.get("es_dueno", True)))


def _sonido():
    try:
        import sonidos_ui
        sonidos_ui.reproducir("captado")
    except Exception:
        pass


def interceptar(app, tipo, texto):
    gestor = getattr(app, "invocacion", None)
    if gestor is None or not getattr(gestor, "activo", False):
        return False
    if tipo == "invocacion":
        gestor.atender_evento(texto)
        return True
    if tipo in ("fin_voz", "silencio", "fallo") and (
            getattr(gestor, "en_turno", False)
            or getattr(gestor, "esperando_orden", False)):
        gestor.fin_voz()
        return True
    if tipo == "oido" and getattr(gestor, "en_turno", False):
        gestor.atender_oido(texto)
        return True
    return False


class GestorInvocacion:
    """Estado del turno ambiental; nunca toca Qt directamente."""

    def __init__(self, app):
        self.app = app
        self.bloqueo = threading.RLock()
        self.activo = True
        self.vivo = False
        self.hilo = None
        self.en_turno = False
        self.esperando_orden = False
        self.limite_orden = 0.0

    def iniciar(self):
        with self.bloqueo:
            if self.vivo and self.hilo is not None and self.hilo.is_alive():
                return
            self.vivo = True
            self.hilo = threading.Thread(
                target=self._bucle, daemon=True, name="invocacion-lyris")
            self.hilo.start()

    def detener(self):
        with self.bloqueo:
            self.vivo = False
            self.activo = False
            self.en_turno = False
            self.esperando_orden = False
        self.app.invocacion_ambiental = False
        self._reposo_visual()
        hilo = self.hilo
        if hilo is not None and hilo.is_alive() and threading.current_thread() is not hilo:
            try:
                hilo.join(timeout=0.4)
            except Exception:
                pass

    def pausar(self):
        with self.bloqueo:
            self.activo = False
            self.en_turno = False
            self.esperando_orden = False
        self.app.invocacion_ambiental = False
        self._reposo_visual()

    def reanudar(self):
        with self.bloqueo:
            self.activo = True
            self.en_turno = False
            self.esperando_orden = False
        self.app.invocacion_ambiental = True
        self.iniciar()

    def permitir(self):
        if not self.activo:
            return True
        try:
            return permitir_transcripcion(self.app)
        except Exception:
            return True

    def _reposo_visual(self):
        try:
            import conversacion
            conversacion.dejar_de_escuchar(self.app)
        except Exception:
            pass
        cara = getattr(self.app, "cara", None)
        if cara is not None and hasattr(cara, "poner_hablando"):
            cara.poner_hablando(False)

    def _reposo(self):
        with self.bloqueo:
            self.en_turno = False
            self.esperando_orden = False
            self.limite_orden = 0.0
        self.app.conversacion = False
        self.app.escuchando = False
        self.app.cola.put(("invocacion", "reposo"))

    def _puede_capturar(self):
        with self.bloqueo:
            if not (self.vivo and self.activo and not self.en_turno):
                return False
            if self.esperando_orden and time.monotonic() >= self.limite_orden:
                self._reposo()
                return False
        voz = getattr(self.app, "voz", None)
        if voz is not None and hasattr(voz, "ocupada") and voz.ocupada():
            return False
        return not getattr(self.app, "escuchando", False)

    def _bucle(self):
        while self.vivo:
            if not self._puede_capturar():
                time.sleep(0.15)
                continue
            try:
                texto = self.app.oido.escuchar(corto=True, app=self.app)
            except Exception as e:
                print(f"[invocacion] captura: {str(e)[:80]}", flush=True)
                self._reposo()
                time.sleep(0.25)
                continue
            self._procesar(texto)

    def _procesar(self, texto):
        if not texto:
            with self.bloqueo:
                if self.esperando_orden and time.monotonic() >= self.limite_orden:
                    self._reposo()
            return
        if contiene_lyris(texto):
            orden = extraer_orden(texto)
            if tiene_orden(orden):
                self._iniciar_turno(orden)
            else:
                with self.bloqueo:
                    self.esperando_orden = True
                    self.limite_orden = time.monotonic() + TIEMPO_ORDEN
                self.app.cola.put(("invocacion", "amarillo"))
                _sonido()
            return
        with self.bloqueo:
            esperando = self.esperando_orden
        if esperando:
            self._iniciar_turno(texto)

    def _iniciar_turno(self, orden):
        with self.bloqueo:
            self.en_turno = True
            self.esperando_orden = False
        self.app.conversacion = True
        self.app.silencios = 0
        self.app.cola.put(("invocacion", "amarillo"))
        _sonido()
        self.app.cola.put(("oido", orden))

    def atender_evento(self, texto):
        cara = getattr(self.app, "cara", None)
        if texto == "amarillo" and cara is not None:
            cara.poner_escuchando(True)
        elif texto == "reposo":
            self._reposo_visual()

    def atender_oido(self, texto):
        self.app._t_accion_llm = 0
        self.app._flujo_cerrado = False
        self.app.origen_entrada_actual = "microfono"
        self._reposo_visual()
        vd = getattr(self.app, "voz_dueno", None)
        if vd is not None and getattr(vd, "activa", False):
            vd.evaluar_entrada_voz(texto)
            uv = getattr(vd, "ultima_verificacion", {})
            if (getattr(vd, "modo_solo_dueno", False)
                    and not uv.get("es_dueno", True)):
                self.fin_voz()
                return
        self.app.enviar(texto)

    def fin_voz(self):
        with self.bloqueo:
            if not (self.en_turno or self.esperando_orden):
                return
        self._reposo()


def instalar(app):
    gestor = GestorInvocacion(app)
    app.invocacion = gestor
    app.invocacion_ambiental = True
    detector = getattr(app, "palabra_clave", None)
    if detector is not None:
        try:
            detector.detener()
        except Exception:
            pass
    gestor.iniciar()
    print("[invocacion] escucha ambiental activa", flush=True)
    return gestor
