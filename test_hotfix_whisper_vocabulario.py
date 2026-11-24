"""Regresión: prompt mínimo de Whisper y filtros anti-bucles.

Verifica que la petición a Groq no incluya listas de comandos ni preguntas,
que la transcripción normal siga funcionando y que los ecos, repeticiones y
bucles de alucinación se descarten como en el log real.
"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import oido as oido_mod
import oido_deepgram
from oido import Oido, PROMPT_WHISPER

TERMINOS = ("Lyris", "Visual Studio Code")
BUCLE_REAL = "¿qué hora es?, ¿qué hora es?, ¿cuándo es?, ¿cuándo es?, ¿cuándo es?"


class ClienteFalso:
    def __init__(self, texto, segmentos=None):
        self.texto, self.segmentos, self.kwargs = texto, segmentos or [], None

    @property
    def audio(self):
        return self

    @property
    def transcriptions(self):
        return self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(text=self.texto, segments=self.segmentos)


class FlujoFalso:
    def __init__(self, bloques=3, **_kw):
        self.bloques = bloques

    def asegurar_flujo(self):
        pass

    def drenar(self):
        pass

    def aplicar_guarda_antieco(self, **_kw):
        pass

    def leer(self, timeout=0.1):
        if self.bloques <= 0:
            return None
        self.bloques -= 1
        return np.full(800, 500, dtype=np.int16)


class VadFalso:
    def __init__(self, **_kw):
        self.entregas, self.completo = 0, False

    def reset(self):
        pass

    def alimentar(self, _datos):
        self.entregas += 1
        if self.entregas >= 2:
            self.completo = True

    def detectando_voz(self):
        return True

    def hay_segmento_completo(self):
        return self.completo

    def flush(self):
        pass

    def extraer_segmento(self):
        return np.sin(np.linspace(0, 100, 8000)).astype(np.float32) * 0.3


class TestWhisperVocabulario(unittest.TestCase):
    def _oido(self, texto, segmentos=None, vocab="Moisés, Lyris"):
        cliente = ClienteFalso(texto, segmentos)
        SILENCIOSO = SimpleNamespace(reproducir_feedback_escucha=lambda **_kw: None)
        for parche in (
            patch.object(oido_mod, "FlujoMicrofono", FlujoFalso),
            patch.object(oido_mod, "DetectorVozSilero", VadFalso),
            patch.dict(sys.modules, {"oido_feedback": SILENCIOSO}),
            # Estos tests exercitan el prompt de Whisper: Deepgram no debe
            # interferir aunque haya clave configurada en el entorno.
            patch.object(oido_deepgram, "transcribir", lambda *_a: None),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        return Oido(cliente, lambda: vocab), cliente

    def test_peticion_incluye_prompt_compacto(self):
        oido, cliente = self._oido("Abre Visual Studio Code.")

        self.assertEqual(oido.escuchar(), "Abre Visual Studio Code.")
        self.assertIsNotNone(cliente.kwargs)
        self.assertEqual(cliente.kwargs["model"], oido_mod.MODELO_VOZ)
        self.assertEqual(cliente.kwargs["language"], "es")
        self.assertEqual(cliente.kwargs["response_format"], "verbose_json")
        self.assertEqual(cliente.kwargs["temperature"], 0.0)
        prompt = cliente.kwargs["prompt"]
        for termino in TERMINOS:
            self.assertIn(termino, prompt)
        for prohibido in ("¿qué hora es?", "minimiza", "Spotify", "Chrome", "volumen"):
            self.assertNotIn(prohibido, prompt)
        self.assertNotIn("¿", prompt)
        self.assertLessEqual(len(prompt), 60)

    def test_nombres_de_memoria_no_rompen_el_limite(self):
        oido, cliente = self._oido("Abre Chrome.", vocab="Moisés, Lyris, Proyecto, Silvestra, Moisés")
        oido.escuchar()
        prompt = cliente.kwargs["prompt"]
        self.assertIn("Proyecto", prompt)
        self.assertLessEqual(len(prompt), 90)

    def test_transcripcion_normal_no_se_rompe(self):
        oido, _cliente = self._oido("Lyris, maximiza el volumen.")
        self.assertEqual(oido.escuchar(), "Lyris, maximiza el volumen.")

    def test_eco_del_prompt_en_silencio_se_descarta(self):
        oido, cliente = self._oido(PROMPT_WHISPER)
        self.assertIsNone(oido.escuchar())
        self.assertIsNotNone(cliente.kwargs)

    def test_repeticiones_y_bucle_se_descartan(self):
        for texto in ("Chrome, chrome, chrome, chrome, chrome, chrome.",
                      "abre abre abre la ventana por favor", BUCLE_REAL):
            with self.subTest(texto=texto):
                oido, _cliente = self._oido(texto)
                self.assertIsNone(oido.escuchar())

    def test_bucle_del_log_se_descarta_como_alucinacion(self):
        self.assertTrue(oido_mod.es_bucle_alucinacion(BUCLE_REAL))
        for texto in ("Gracias, muchas gracias.", "Lyris, ¿qué hora es?",
                      "Hola, hola, ¿cómo estás?"):
            self.assertFalse(oido_mod.es_bucle_alucinacion(texto), texto)

    def test_filtro_de_silencio_existente_sigue_activo(self):
        segmentos = [{"no_speech_prob": 0.93, "avg_logprob": -0.4}]
        oido, _cliente = self._oido("El clima esta soleado.", segmentos)
        self.assertIsNone(oido.escuchar())


if __name__ == "__main__":
    unittest.main()
