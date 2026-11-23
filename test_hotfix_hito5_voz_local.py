"""Regresión Hito 5: Kokoro local con fallback y barge-in solo ante orden clara."""
import io
import os
import queue
import sys
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

import config
import oido
import voz
import voz_local


class TtsFalso:
    def __init__(self):
        self.ultimo = None

    def generate(self, texto, speed=1.0):
        self.ultimo = (texto, speed)
        return SimpleNamespace(samples=[0.0, 0.25, -0.25], sample_rate=24000)


class ReconocedorFalso:
    def __init__(self, parcial):
        self.parcial = parcial
        self.aceptados = 0

    def AcceptWaveform(self, _datos):
        self.aceptados += 1

    def PartialResult(self):
        return '{"partial":"%s"}' % self.parcial


class VozFalsa:
    def __init__(self, ocupada=True):
        self._ocupada = ocupada
        self.paradas = []

    def ocupada(self):
        return self._ocupada

    def detener(self, motivo=None):
        self.paradas.append(motivo)


class CommunicateFalso:
    def __init__(self, *_args, **_kw):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"EDGE_AUDIO"}
        yield {"type": "word", "data": "ignorar"}


class TestHotfixHito5VozLocal(unittest.TestCase):
    def test_config_kokoro_recibe_lexicon_y_data_dir(self):
        captura = {}

        class KokoroCfg:
            def __init__(self, **kw):
                captura["kokoro"] = kw

        class ModeloCfg:
            def __init__(self, kokoro):
                captura["modelo"] = kokoro

        class TtsCfg:
            def __init__(self, model):
                captura["tts_model"] = model

        sherpa = SimpleNamespace(
            OfflineTtsKokoroModelConfig=KokoroCfg,
            OfflineTtsModelConfig=ModeloCfg,
            OfflineTtsConfig=TtsCfg,
            OfflineTts=lambda _cfg: TtsFalso(),
        )
        lexico = "modelos/kokoro/lexicon-us-en.txt,modelos/kokoro/lexicon-gb-en.txt"
        rutas = ("modelos/kokoro/model.int8.onnx", "modelos/kokoro/voices.bin",
                 "modelos/kokoro/tokens.txt", lexico,
                 "modelos/kokoro/espeak-ng-data")
        with patch.object(voz_local, "_archivos", lambda: rutas), \
             patch.dict(sys.modules, {"sherpa_onnx": sherpa}), \
             patch.object(voz_local, "_TTS", None), \
             patch.object(voz_local, "_FALLADO", False):
            self.assertIsNotNone(voz_local._cargar())

        self.assertEqual(captura["kokoro"]["lexicon"], lexico)
        self.assertEqual(captura["kokoro"]["data_dir"],
                         "modelos/kokoro/espeak-ng-data")
        self.assertIsInstance(captura["modelo"], KokoroCfg)
        self.assertIsInstance(captura["tts_model"], ModeloCfg)

    def test_resolucion_real_de_lexicons_y_data_dir(self):
        if not os.path.isdir("modelos/kokoro-int8-multi-lang-v1_0"):
            self.skipTest("modelo Kokoro no descargado")
        rutas = voz_local._archivos()
        self.assertIsNotNone(rutas)
        modelo, _voces, _tokens, lexico, dato = rutas
        self.assertTrue(modelo.endswith("model.int8.onnx"))
        self.assertIn("lexicon-us-en.txt", lexico)
        self.assertIn("lexicon-gb-en.txt", lexico)
        self.assertTrue(dato.endswith("espeak-ng-data"))

    def test_sintesis_real_devuelve_wav_valido(self):
        if not os.path.isdir("modelos/kokoro-int8-multi-lang-v1_0"):
            self.skipTest("modelo Kokoro no descargado")
        audio = voz_local.sintetizar_wav("Hola")
        self.assertTrue(audio and audio.startswith(b"RIFF"))
        with wave.open(io.BytesIO(audio), "rb") as archivo:
            self.assertEqual(archivo.getnchannels(), 1)
            self.assertGreater(archivo.getnframes(), 0)

    def test_wav_valido_y_mapeo_de_emocion(self):
        wav = voz_local.samples_a_wav([0.0, 0.5, -0.5, 1.0, -1.0], 22050)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav[:16])
        with wave.open(io.BytesIO(wav), "rb") as archivo:
            self.assertEqual(archivo.getnchannels(), 1)
            self.assertEqual(archivo.getsampwidth(), 2)
            self.assertEqual(archivo.getframerate(), 22050)
            self.assertEqual(archivo.getnframes(), 5)
        self.assertEqual(voz_local.velocidad_para("animada"), 1.08)
        self.assertEqual(voz_local.velocidad_para("calmada"), 0.92)
        self.assertEqual(voz_local.velocidad_para("neutral"), 1.0)
        self.assertEqual(voz_local.velocidad_para("emocion_inventada"), 1.0)

    def test_sintesis_local_recorta_texto_y_pasa_speed(self):
        tts = TtsFalso()
        with patch.object(voz_local, "_cargar", lambda: tts):
            audio = voz_local.sintetizar_wav("  hola  Lyris  ", "animada")
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(tts.ultimo, ("hola Lyris", 1.08))

    def test_sin_modelo_devuelve_none_y_voz_cae_a_edge_tts(self):
        with patch.object(voz_local, "_cargar", lambda: None):
            self.assertIsNone(voz_local.sintetizar_wav("hola"))

        frase = "frase unica hito5 " + str(id(self))
        falso = SimpleNamespace(Communicate=CommunicateFalso)
        with patch.dict(sys.modules, {"edge_tts": falso}), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None), \
             patch("voz_cache.guardar_audio_cache", lambda *_a: None), \
             patch.object(voz_local, "sintetizar_wav", lambda *_a: None):
            self.assertEqual(voz.Voz._audio(frase, "neutral"), b"EDGE_AUDIO")

    def test_voz_prefiere_kokoro_cuando_devuelve_audio(self):
        frase = "frase kokoro hito5 " + str(id(self))
        with patch.object(voz_local, "sintetizar_wav", lambda *_a: b"KOKORO_WAV"), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None):
            self.assertEqual(voz.Voz._audio(frase, "alegre"), b"KOKORO_WAV")

    def test_barge_in_ignora_ruido_y_exige_voz_activa(self):
        datos = SimpleNamespace(tobytes=lambda: b"\x00\x00")
        corte = ("espera", "para", "silencio")
        for ruido in ("", "   ", "??!!", "mmm", "a"):
            app = SimpleNamespace(voz=VozFalsa(), cola=queue.Queue())
            rec = ReconocedorFalso(ruido)
            self.assertFalse(oido._barge_in(app, datos, corte, rec))
            self.assertTrue(app.cola.empty())
            self.assertEqual(app.voz.paradas, [])

        app = SimpleNamespace(voz=VozFalsa(ocupada=False), cola=queue.Queue())
        self.assertFalse(oido._barge_in(app, datos, corte, ReconocedorFalso("espera")))
        self.assertTrue(app.cola.empty())

    def test_barge_in_ordena_detener_y_emite_interrupcion(self):
        datos = SimpleNamespace(tobytes=lambda: b"\x01\x02")
        app = SimpleNamespace(voz=VozFalsa(), cola=queue.Queue())
        rec = ReconocedorFalso("   espera  ")
        self.assertTrue(oido._barge_in(app, datos, ("espera", "para"), rec))
        self.assertEqual(rec.aceptados, 1)
        self.assertEqual(len(app.voz.paradas), 1)
        self.assertEqual(app.cola.get_nowait(), ("interrupcion", "comando"))

    def test_flag_de_barge_in_por_config_o_entorno(self):
        with patch.object(config, "BARGE_IN_ACTIVO", False), \
             patch.dict(os.environ, {"LYRIS_BARGE_IN": "0"}):
            self.assertFalse(oido._barge_in_habilitado())
        with patch.object(config, "BARGE_IN_ACTIVO", False), \
             patch.dict(os.environ, {"LYRIS_BARGE_IN": "1"}):
            self.assertTrue(oido._barge_in_habilitado())
        with patch.object(config, "BARGE_IN_ACTIVO", True), \
             patch.dict(os.environ, {"LYRIS_BARGE_IN": "0"}):
            self.assertTrue(oido._barge_in_habilitado())


if __name__ == "__main__":
    unittest.main()
