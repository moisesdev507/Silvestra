"""Regresión Hito 5: Piper VITS local, prioridad edge-tts y barge-in."""
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
import bajar_modelos
import voz
import voz_fonemas
import voz_local


class TtsFalso:
    def __init__(self):
        self.ultimo = None

    def generate(self, texto, config=None, speed=1.0):
        self.ultimo = (texto, getattr(config, "speed", speed))
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
    def test_g2p_español_y_descarga_piper(self):
        self.assertEqual(''.join(chr(c) for c in
                                 voz_fonemas.fonemas_es('hola que tal')[0]),
                         'ola ke tal ')
        self.assertTrue(all("vits-piper-es_" in u for u in bajar_modelos.PIPER_URLS))
        self.assertIs(bajar_modelos.bajar_kokoro, bajar_modelos.bajar_piper)

    def test_config_vits_recibe_model_tokens_y_data_dir(self):
        captura = {}

        class VitsCfg:
            def __init__(self, **kw):
                captura["vits"] = kw

        class ModeloCfg:
            def __init__(self, vits):
                captura["modelo"] = vits

        class TtsCfg:
            def __init__(self, model):
                captura["tts_model"] = model

        sherpa = SimpleNamespace(
            OfflineTtsVitsModelConfig=VitsCfg,
            OfflineTtsModelConfig=ModeloCfg,
            OfflineTtsConfig=TtsCfg,
            OfflineTts=lambda _cfg: TtsFalso(),
        )
        rutas = ("modelos/vits-piper-es_MX-claude-high/voz.onnx",
                 "modelos/vits-piper-es_MX-claude-high/tokens.txt",
                 "modelos/vits-piper-es_MX-claude-high/espeak-ng-data")
        with patch.object(voz_local, "_archivos", lambda: rutas), \
             patch.dict(sys.modules, {"sherpa_onnx": sherpa}), \
             patch.object(voz_local, "_TTS", None), \
             patch.object(voz_local, "_FALLADO", False):
            self.assertIsNotNone(voz_local._cargar())

        self.assertEqual(captura["vits"]["model"], rutas[0])
        self.assertEqual(captura["vits"]["tokens"], rutas[1])
        self.assertEqual(captura["vits"]["data_dir"], rutas[2])
        self.assertIsInstance(captura["modelo"], VitsCfg)
        self.assertIsInstance(captura["tts_model"], ModeloCfg)

    def test_resolucion_real_de_piper_vits(self):
        if not voz_local._carpeta_modelo():
            self.skipTest("modelo Piper VITS no descargado")
        rutas = voz_local._archivos()
        self.assertIsNotNone(rutas)
        modelo, tokens, dato = rutas
        self.assertTrue(modelo.endswith(".onnx"))
        self.assertTrue(tokens.endswith("tokens.txt"))
        self.assertTrue(dato.endswith("espeak-ng-data"))

    def test_sintesis_real_devuelve_wav_valido(self):
        if not voz_local._carpeta_modelo():
            self.skipTest("modelo Piper VITS no descargado")
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
        self.assertEqual(tts.ultimo[0], "hola Lyris")
        self.assertAlmostEqual(tts.ultimo[1], 1.08, places=5)

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

    def test_edge_primero_por_defecto_y_fallback_a_piper_si_falla(self):
        frase = "frase prioridad hito5 " + str(id(self))
        falso = SimpleNamespace(Communicate=CommunicateFalso)
        with patch.dict(os.environ, {"LYRIS_TTS_LOCAL": "0"}), \
             patch.dict(sys.modules, {"edge_tts": falso}), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None), \
             patch("voz_cache.guardar_audio_cache", lambda *_a: None), \
             patch.object(voz_local, "fallback_local",
                          side_effect=AssertionError("edge no debió fallar")):
            self.assertEqual(voz.Voz._audio(frase, "alegre"), b"EDGE_AUDIO")

        with patch.dict(os.environ, {"LYRIS_TTS_LOCAL": "0"}), \
             patch.dict(sys.modules, {"edge_tts": falso}), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None), \
             patch.object(voz_local, "generar_edge", lambda *_a: None), \
             patch.object(voz_local, "fallback_local", lambda *_a: b"PIPER_WAV"):
            self.assertEqual(voz.Voz._audio(frase, "alegre"), b"PIPER_WAV")

    def test_local_primero_con_env_y_cae_a_edge_si_falla(self):
        frase = "frase local hito5 " + str(id(self))
        falso = SimpleNamespace(Communicate=CommunicateFalso)
        vistos = []

        def local(frase, emocion):
            vistos.append(emocion)
            return None

        with patch.dict(os.environ, {"LYRIS_TTS_LOCAL": "1"}), \
             patch.dict(sys.modules, {"edge_tts": falso}), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None), \
             patch("voz_cache.guardar_audio_cache", lambda *_a: None), \
             patch.object(voz_local, "fallback_local", local):
            self.assertEqual(voz.Voz._audio(frase, "calmada"), b"EDGE_AUDIO")
        self.assertEqual(vistos, ["calmada"])

        with patch.dict(os.environ, {"LYRIS_TTS_LOCAL": "1"}), \
             patch("voz_cache.obtener_audio_cache", lambda *_a: None), \
             patch.object(voz_local, "fallback_local", lambda *_a: b"PIPER_WAV"), \
             patch.object(voz_local, "generar_edge",
                          side_effect=AssertionError("no debe llamar a edge")):
            self.assertEqual(voz.Voz._audio(frase), b"PIPER_WAV")

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
