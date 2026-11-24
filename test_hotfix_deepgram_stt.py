"""Regresión: Deepgram Nova como STT principal con respaldo automático a Whisper."""
import contextlib
import io
import os
import secrets
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import config
import httpx
import numpy as np

import oido as oido_mod
import oido_deepgram
from oido import Oido

TEXTO_DG = "Abre el bloc de notas."
TEXTO_WHISPER = "Maximiza la ventana."
BUCLE = "¿qué hora es?, ¿qué hora es?, ¿cuándo es?, ¿cuándo es?"


class ClienteFalso:
    def __init__(self, texto):
        self.texto, self.kwargs = texto, None

    @property
    def audio(self):
        return self

    @property
    def transcriptions(self):
        return self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(text=self.texto, segments=[])


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
        self.entregas, self.completo = 0, False

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


class RespuestaDG:
    def __init__(self, codigo, texto=TEXTO_DG, duracion=1.2):
        self.status_code = codigo
        self._texto, self._duracion = texto, duracion

    def json(self):
        return {
            "metadata": {"duration": self._duracion},
            "results": {"channels": [{"alternatives": [{"transcript": self._texto}]}]},
        }


class TestHotfixDeepgramSTT(unittest.TestCase):
    def setUp(self):
        oido_deepgram.reiniciar()
        self.clave = "prueba-" + secrets.token_hex(4)
        # Aislar los tests de cualquier clave real definida en config.py.
        for atributo in ("DEEPGRAM_API_KEY", "DEEPGRAM_MODEL"):
            parche = patch.object(config, atributo, "", create=True)
            parche.start()
            self.addCleanup(parche.stop)

    def _oido(self, texto_whisper=TEXTO_WHISPER):
        cliente = ClienteFalso(texto_whisper)
        silencioso = SimpleNamespace(reproducir_feedback_escucha=lambda **_kw: None)
        for parche in (
            patch.object(oido_mod, "FlujoMicrofono", FlujoFalso),
            patch.object(oido_mod, "DetectorVozSilero", VadFalso),
            patch.dict(sys.modules, {"oido_feedback": silencioso}),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        return Oido(cliente, lambda: "Moisés, Lyris"), cliente

    def _con_clave(self):
        return patch.dict(os.environ, {"DEEPGRAM_API_KEY": self.clave})

    def test_200_transcribe_con_deepgram_sin_llamar_a_whisper(self):
        oido, cliente = self._oido()
        post = Mock(return_value=RespuestaDG(200))
        with self._con_clave(), patch.object(oido_deepgram.httpx, "post", post):
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                resultado = oido.escuchar()

        self.assertEqual(resultado, TEXTO_DG)
        self.assertIsNone(cliente.kwargs)
        peticion = post.call_args.kwargs
        self.assertEqual(peticion["params"]["model"], "nova-3")
        self.assertEqual(peticion["params"]["language"], "es")
        self.assertEqual(peticion["params"]["smart_format"], "true")
        self.assertEqual(peticion["headers"]["Authorization"], "Token " + self.clave)
        self.assertEqual(peticion["headers"]["Content-Type"], "audio/wav")
        self.assertLessEqual(peticion["timeout"], 6.0)
        self.assertNotIn(self.clave, salida.getvalue())
        self.assertIn("deepgram=", salida.getvalue())

    def test_clave_y_modelo_desde_config_tienen_prioridad(self):
        oido, cliente = self._oido()
        modelo_config = "nova-3-config"
        post = Mock(return_value=RespuestaDG(200))
        with patch.object(config, "DEEPGRAM_API_KEY", self.clave, create=True), \
             patch.object(config, "DEEPGRAM_MODEL", modelo_config, create=True), \
             patch.dict(os.environ, {"DEEPGRAM_API_KEY": "", "DEEPGRAM_MODEL": "nova-3"}), \
             patch.object(oido_deepgram.httpx, "post", post):
            resultado = oido.escuchar()

        self.assertEqual(resultado, TEXTO_DG)
        self.assertIsNone(cliente.kwargs)
        peticion = post.call_args.kwargs
        self.assertEqual(peticion["headers"]["Authorization"], "Token " + self.clave)
        self.assertEqual(peticion["params"]["model"], modelo_config)

    def test_timeout_y_500_caen_a_whisper_en_el_mismo_turno(self):
        for fallo in ("timeout", 500):
            with self.subTest(fallo=fallo):
                oido_deepgram.reiniciar()
                oido, cliente = self._oido()
                if fallo == "timeout":
                    post = Mock(side_effect=httpx.TimeoutException("lento"))
                else:
                    post = Mock(return_value=RespuestaDG(500))
                with self._con_clave(), patch.object(oido_deepgram.httpx, "post", post):
                    resultado = oido.escuchar()
                self.assertEqual(resultado, TEXTO_WHISPER)
                self.assertIsNotNone(cliente.kwargs)
                self.assertTrue(oido_deepgram.esta_activo())

    def test_401_y_402_desactivan_deepgram_para_los_siguientes_turnos(self):
        for codigo in (401, 402):
            with self.subTest(codigo=codigo):
                oido_deepgram.reiniciar()
                post = Mock(return_value=RespuestaDG(codigo))
                with self._con_clave(), patch.object(oido_deepgram.httpx, "post", post):
                    primero, cli1 = self._oido()
                    self.assertEqual(primero.escuchar(), TEXTO_WHISPER)
                    self.assertIsNotNone(cli1.kwargs)
                    segundo, cli2 = self._oido()
                    self.assertEqual(segundo.escuchar(), TEXTO_WHISPER)
                    self.assertIsNotNone(cli2.kwargs)

                self.assertEqual(post.call_count, 1)
                self.assertFalse(oido_deepgram.esta_activo())

    def test_sin_clave_usa_whisper_directo(self):
        oido, cliente = self._oido()
        post = Mock(return_value=RespuestaDG(200))
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": ""}), \
             patch.object(oido_deepgram.httpx, "post", post):
            resultado = oido.escuchar()
        self.assertEqual(resultado, TEXTO_WHISPER)
        self.assertIsNotNone(cliente.kwargs)
        post.assert_not_called()

    def test_bucle_de_deepgram_tambien_se_descarta(self):
        oido, cliente = self._oido()
        post = Mock(return_value=RespuestaDG(200, texto=BUCLE))
        with self._con_clave(), patch.object(oido_deepgram.httpx, "post", post):
            self.assertIsNone(oido.escuchar())
        self.assertIsNone(cliente.kwargs)


if __name__ == "__main__":
    unittest.main()
