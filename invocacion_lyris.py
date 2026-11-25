# Invocación de Kaya: un único pipeline de captura (oido + Silero VAD)
import re
import threading
import time

TIEMPO_ORDEN = 20.0
TIEMPO_RESPUESTA = 12.0
TIEMPO_SEGUIMIENTO = 10.0
DURACION_ECO = 0.4
FUERTES = {"kaya", "kaia", "caya", "kalla", "lyris", "liris", "lirys", "iris", "viris", "silvestra"}
DEBILES = {"calla", "luis", "libres"}
VARIANTES = FUERTES | DEBILES
RELLENO = {"oye", "oiga", "hola", "hey", "bueno", "pues", "entonces", "buenas"}
ORDENES_PARAR_BAILE = (
    "para de bailar", "deja de bailar", "detente", "stop", "para el baile", "deja el baile", "para",
)
_SEPARADOR = re.compile(r"[^\wáéíóúñü]+", re.UNICODE)


def _inicio_captura(app):
    inicio = getattr(getattr(app, "oido", None), "t_captura_inicio", None)
    return inicio if inicio is not None else time.monotonic()


def palabras(texto):
    return [p for p in _SEPARADOR.split(str(texto or "").lower()) if p]


def _extraer_orden_posicional(ps, indice, es_debil=False):
    antes = [p for p in ps[:indice] if p not in VARIANTES]
    despues = [p for p in ps[indice + 1:] if p not in VARIANTES]
    while antes and antes[0] in RELLENO:
        antes.pop(0)
    while despues and despues[0] in RELLENO:
        despues.pop(0)
    if es_debil and not despues:
        return ""
    return " ".join(despues if despues else antes).strip()


def _esta_bailando(app):
    if app is None:
        return False
    try:
        cara = getattr(app, "cara", None)
        gb = getattr(cara, "gestor_baile", None)
        if gb and getattr(gb, "activo", False):
            return True
        import baile_audio
        return bool(getattr(baile_audio, "_AUDIO_ACTIVO", False))
    except Exception:
        return False


def detectar(texto, en_baile=False):
    t_limpio = " ".join(str(texto or "").lower().split()).strip()
    if not t_limpio:
        return False, "", ""

    if en_baile:
        for pb in ORDENES_PARAR_BAILE:
            if t_limpio == pb or t_limpio.startswith(pb + " ") or t_limpio.endswith(" " + pb):
                return True, "baile_stop", "para de bailar"

    ps = palabras(texto)
    if not ps:
        return False, "", ""

    try:
        import identidad_kaya
        ok_k, alias_k, ord_k = identidad_kaya.detectar_invocacion(texto)
        if ok_k:
            return True, alias_k, ord_k
    except Exception:
        pass

    for i, p in enumerate(ps):
        if p in FUERTES:
            return True, p, _extraer_orden_posicional(ps, i)

    if len(ps) == 1 and ps[0] in DEBILES:
        return True, ps[0], ""

    if ps[0] in DEBILES:
        return True, ps[0], _extraer_orden_posicional(ps, 0, es_debil=True)

    if en_baile:
        for i, p in enumerate(ps):
            if p in DEBILES:
                return True, p, _extraer_orden_posicional(ps, i, es_debil=False)

    if ps[-1] in DEBILES:
        indice = len(ps) - 1
        return True, ps[indice], _extraer_orden_posicional(ps, indice, es_debil=True)

    return False, "", ""


def contiene_lyris(texto):
    return detectar(texto)[0]


def extraer_orden(texto):
    return detectar(texto)[2]


def tiene_orden(texto):
    return any(len(p) >= 2 and p not in RELLENO and p not in DEBILES
               for p in palabras(texto))


def texto_valido(texto):
    if not str(texto or "").strip():
        return False
    try:
        import oido_filtro
        return not oido_filtro.es_bucle_degenerado(texto)
    except Exception:
        return True


def permitir_transcripcion(app):
    vd = getattr(app, "voz_dueno", None)
    if vd is None or not getattr(vd, "activa", False):
        return True
    vd.evaluar_entrada_voz("")
    uv = getattr(vd, "ultima_verificacion", {})
    return (not getattr(vd, "modo_solo_dueno", False)
            or bool(uv.get("es_dueno", True)))


def palabra_clave_config():
    try:
        import estado
        return bool(estado.cargar().get("palabra_clave", True))
    except Exception:
        return True


def dueno_verificado(app):
    vd = getattr(app, "voz_dueno", None)
    if vd is None or not getattr(vd, "activa", False):
        return True
    try:
        vd.evaluar_entrada_voz("")
        uv = getattr(vd, "ultima_verificacion", {})
        return bool(uv.get("es_dueno", False))
    except Exception:
        return False


def _sonido(nombre="activar"):
    try:
        import sonidos_ui
        sonidos_ui.reproducir(nombre)
    except Exception:
        pass


def _micro_voz(app):
    try:
        import micro_voz
        micro_voz.sonar_invocacion(app)
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
    if tipo == "oido" and (
            getattr(gestor, "en_turno", False)
            or getattr(gestor, "esperando_orden", False)
            or getattr(gestor, "seguimiento_activo", False)):
        if getattr(gestor, "en_turno", False):
            gestor.atender_oido(texto)
        else:
            gestor._procesar(texto)
        return True
    return False


