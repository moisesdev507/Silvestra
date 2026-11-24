"""Regresión Hito 1: oído fino para gracias, earcons suaves y concisión oral."""
import inspect
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro_parser
import cerebro_prompt
import oido
import sonidos_ui


SEG_CLARO = [{"no_speech_prob": 0.04, "avg_logprob": -0.18}]
SEG_RUIDO = [{"no_speech_prob": 0.91, "avg_logprob": -0.40}]
SEG_LOGP = [{"no_speech_prob": 0.10, "avg_logprob": -1.60}]


class ReflejoFalso:
    def __init__(self, segmentos):
        self.segments = segmentos


class TestHito1Reflejos(unittest.TestCase):
    def test_gracias_claro_pasa_y_ruido_se_descarta(self):
        clara = ReflejoFalso(SEG_CLARO)
        self.assertIsNone(
            oido.motivo_descarte_transcripcion("Muchas gracias.", 1290.4, clara))
        self.assertIsNone(
            oido.motivo_descarte_transcripcion("Muchas gracias, bebé.", 1100.0, clara))
        self.assertIsNone(
            oido.motivo_descarte_transcripcion("Gracias, muchas gracias.", 1180.0, clara))
        self.assertIsNone(
            oido.motivo_descarte_transcripcion("muchas gracias, gracias", 1180.0, clara))

        self.assertIsNotNone(
            oido.motivo_descarte_transcripcion("Muchas gracias.", 20.0, clara))
        self.assertIsNotNone(
            oido.motivo_descarte_transcripcion(
                "Muchas gracias.", 900.0, ReflejoFalso(SEG_RUIDO)))
        self.assertIsNotNone(
            oido.motivo_descarte_transcripcion(
                "Muchas gracias.", 900.0, ReflejoFalso(SEG_LOGP)))

    def test_youtube_y_gracias_largas_siempre_se_descartan(self):
        clara = ReflejoFalso(SEG_CLARO)
        for texto in (
            "Suscríbete al canal",
            "Gracias por ver",
            "Subtítulos realizados por Amara.org",
            "Listo, Silvestra, Muchas Gracias, I Love You Baby",
        ):
            motivo = oido.motivo_descarte_transcripcion(texto, 5000.0, clara)
            self.assertIsNotNone(motivo, texto)
            self.assertIn("alucinacion_whisper", motivo)

    def test_texto_normal_no_se_altera(self):
        clara = ReflejoFalso(SEG_CLARO)
        self.assertIsNone(
            oido.motivo_descarte_transcripcion("Hey, gracias.", 800.0, clara))
        self.assertIsNone(
            oido.motivo_descarte_transcripcion(
                "Abriendo Visual Studio Code.", 800.0, clara))

    def test_earcons_no_excepcion_ni_bloqueo(self):
        self.assertLessEqual(os.path.getsize(sonidos_ui.__file__), 7500)
        with patch.dict(os.environ, {"SILVESTRA_SIN_EARCONS": ""}, clear=False):
            for nombre in ("captado", "accion", "desconocido"):
                t0 = time.time()
                sonidos_ui.reproducir(nombre)
                self.assertLess(time.time() - t0, 0.2)

    def test_prompt_brevedad_y_formato(self):
        ruta_alma = os.path.join(os.path.dirname(cerebro_prompt.__file__), "alma.txt")
        with open(ruta_alma, "r", encoding="utf-8") as f:
            alma = f.read()
        self.assertEqual(cerebro_prompt.cargar_alma().strip(), alma.strip())
        for texto in ("1 a 2 frases", "Estoy lista para ayudarte con...", "¡Por supuesto!"):
            self.assertIn(texto, alma)

        fuente = inspect.getsource(cerebro_prompt)
        for clave in (
            "FORMATO OBLIGATORIO:", "EMOCION:", "RESPUESTA:", "ACCION:", "RECUERDO:",
            "1 a 2 frases", "estoy lista para ayudarte con...", "¡por supuesto!",
        ):
            self.assertIn(clave, fuente)

        muestra = (
            "EMOCION: alegre\n"
            "RESPUESTA: Listo.\n"
            "ACCION: ninguna\n"
            "RECUERDO: ninguno"
        )
        resp, accion, recuerdo, emo = cerebro_parser.separar(muestra)
        self.assertEqual((resp, emo), ("Listo.", "alegre"))
        self.assertIsNone(accion)
        self.assertIsNone(recuerdo)


if __name__ == "__main__":
    unittest.main()
