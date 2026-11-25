"""Aplicación gráfica de escritorio para Kaya Gemini Live.

Integra el núcleo conversacional de baja latencia (kaya_live_nucleo.py) con voz
Achernar y tools de PC directamente en el orbe visual flotante de cara_qt.py.
"""
import argparse
import asyncio
import os
import queue
import sys
import threading
import time
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import cara_qt
import kaya_live_nucleo


class PuenteLiveQt:
    """Puente thread-safe entre el bucle asyncio de Kaya Live y la GUI PySide6."""

    def __init__(self, cara: cara_qt.Cara, sesion: kaya_live_nucleo.SesionKayaLive):
        self.cara = cara
        self.sesion = sesion
        self.cola_eventos = queue.Queue(maxsize=1000)
        self.corriendo = True

        self.timer_drenado = QTimer(self.cara)
        self.timer_drenado.timeout.connect(self._drenar_cola)
        self.timer_drenado.start(30)

        self._conectar_callbacks()

    def _conectar_callbacks(self):
        self.sesion.on_estado = self.encolar_estado
        self.sesion.on_nivel_voz = self.encolar_nivel_voz
        self.sesion.on_transcripcion = self.encolar_transcripcion

    def encolar_estado(self, estado: str):
        try:
            self.cola_eventos.put_nowait(("estado", str(estado)))
        except queue.Full:
            pass

    def encolar_nivel_voz(self, nivel: float):
        try:
            self.cola_eventos.put_nowait(("nivel", float(nivel)))
        except queue.Full:
            pass

    def encolar_transcripcion(self, rol: str, texto: str):
        try:
            self.cola_eventos.put_nowait(("texto", (str(rol), str(texto))))
        except queue.Full:
            pass

    def _drenar_cola(self):
        """Drena eventos en el hilo principal de Qt aplicando cambios visuales."""
        procesados = 0
        while not self.cola_eventos.empty() and procesados < 50:
            procesados += 1
            try:
                tipo, datos = self.cola_eventos.get_nowait()
            except queue.Empty:
                break

            if tipo == "estado":
                self._aplicar_estado(datos)
            elif tipo == "nivel":
                self.cara.nivel_volumen = datos
            elif tipo == "texto":
                rol, texto = datos
                if rol == "kaya" and texto:
                    self.cara.decir(texto)

    def _aplicar_estado(self, estado: str):
        if estado == "escuchando":
            self.cara.poner_viva(True)
            self.cara.poner_escuchando(True)
            self.cara.poner_hablando(False)
            self.cara.pensando = False
        elif estado == "hablando":
            self.cara.poner_viva(True)
            self.cara.poner_escuchando(False)
            self.cara.poner_hablando(True)
            self.cara.pensando = False
        elif estado == "pensando":
            self.cara.poner_viva(True)
            self.cara.poner_escuchando(False)
            self.cara.poner_hablando(False)
            self.cara.pensando = True
        elif estado in ("reposo", "error"):
            self.cara.poner_escuchando(False)
            self.cara.poner_hablando(False)
            self.cara.pensando = False
            self.cara.nivel_volumen = 0.0
            if estado == "error":
                self.cara.fijar_emocion("preocupada")
            else:
                self.cara.fijar_emocion("neutral")


