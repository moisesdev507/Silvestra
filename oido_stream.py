"""STT streaming en tiempo real por WebSocket con Deepgram Nova-3.

Transmite frames PCM16 a 16kHz mientras el usuario habla.
Al detectar silencio, cierra el stream y devuelve (texto, duracion) en ~0.15s.
Fallback transparente a None para que oido.py use HTTP POST.
"""
import json
import os
import queue
import threading
import time

import config
import oido_deepgram

URL_WS = "wss://api.deepgram.com/v1/listen?model=nova-3&language=es-419&smart_format=true&encoding=linear16&sample_rate=16000"


class DeepgramStreamer:
    """Gestiona el stream WebSocket en un hilo dedicado con cola sin bloqueo."""

    def __init__(self):
        self.cola = queue.Queue()
        self.texto = ""
        self.duracion = 0.0
        self.listo = threading.Event()
        self.error = False
        self._hilo = None
        self._iniciado = False

    def iniciar(self):
        clave = str(getattr(config, "DEEPGRAM_API_KEY", "")
                    or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
        if not clave or not oido_deepgram.esta_activo():
            self.error = True
            return False

        self._iniciado = True
        self._hilo = threading.Thread(target=self._bucle, args=(clave,), daemon=True)
        self._hilo.start()
        return True

    def alimentar(self, pcm_bytes):
        """Encola datos PCM crudos si el stream está vivo."""
        if not self._iniciado or self.error:
            return
        if pcm_bytes:
            self.cola.put(bytes(pcm_bytes))

    def finalizar(self, timeout=1.5):
        """Cierra el stream y espera la transcripción final."""
        if not self._iniciado or self.error:
            return None
        self.cola.put(None)
        self.listo.wait(timeout=timeout)
        if self.texto and self.texto.strip():
            print(f"[oido_stream] transcrito='{self.texto}'", flush=True)
            return self.texto.strip(), self.duracion
        return None

    def _bucle(self, clave):
        try:
            from websockets.sync.client import connect as ws_connect
        except Exception:
            self.error = True
            self.listo.set()
            return

        headers = {"Authorization": f"Token {clave}"}
        try:
            with ws_connect(URL_WS, additional_headers=headers, open_timeout=2.0) as ws:
                fragmentos = []

                def _receptor():
                    try:
                        for mensaje in ws:
                            if not mensaje:
                                continue
                            if isinstance(mensaje, str):
                                data = json.loads(mensaje)
                            else:
                                data = json.loads(mensaje.decode("utf-8", "ignore"))
                            if data.get("type") == "Results":
                                canales = data.get("channel", {}).get("alternatives", [])
                                if canales:
                                    t = canales[0].get("transcript", "")
                                    if t and t.strip():
                                        fragmentos.append(t.strip())
                            dur = data.get("metadata", {}).get("duration")
                            if dur:
                                self.duracion = float(dur)
                    except Exception:
                        pass

                hilo_rec = threading.Thread(target=_receptor, daemon=True)
                hilo_rec.start()

                while True:
                    bloque = self.cola.get()
                    if bloque is None:
                        try:
                            ws.send(json.dumps({"type": "CloseStream"}))
                        except Exception:
                            pass
                        break
                    try:
                        ws.send(bloque)
                    except Exception:
                        self.error = True
                        break

                hilo_rec.join(timeout=1.2)
                self.texto = " ".join(fragmentos).strip()
        except Exception:
            self.error = True
        finally:
            self.listo.set()


def crear_streamer():
    """Fabrica un streamer e inicia la conexión en fondo si Deepgram está disponible."""
    streamer = DeepgramStreamer()
    if streamer.iniciar():
        return streamer
    return None