class GestorInvocacion:

    def __init__(self, app):
        self.app = app
        self.bloqueo = threading.RLock()
        self.activo = True
        self.vivo = False
        self.hilo = None
        self.en_turno = False
        self.esperando_orden = False
        self.limite_orden = 0.0
        self.limite_respuesta = 0.0
        self.palabra_clave = palabra_clave_config()
        self.seguimiento_activo = False
        self.limite_seguimiento = 0.0

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
            self.seguimiento_activo = False
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
            self.seguimiento_activo = False
        self.app.invocacion_ambiental = False
        self._reposo_visual()

    def reanudar(self):
        with self.bloqueo:
            self.activo = True
            self.en_turno = False
            self.esperando_orden = False
            self.seguimiento_activo = False
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
            self.seguimiento_activo = False
            self.limite_seguimiento = 0.0
        self.app.conversacion = False
        self.app.escuchando = False
        self.app.cola.put(("invocacion", "reposo"))

    def _puede_capturar(self):
        with self.bloqueo:
            if self.seguimiento_activo and time.monotonic() >= self.limite_seguimiento:
                self.seguimiento_activo = False
            if self.en_turno and time.monotonic() >= self.limite_respuesta:
                self._reposo()  # cerebro sin respuesta hablada: nunca queda amarillo
                return False
            if not (self.vivo and self.activo and not self.en_turno):
                return False
            if self.esperando_orden and time.monotonic() >= self.limite_orden:
                self._reposo()
                return False
        voz = getattr(self.app, "voz", None)
        if voz is not None and hasattr(voz, "ocupada") and voz.ocupada():
            try:
                import charla_continua
                if not charla_continua.barge_in_habilitado(): return False
            except Exception:
                return False
        return not getattr(self.app, "escuchando", False)

    def _bucle(self):
        while self.vivo:
            if not self._puede_capturar():
                time.sleep(0.15)
                continue
            try:
                texto = self.app.oido.escuchar(corto=True, app=self.app)
                duracion = getattr(self.app.oido, "duracion_ultimo_audio", None)
            except Exception as e:
                print(f"[invocacion] captura: {str(e)[:80]}", flush=True)
                self._reposo()
                time.sleep(0.25)
                continue
            self._procesar(texto, duracion)

    def _procesar(self, texto, duracion=None):
        if duracion is None:
            duracion = getattr(getattr(self.app, "oido", None),
                               "duracion_ultimo_audio", None)
        try:
            corto = duracion is not None and 0.0 < float(duracion) < DURACION_ECO
        except (TypeError, ValueError):
            corto = False
        ahora = time.monotonic()
        with self.bloqueo:
            seguimiento = self.seguimiento_activo
            if seguimiento and ahora >= self.limite_seguimiento:
                self.seguimiento_activo = False
                seguimiento = False
            esperando = self.esperando_orden
            directo = not self.palabra_clave
        if not texto:
            with self.bloqueo:
                if self.esperando_orden and time.monotonic() >= self.limite_orden:
                    self._reposo()
            return
        bailando = _esta_bailando(self.app)
        dispara, variante, orden = detectar(texto, en_baile=bailando)
        if dispara:
            print(f"[invocacion] detectada='{variante}' -> orden='{orden}'", flush=True)
            if bailando and (variante == "baile_stop" or any(p in orden.lower() for p in ("para", "stop", "detente"))):
                try:
                    c = getattr(self.app, "cara", None)
                    if c and getattr(c, "gestor_baile", None):
                        c.gestor_baile.detener(app=self.app)
                    import baile_audio
                    baile_audio.detener_musica_baile()
                except Exception:
                    pass
            if tiene_orden(orden):
                self._iniciar_turno(orden)
            else:
                _micro_voz(self.app)
                with self.bloqueo:
                    self.esperando_orden = True
                    self.limite_orden = _inicio_captura(self.app) + TIEMPO_ORDEN
                self.app.cola.put(("invocacion", "amarillo"))
            return
        if directo and dueno_verificado(self.app):
            if not corto and texto_valido(texto):
                self._iniciar_turno(texto)
            return
        if esperando or seguimiento:
            if corto or len(str(texto).strip()) < 3 or not texto_valido(texto):
                print(f"[invocacion] transcripcion ignorada motivo=eco_o_bucle: '{texto}'", flush=True)
                return
            try:
                import charla_continua
                if charla_continua.es_cierre_conversacion(texto):
                    charla_continua.cerrar_ventana_charla()
                    self._reposo()
                    self.app.decir(charla_continua.respuesta_cierre_amable(), emocion="calida")
                    return
            except Exception:
                pass
            self._iniciar_turno(texto)

    def _iniciar_turno(self, orden):
        with self.bloqueo:
            self.en_turno = True
            self.esperando_orden = False
            self.seguimiento_activo = False
            self.limite_seguimiento = 0.0
        self.app.conversacion = True
        self.app.silencios = 0
        self.limite_respuesta = time.monotonic() + TIEMPO_RESPUESTA
        self.app.cola.put(("invocacion", "amarillo"))
        self.app.cola.put(("oido", orden))

    def atender_evento(self, texto):
        cara = getattr(self.app, "cara", None)
        if texto == "amarillo" and cara is not None:
            cara.poner_escuchando(True)
        elif texto == "reposo":
            self._reposo_visual()

    def atender_oido(self, texto):
        if not texto_valido(texto):
            print(f"[invocacion] orden descartada motivo=bucle_o_vacio: '{texto}'", flush=True)
            self.fin_voz()
            return
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
                print(f"[invocacion] orden descartada motivo=no_dueno: '{texto}'", flush=True)
                self.fin_voz()
                return
        print(f"[invocacion] orden despachada: '{texto}'", flush=True)
        self.app.enviar(texto)

    def fin_voz(self):
        with self.bloqueo:
            if not (self.en_turno or self.esperando_orden):
                return
            respondido = self.en_turno
        self._reposo()
        if respondido:
            with self.bloqueo:
                self.seguimiento_activo = True
                self.limite_seguimiento = time.monotonic() + TIEMPO_SEGUIMIENTO


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
