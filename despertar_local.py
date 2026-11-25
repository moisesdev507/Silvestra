"""Despertar por voz 100 % local mientras Gemini Live está en reposo (0 tokens).

Reutiliza el VAD RMS de ``live_audio`` mediante la puerta local y alimenta solo
las tramas con voz a Vosk con el modelo español ya incluido en el proyecto. No
abre la sesión streaming de Deepgram que usa ``oido.escuchar``.
"""
import json
import os
import re
import threading
import time
import unicodedata

import audio_lock
import live_audio
import puerta_audio_live
import rutas_app

VARIANTES = {"kaya", "kaia", "calla", "caia"}
SEPARADOR = re.compile(r"[^\wáéíóúñü]+", re.UNICODE)
MAX_FRAMES = 80  # ~4 s de audio inicial como máximo
POLL_MS = 10.0   # despacho del wake-word en cuanto aparece en el partial


def contiene_kaya(texto) -> bool:
    """Reconoce 'kaya' y variantes fonéticas habituales en español."""
    plano = unicodedata.normalize("NFD", str(texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    palabras = [p for p in SEPARADOR.split(plano) if p]
    return any(p in VARIANTES for p in palabras)


def ruta_modelo_vosk() -> str:
    return rutas_app.ruta_recurso("modelos", "vosk-model-small-es-0.42")


class EscuchaDespertarLocal:
    """Escucha el wake-word local y entrega el audio inicial al reactivar Live."""

    def __init__(self, al_despertar, ruta_modelo=None, reconocedor=None,
                 reloj=None, crear_stream=None, dormir=None):
        self.al_despertar = al_despertar
        self.ruta_modelo = ruta_modelo or ruta_modelo_vosk()
        self._reconocedor = reconocedor
        self._reloj = reloj or time.monotonic
        self._crear_stream = crear_stream or live_audio.crear_input_stream
        self._dormir = dormir or time.sleep
        self._bloqueo = threading.RLock()
        self._gate = puerta_audio_live.PuertaAudioLive(preroll_ms=240, hangover_ms=400)
        self._vivo = False
        self._hilo = None
        self._stream = None
        self._rate = live_audio.RATE_ENTRADA
        self._audio = []
        self._audio_pendiente = None
        self._post_kaya = []  # captura posterior al nombre, para el handoff a Live
        self._t_deteccion = None
        self._despachado = False

    @property
    def activa(self) -> bool:
        with self._bloqueo:
            return self._vivo

    def _obtener_reconocedor(self):
        if self._reconocedor is not None:
            return self._reconocedor
        if not os.path.isdir(self.ruta_modelo):
            print("[despertar] Falta el modelo Vosk local; wake-word desactivado.", flush=True)
            return None
        try:
            import vosk
            modelo = vosk.Model(self.ruta_modelo)
            self._reconocedor = vosk.KaldiRecognizer(modelo, live_audio.RATE_ENTRADA)
            return self._reconocedor
        except Exception as e:
            print(f"[despertar] No pude cargar Vosk: {e}", flush=True)
            return None

    def iniciar(self) -> bool:
        """Abre el micrófono local solo si el modelo Vosk está disponible."""
        if self.activa or self._obtener_reconocedor() is None:
            return False
        with self._bloqueo:
            self._vivo = True
            self._despachado = False
            self._audio.clear()
            self._audio_pendiente = None
            self._post_kaya.clear()
            self._t_deteccion = None
            self._gate.reiniciar()
        try:
            with audio_lock.bloqueo_portaudio():
                self._stream, self._rate = self._crear_stream(self._callback)
        except Exception as e:
            print(f"[despertar] No pude abrir el micrófono local: {e}", flush=True)
            self.detener()
            return False
        self._hilo = threading.Thread(target=self._vigilar, daemon=True, name="wake-local")
        self._hilo.start()
        print("[despertar] Escucha local 'Kaya' activa (0 tokens Gemini).", flush=True)
        return True

    def detener(self):
        """Cierra el stream desde el hilo monitor, nunca desde el callback PortAudio."""
        with self._bloqueo:
            self._vivo = False
        stream, self._stream = self._stream, None
        if stream is not None:
            self._stream = live_audio.cerrar_stream(stream)
        hilo = self._hilo
        if hilo is not None and hilo is not threading.current_thread() and hilo.is_alive():
            try:
                hilo.join(timeout=0.5)
            except Exception:
                pass
        self._hilo = None

    def _callback(self, indata, frames, time_info, status):
        self.procesar_frame(bytes(indata))

    @staticmethod
    def _texto(raw, clave):
        if not raw:
            return ""
        try:
            return str(json.loads(raw).get(clave, "") or "")
        except Exception:
            return ""

    def procesar_frame(self, pcm: bytes):
        """Alimenta a Vosk solo el audio que el gate local autoriza."""
        if not self.activa or not pcm:
            return
        if self._rate != live_audio.RATE_ENTRADA:
            pcm = live_audio.remuestrear_pcm16_a_16k(pcm, self._rate)
        autorizados, _ = self._gate.procesar(pcm)
        rec = self._reconocedor
        if rec is not None and self._t_deteccion is None:
            texto = self._texto(getattr(rec, "PartialResult", lambda: "")(), "partial")
            if not contiene_kaya(texto) and not self._gate.abierta:
                # Result() solo con el gate cerrado para no resetear Vosk a mitad de frase.
                texto = self._texto(getattr(rec, "Result", lambda: "")(), "text")
            if contiene_kaya(texto):
                with self._bloqueo:
                    self._t_deteccion = self._reloj()
        if not autorizados or rec is None:
            return
        with self._bloqueo:
            self._audio.extend(autorizados)
            if len(self._audio) > MAX_FRAMES:
                del self._audio[:-MAX_FRAMES]
            if self._despachado:
                # Sigue capturando mientras Live conecta: no se pierde lo que
                # el usuario dice después del nombre.
                self._post_kaya.extend(autorizados)
                if len(self._post_kaya) > MAX_FRAMES:
                    del self._post_kaya[:-MAX_FRAMES]
        for frame in autorizados:
            try:
                rec.AcceptWaveForm(frame)
            except Exception:
                return

    def drenar_posteriores(self) -> list:
        """Frames posteriores a 'Kaya' capturados durante la reconexión."""
        with self._bloqueo:
            audio, self._post_kaya = self._post_kaya, []
            return list(audio)

    def _listo_para_despachar(self) -> bool:
        with self._bloqueo:
            return self._t_deteccion is not None and not self._despachado

    def _vigilar(self):
        while self._vivo and not self._despachado:
            self._dormir(POLL_MS / 1000.0)
            if self._listo_para_despachar():
                self._finalizar()
                return

    def _finalizar(self):
        """Despacha al instante y sigue capturando hasta que Live tome el micro."""
        with self._bloqueo:
            if self._despachado:
                return
            self._despachado = True
            audio = list(self._audio)
            self._audio_pendiente = audio
        if callable(self.al_despertar):
            try:
                self.al_despertar("kaya", audio)
            except Exception as e:
                print(f"[despertar] Fallo al reactivar Live: {e}", flush=True)
