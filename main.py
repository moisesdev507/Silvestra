import faulthandler
import os
import queue
import sys
import threading
import traceback

# Diario de errores: como corre sin ventana, todo se guarda en silvestra.log
_ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra.log")
try:
    import logging
    _diario = open(_ruta, "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = _diario
    sys.stderr = _diario
    faulthandler.enable(file=_diario, all_threads=True)
    logging.basicConfig(filename=_ruta, encoding="utf-8", level=logging.INFO, force=True)
except Exception:
    _diario = sys.stderr


def _excepthook_sys(exc_type, exc_value, exc_traceback):
    try:
        hilo_nombre = threading.current_thread().name
        print(f"\n[FATAL_CAPTURADO] Excepción no capturada en hilo '{hilo_nombre}':", file=_diario, flush=True)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_diario)
        _diario.flush()
    except Exception:
        pass


def _excepthook_thread(args):
    try:
        hilo_nombre = getattr(args.thread, "name", "Desconocido") if args.thread else "Desconocido"
        print(f"\n[FATAL_CAPTURADO] Excepción no capturada en hilo '{hilo_nombre}':", file=_diario, flush=True)
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=_diario)
        _diario.flush()
    except Exception:
        pass


sys.excepthook = _excepthook_sys
threading.excepthook = _excepthook_thread

from groq import Groq

import acciones
import aprendizaje
import camara
import casa
import config
import control_pc
import conversacion
import correcciones
import cuidado
import diario
import escenario
import estudio
import eventos
import habilidades
import hilos
import hud
import ideas
import iniciativa
import nacimiento
import palabra_clave
import pantalla
import pantalla_remota
import presentacion
import propuestas
import recordatorios
import resumen
import telegram_puente
import voz_dueno
from cara_qt import Cara
from cerebro import Cerebro
from memoria import Memoria
from oido import Oido
from voz import Voz


class Silvestra:
    ultimo_dicho = ""

    def __init__(self):
        self.memoria = Memoria()
        self.cliente = Groq(api_key=config.CLAVE)
        self.cerebro = Cerebro(self.cliente, self.memoria)
        self.voz = Voz()
        self.oido = Oido(self.cliente, self.memoria.vocabulario)
        self.cola = queue.Queue()

        self.conversacion = False
        self.escuchando = False
        self.silencios = 0
        self.descansando = False
        self.pendiente_descanso = False
        self.flujo = None
        self.texto_flujo = ""

        self.cara = Cara(
            self.abrir_chat,
            self.alternar_conversacion,
            self.renacer,
            self.pedir_descanso,
        )
        self.cara._ref_voz = self.voz
        self.cara.poner_viva(bool(self.memoria.nombre))
        presentacion.instalar(self)
        self.casa = casa.instalar(self)
        self.camara = camara.instalar(self)
        self.habilidades = habilidades.instalar(self)
        ideas.instalar(self)
        hilos.instalar(self)
        estudio.instalar(self)
        self.iniciativa = iniciativa.instalar(self)
        self.palabra_clave = palabra_clave.instalar(self)
        pantalla.instalar(self)
        self.hud = hud.instalar(self)
        escenario.instalar(self)
        self.telegram = telegram_puente.instalar(self)
        self.diario = diario.instalar(self)
        self.recordatorios = recordatorios.instalar(self)
        self.cuidado = cuidado.instalar(self)
        self.propuestas = propuestas.instalar(self)
        self.origen_entrada_actual = "chat"
        voz_dueno.instalar(self)
        control_pc.instalar(self)
        correcciones.instalar(self)
        self.resumen = resumen.instalar(self)
        self.aprendizaje = aprendizaje.instalar(self)
        self.pantalla_remota = pantalla_remota.instalar(self)

        self.cara.root.after(100, self.revisar_cola)

        if self.memoria.nombre:
            self.cara.root.after(500, self.saludar)
        else:
            self.cara.root.after(800, self.nacer)

    # ---------- Hablar y acciones ----------
    def puede_hablar_sola(self):
        """True solo si Silvestra no está hablando ni escuchando al usuario."""
        return not self.voz.ocupada() and not self.escuchando

    def decir(self, texto, ms=None, con_voz=True, emocion=None):
        emo = emocion or getattr(self.voz, "deducir_emocion", lambda t: "neutral")(texto)
        if hasattr(self.cara, "fijar_emocion"):
            self.cara.fijar_emocion(emo)
        self.cara.decir(texto, ms, emocion=emo)
        if con_voz:
            self.ultimo_dicho = texto
            self.voz.hablar(texto, lambda: self.cola.put(("fin_voz", None)), emocion=emo)

    def ejecutar(self, linea):
        if not self.puede_hablar_sola():
            self.cara.root.after(300, lambda: self.ejecutar(linea))
            return
        nombre, arg = acciones.interpretar(linea)
        if nombre is None:
            return
        if nombre == "descansar":
            self.pedir_descanso()
            return
        ok, mensaje = acciones.ejecutar(nombre, arg)
        if not ok:
            self.cara.decir(mensaje, 4000)
            if hasattr(self, "propuestas") and self.propuestas:
                self.propuestas.detectar_carencia_accion(nombre)

    # ---------- Descansar y despertar ----------
    def pedir_descanso(self):
        if self.descansando or self.pendiente_descanso:
            return
        self.pendiente_descanso = True
        self.conversacion = False
        self._iniciar_reflexion()
        self.cara.root.after(7000, self.descansar)

    def descansar(self):
        if self.descansando or not self.pendiente_descanso:
            return
        self.pendiente_descanso = False
        self.descansando = True
        self.conversacion = False
        self.cara.ocultar()

    def despertar(self):
        self.descansando = False
        self.cara.mostrar()
        self.conversacion = True
        self.silencios = 0
        self.decir(f"Aquí estoy, {self.memoria.creador}. Dime.", 3000)

    def _iniciar_reflexion(self):
        threading.Thread(target=self.cerebro.reflexionar, args=(hilos,), daemon=True).start()

    # ---------- Delegación de conversación ----------
    def abrir_chat(self):
        conversacion.abrir_chat(self)

    def enviar(self, texto):
        if hasattr(self, "propuestas") and self.propuestas:
            try:
                self.propuestas.detectar_desde_correccion(texto)
            except Exception:
                pass
        conversacion.enviar(self, texto)

    def alternar_conversacion(self):
        conversacion.alternar_conversacion(self)

    def escuchar(self):
        conversacion.escuchar(self)

    def _grabar(self):
        conversacion.grabar(self)

    def _es_eco(self, texto):
        return conversacion.es_eco(self, texto)

    def _dejar_de_escuchar(self):
        conversacion.dejar_de_escuchar(self)

    # ---------- Delegación de nacimiento ----------
    def nacer(self):
        nacimiento.nacer(self)

    def saludar(self):
        nacimiento.saludar(self)

    def renacer(self):
        nacimiento.renacer(self)

    # ---------- Bucle de eventos ----------
    def revisar_cola(self):
        try:
            while not self.cola.empty():
                try:
                    tipo, texto = self.cola.get_nowait()
                except queue.Empty:
                    break
                try:
                    eventos.atender_evento(self, tipo, texto)
                except Exception as e:
                    print(f"[eventos] Error atendiendo evento '{tipo}': {e}", flush=True)
                    traceback.print_exc()
        finally:
            try:
                self.cara.root.after(100, self.revisar_cola)
            except Exception as e:
                print(f"[eventos] Error reprogramando revisar_cola: {e}", flush=True)

    def iniciar(self):
        self.cara.iniciar()


if __name__ == "__main__":
    Silvestra().iniciar()