class KayaLiveApp:
    """Coordinador de ciclo de vida completo para Kaya Live GUI."""

    def __init__(
        self,
        modelo: str = kaya_live_nucleo.MODELO_DEFECTO,
        voz: str = kaya_live_nucleo.VOZ_DEFECTO,
        silencio: float = kaya_live_nucleo.TIMEOUT_SILENCIO_DEFECTO,
    ):
        self.modelo = modelo
        self.voz = voz
        self.silencio = silencio

        self.sesion: Optional[kaya_live_nucleo.SesionKayaLive] = None
        self.puente: Optional[PuenteLiveQt] = None
        self.cara: Optional[cara_qt.Cara] = None
        self.hilo_async: Optional[threading.Thread] = None
        self.loop_async: Optional[asyncio.AbstractEventLoop] = None
        self._cerrando = False

    def _al_escribir(self):
        if self.cara is None:
            return
        def al_enviar(txt):
            if txt and self.sesion and self.loop_async:
                print(f"[LIVE Chat]: {txt}", flush=True)
                if getattr(self.sesion, "_session", None):
                    from google.genai import types
                    fut = asyncio.run_coroutine_threadsafe(
                        self.sesion._session.send(input=txt, end_of_turn=True),
                        self.loop_async
                    )
        self.cara.abrir_entrada("Hablar con Kaya Live", al_enviar)

    def _al_conversar(self):
        """Pausa o reanuda la interacción por voz al hacer clic en el menú/orbe."""
        if not self.sesion:
            return
        if self.sesion._pausado or self.sesion._evento_parada.is_set():
            self.reanudar_sesion()
        else:
            self.sesion.pausar()

    def _al_renacer(self):
        """Reinicia la sesión en vivo."""
        self.reiniciar_sesion()

    def _al_descansar(self):
        """Pone a Kaya en reposo."""
        if self.sesion:
            self.sesion.pausar()
        if self.cara:
            self.cara.ocultar()

    def reactivar(self):
        """Reactiva la sesión si entró en reposo o silencio."""
        if self.cara and not self.cara.isVisible():
            self.cara.mostrar()
        if self.sesion:
            if self.sesion._evento_parada.is_set():
                self.reiniciar_sesion()
            else:
                self.sesion.reanudar()

    def _hilo_asyncio(self):
        """Bucle de eventos asyncio en hilo secundario daemon."""
        self.loop_async = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop_async)
        try:
            self.loop_async.run_until_complete(self.sesion.ejecutar())
        except Exception as e:
            if not self._cerrando:
                print(f"[LIVE App] Excepción en bucle Live: {e}", flush=True)
        finally:
            try:
                pendientes = asyncio.all_tasks(self.loop_async)
                for t in pendientes:
                    t.cancel()
                if pendientes:
                    self.loop_async.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
                self.loop_async.close()
            except Exception:
                pass

    def iniciar_live_thread(self):
        self.sesion = kaya_live_nucleo.SesionKayaLive(
            modelo=self.modelo,
            voz=self.voz,
            timeout_silencio=self.silencio,
        )
        if self.cara:
            self.puente = PuenteLiveQt(self.cara, self.sesion)

        self.hilo_async = threading.Thread(target=self._hilo_asyncio, name="kaya-live-async", daemon=True)
        self.hilo_async.start()

    def detener(self):
        """Cierre ordenado y sin bloqueos de PortAudio."""
        self._cerrando = True
        if self.puente and self.puente.timer_drenado:
            self.puente.timer_drenado.stop()
        if self.sesion:
            self.sesion.detener()
        if self.loop_async and self.loop_async.is_running():
            self.loop_async.call_soon_threadsafe(self.loop_async.stop)
        if self.cara and self.cara.burbuja:
            try:
                self.cara.burbuja.close()
            except Exception:
                pass

    def reiniciar_sesion(self):
        """Reconecta o reanuda la sesión en caliente sin reiniciar la GUI."""
        self.detener()
        self._cerrando = False
        time.sleep(0.1)
        self.iniciar_live_thread()

    def reanudar_sesion(self):
        if self.sesion and not self.sesion._evento_parada.is_set():
            self.sesion.reanudar()
        else:
            self.reiniciar_sesion()

    def ejecutar(self):
        """Inicializa cara_qt y arranca el bucle Qt."""
        self.cara = cara_qt.Cara(
            al_escribir=self._al_escribir,
            al_conversar=self._al_conversar,
            al_renacer=self._al_renacer,
            al_descansar=self._al_descansar,
        )
        self.cara.setWindowTitle("Kaya Live (Achernar)")
        self.cara.poner_viva(True)

        app_qt = self.cara.app
        app_qt.aboutToQuit.connect(self.detener)

        self.iniciar_live_thread()
        self.cara.iniciar()


def verificar_conexion(modelo: str, voz: str) -> bool:
    """Valida la conexión con Gemini Live API sin abrir ventana Qt."""
    print(f"[LIVE App] Validando conexión Live con modelo='{modelo}' y voz='{voz}'...")
    s = kaya_live_nucleo.SesionKayaLive(modelo=modelo, voz=voz, saludar_al_iniciar=False)
    return asyncio.run(s.ejecutar(solo_verificar=True))


def main():
    parser = argparse.ArgumentParser(description="Kaya Gemini Live GUI con cara_qt y voz Achernar.")
    parser.add_argument("--modelo", default=kaya_live_nucleo.MODELO_DEFECTO)
    parser.add_argument("--voz", default=kaya_live_nucleo.VOZ_DEFECTO)
    parser.add_argument("--silencio", type=float, default=kaya_live_nucleo.TIMEOUT_SILENCIO_DEFECTO)
    parser.add_argument("--verificar", action="store_true", help="Valida conexión e imports sin abrir GUI.")
    args = parser.parse_args()

    if args.verificar:
        ok = verificar_conexion(args.modelo, args.voz)
        sys.exit(0 if ok else 1)

    app = KayaLiveApp(modelo=args.modelo, voz=args.voz, silencio=args.silencio)
    try:
        app.ejecutar()
    except KeyboardInterrupt:
        app.detener()


if __name__ == "__main__":
    main()
