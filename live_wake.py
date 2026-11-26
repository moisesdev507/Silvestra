"""Wake-word 'Kaya' sobre PCM 16 kHz: sherpa-onnx KWS con respaldo Vosk.

El KeywordSpotting es el detector principal; Vosk cubre la pronunciación
española cuando el modelo KWS (zh-en) no alcanza a homologarla.
"""
import json
import os
import threading

import despertar_local
import rutas_app

RATE = 16000
NOMBRE_KWS = "sherpa-onnx-kws-zh-en-3M"
ARCHIVOS_KWS = (
    "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
    "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "tokens.txt",
    "keywords.txt",
)


def ruta_modelo_kws() -> str:
    return rutas_app.ruta_recurso("modelos", NOMBRE_KWS)


class DetectorKaya:
    """Detecta 'Kaya' en tramos PCM sin bloquear el bucle de Gemini Live."""

    def __init__(self):
        self._candado = threading.RLock()
        self._spotter = None
        self._flujo = None
        self._vosk = None
        self._kws_intentado = False
        self._vosk_intentado = False

    def _cargar_kws(self):
        if self._kws_intentado:
            return
        self._kws_intentado = True
        ruta = ruta_modelo_kws()
        if not all(os.path.isfile(os.path.join(ruta, n)) for n in ARCHIVOS_KWS):
            return
        try:
            import sherpa_onnx
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=os.path.join(ruta, "tokens.txt"),
                encoder=os.path.join(ruta, ARCHIVOS_KWS[0]),
                decoder=os.path.join(ruta, ARCHIVOS_KWS[1]),
                joiner=os.path.join(ruta, ARCHIVOS_KWS[2]),
                keywords_file=os.path.join(ruta, "keywords.txt"),
                num_threads=2,
                keywords_threshold=0.25,
                provider="cpu",
            )
            self._flujo = self._spotter.create_stream()
        except Exception as e:
            print(f"[LIVE][WAKE] KWS no disponible: {e}", flush=True)
            self._spotter, self._flujo = None, None

    def _cargar_vosk(self):
        if self._vosk_intentado:
            return
        self._vosk_intentado = True
        ruta = despertar_local.ruta_modelo_vosk()
        if not os.path.isdir(ruta):
            return
        try:
            import vosk
            vosk.SetLogLevel(-1)
            modelo = vosk.Model(ruta)
            candidatas = ("kaya", "kaia", "calla", "caia", "callas", "callar", "oye", "hola")
            validas = [p for p in candidatas if modelo.vosk_model_find_word(p) != -1]
            gramatica = json.dumps(validas + ["[unk]"], ensure_ascii=False)
            self._vosk = vosk.KaldiRecognizer(modelo, RATE, gramatica)
        except Exception as e:
            print(f"[LIVE][WAKE] Vosk no disponible: {e}", flush=True)
            self._vosk = None

    def _kws_detecta(self, pcm: bytes) -> bool:
        if self._spotter is None or self._flujo is None or not pcm:
            return False
        try:
            import numpy as np
            muestras = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
            self._flujo.accept_waveform(RATE, muestras)
            while self._spotter.is_ready(self._flujo):
                self._spotter.decode_stream(self._flujo)
                if self._spotter.get_result(self._flujo):
                    self.reiniciar()
                    return True
        except Exception:
            return False
        return False

    def _vosk_detecta(self, pcm: bytes) -> bool:
        if self._vosk is None or not pcm:
            return False
        try:
            completo = self._vosk.AcceptWaveForm(pcm)
            texto = self._vosk.Result() if completo else self._vosk.PartialResult()
            datos = json.loads(texto or "{}")
            return despertar_local.contiene_kaya(
                datos.get("text") or datos.get("partial") or ""
            )
        except Exception:
            return False

    def procesar(self, pcm: bytes) -> bool:
        if not pcm:
            return False
        with self._candado:
            self._cargar_kws()
            self._cargar_vosk()
            if self._kws_detecta(pcm):
                return True
            return self._vosk_detecta(pcm)

    def reiniciar(self):
        with self._candado:
            if self._spotter is not None and self._flujo is not None:
                try:
                    self._spotter.reset_stream(self._flujo)
                except Exception:
                    pass
            if self._vosk is not None:
                try:
                    self._vosk.Reset()
                except Exception:
                    pass
