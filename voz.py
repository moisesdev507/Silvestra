import asyncio
import io
import os
import queue
import re
import subprocess
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Voz natural de Microsoft Edge (gratis, necesita internet).
# Si falla o no hay internet, usa la voz de Windows.
VOZ_EDGE = "es-PA-MargaritaNeural"

GUION_WINDOWS = (
    "Add-Type -AssemblyName System.Speech;"
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1;"
    "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
    "$s.Rate = 0;"
    "$s.Speak($env:SILVESTRA_TEXTO)"
)


def dividir_frases(texto):
    """Parte el texto en frases para empezar a hablar con la primera."""
    partes = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", texto.strip()) if p.strip()]
    frases = []
    for p in partes:
        if frases and len(frases[-1]) < 25:  # une frases muy cortas
            frases[-1] += " " + p
        else:
            frases.append(p)
    return frases or [texto]


class Voz:
    def __init__(self):
        self.version = 0
        self._activos = 0
        self.proceso = None
        self.pg = None
        try:
            import pygame

            pygame.mixer.init()
            self.pg = pygame
        except Exception:
            self.pg = None

    def ocupada(self):
        """Devuelve True si hay un flujo de voz activo o el mixer está reproduciendo."""
        if self._activos > 0:
            return True
        if self.pg is not None:
            try:
                if self.pg.mixer.music.get_busy():
                    return True
            except Exception:
                pass
        return False

    def hablar(self, texto, al_terminar=None):
        flujo = self.flujo(al_terminar)
        for frase in dividir_frases(texto):
            flujo.agregar(frase)
        flujo.cerrar()

    def flujo(self, al_terminar=None):
        """Empieza a hablar frase por frase conforme van llegando. Usa .agregar(frase) y al final .cerrar()."""
        self.version += 1
        self._activos += 1
        flujo = Flujo()
        threading.Thread(target=self._hablar, args=(flujo, al_terminar, self.version), daemon=True).start()
        return flujo

    def _parar(self):
        if self.pg is not None:
            try:
                self.pg.mixer.music.stop()
            except Exception:
                pass
        if self.proceso is not None and self.proceso.poll() is None:
            self.proceso.terminate()

    @staticmethod
    def _audio(frase):
        import edge_tts

        async def crear():
            datos = bytearray()
            async for trozo in edge_tts.Communicate(frase, VOZ_EDGE).stream():
                if trozo["type"] == "audio":
                    datos += trozo["data"]
            return bytes(datos)

        return asyncio.run(asyncio.wait_for(crear(), 10))

    def _voz_windows(self, texto, version):
        entorno = os.environ.copy()
        entorno["SILVESTRA_TEXTO"] = texto
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", GUION_WINDOWS],
                env=entorno,
                creationflags=0x08000000,
            )
        except Exception:
            return
        self.proceso = proc
        while proc.poll() is None and version == self.version:
            time.sleep(0.05)

    def _hablar(self, flujo, al_terminar, version):
        try:
            self._parar()
            buzon = queue.Queue()

            def productor():
                while True:
                    frase = flujo.entrada.get()
                    if frase is None or version != self.version:
                        break
                    try:
                        buzon.put((frase, self._audio(frase)))
                    except Exception:
                        buzon.put((frase, None))
                buzon.put(None)

            threading.Thread(target=productor, daemon=True).start()

            while True:
                item = buzon.get()
                if item is None:
                    break
                if version != self.version:
                    return
                frase, audio = item
                if audio and self.pg is not None:
                    try:
                        self.pg.mixer.music.load(io.BytesIO(audio))
                        self.pg.mixer.music.play()
                        while self.pg.mixer.music.get_busy() and version == self.version:
                            time.sleep(0.05)
                        continue
                    except Exception:
                        pass
                self._voz_windows(frase, version)

            if version == self.version and al_terminar:
                al_terminar()
        finally:
            self._activos = max(0, self._activos - 1)


class Flujo:
    """Cola de frases que Voz va diciendo en orden."""

    def __init__(self):
        self.entrada = queue.Queue()

    def agregar(self, frase):
        if frase and frase.strip():
            self.entrada.put(frase.strip())

    def cerrar(self):
        self.entrada.put(None)