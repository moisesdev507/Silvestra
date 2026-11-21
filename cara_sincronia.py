"""Estado y forma de boca derivados del audio real, sin acceso a Qt."""
import math
import re
import threading
import time


class SincroniaLabial:
    def __init__(self):
        self._lock = threading.RLock()
        self.generacion = 0
        self.reproduciendo_audio = False
        self.nivel_rms = -1.0
        self.patron = (0.45, 0.8, 0.35, 1.0)
        self.inicio = 0.0
        self.cancelada = False

    def preparar(self, generacion, texto):
        grupos = re.findall(r"[aeiouáéíóúü]+", str(texto).lower())
        patron = tuple(min(1.0, 0.4 + min(0.6, len(x) * .16)) for x in grupos)
        with self._lock:
            self.generacion = int(generacion)
            self.reproduciendo_audio = False
            self.nivel_rms = -1.0
            self.patron = patron or (0.55, 0.9, 0.35)
            self.cancelada = False

    def iniciar(self, generacion):
        with self._lock:
            if int(generacion) != self.generacion:
                return False
            self.reproduciendo_audio = True
            self.inicio = time.monotonic()
            return True

    def actualizar(self, generacion, nivel):
        with self._lock:
            if int(generacion) != self.generacion:
                return False
            self.nivel_rms = max(-1.0, min(1.0, float(nivel)))
            return True

    def finalizar(self, generacion, inmediata=False):
        with self._lock:
            if int(generacion) != self.generacion:
                return False
            self.reproduciendo_audio = False
            self.nivel_rms = 0.0
            self.cancelada = bool(inmediata)
            return True

    def cancelar(self):
        with self._lock:
            self.reproduciendo_audio = False
            self.nivel_rms = 0.0
            self.cancelada = True

    def snapshot(self):
        with self._lock:
            return self.generacion, self.reproduciendo_audio, self.nivel_rms, self.patron, self.inicio, self.cancelada

    def callbacks(self, voz, generacion, version, reportar_inicio):
        def inicio():
            with voz._estado_lock:
                if version != voz.version or generacion != voz._generacion_audio:
                    return
                self.iniciar(generacion)
                reportar_inicio()

        def nivel(valor):
            with voz._estado_lock:
                if version != voz.version or generacion != voz._generacion_audio:
                    return
                voz.nivel_volumen = float(valor)
                self.actualizar(generacion, -1.0 if valor < -0.5 else valor)
        return inicio, nivel


def forma_boca(cara, tiempo, ahora=None):
    """Devuelve (visible, apertura vertical, semiancho) con ataque/caída suaves."""
    ahora = time.monotonic() if ahora is None else float(ahora)
    voz = getattr(cara, "_ref_voz", None)
    estado = getattr(voz, "sincronia_labial", None)
    if estado is not None:
        _, activa, rms, patron, inicio, cancelada = estado.snapshot()
    else:
        activa = bool(getattr(cara, "hablando", False))
        rms = float(getattr(cara, "nivel_volumen", -1.0))
        patron = (.45, .8, .35, 1.0, .55)
        inicio, cancelada = ahora, False
    if cancelada:
        cara._boca_suave, cara._boca_tiempo = 0.0, ahora
        return False, 0.0, max(11.0, float(getattr(cara, "val_boca_ancho", 28.0)) * .48)
    previa = float(getattr(cara, "_boca_suave", 0.0))
    ultima = float(getattr(cara, "_boca_tiempo", ahora))
    dt = max(0.0, min(.12, ahora - ultima))
    if activa:
        if rms >= 0:
            # Compresión logarítmica conserva matices y evita saturar con RMS habitual.
            amplitud = math.log1p(9.0 * max(0.0, rms)) / math.log(10.0)
            pulso = amplitud
        else:
            paso = max(0.0, ahora - inicio)
            indice = int(paso / .19) % len(patron)
            fase = (paso % .19) / .19
            pulso = patron[indice] * math.exp(-2.2 * fase) + .12 * patron[(indice + 1) % len(patron)]
        objetivo = 2.8 + 10.0 * max(0.0, min(1.0, pulso))
        factor = 1.0 - math.exp(-dt / .035)  # ataque veloz
    else:
        objetivo = 0.0
        factor = 1.0 - math.exp(-dt / .095)  # caída natural al terminar
    suave = previa + (objetivo - previa) * factor
    cara._boca_suave, cara._boca_tiempo = suave, ahora
    visible = activa or suave > .35
    base = float(getattr(cara, "val_boca_ancho", 28.0)) * .48
    ancho = max(11.0, base * (1.0 + min(.12, suave / 100.0)))
    return visible, suave, ancho
