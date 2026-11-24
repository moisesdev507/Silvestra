"""Regresión: invocación duplicada no debe activar eco_prompt_o_repeticion."""
import contextlib
import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import oido as oido_mod
import oido_deepgram
import oido_filtro
from oido import Oido

FRASE = ("Lyris, Lyris, recuerda que mañana tengo una entrega de "
         "programación en la FIEC, a las 9 de la mañana.")
NORMALIZADA = ("Lyris, recuerda que mañana tengo una entrega de "
               "programación en la FIEC, a las 9 de la mañana.")


class FlujoFalso:
    def __init__(self, **_kw):
        self.bloques = 3

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


class TestFiltroEcoOido(unittest.TestCase):
    def _escuchar(self, texto, ultimo_dicho=""):
        oido_deepgram.reiniciar()
        silencioso = SimpleNamespace(reproducir_feedback_escucha=lambda **_kw: None)
        parches = (
            patch.object(oido_mod, "FlujoMicrofono", FlujoFalso),
            patch.object(oido_mod, "DetectorVozSilero", VadFalso),
            patch.dict(sys.modules, {"oido_feedback": silencioso}),
            patch.object(oido_deepgram, "transcribir", lambda *_a, **_k: (texto, 1.2)),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        oido = Oido(SimpleNamespace(), lambda: "Moisés, Lyris")
        app = SimpleNamespace(ultimo_dicho=ultimo_dicho)
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            resultado = oido.escuchar(app=app)
        return resultado, salida.getvalue()

    def test_invocacion_duplicada_no_se_descarta_y_se_normaliza(self):
        self.assertEqual(oido_filtro.normalizar_transcripcion(FRASE), NORMALIZADA)
        resultado, salida = self._escuchar(FRASE)
        self.assertEqual(resultado, NORMALIZADA)
        self.assertIn("[oido] transcrito=", salida)
        self.assertNotIn("eco_prompt_o_repeticion", salida)

    def test_eco_real_del_ultimo_tts_si_se_descarta(self):
        ultimo = "Aquí andoy, despejada y lista para lo que traigas, Moisés."
        for texto in (ultimo, f"Lyris, {ultimo}"):
            with self.subTest(texto=texto):
                resultado, salida = self._escuchar(texto, ultimo)
                self.assertIsNone(resultado)
                self.assertIn("eco_prompt_o_repeticion", salida)

    def test_alucinacion_degenerada_si_se_descarta(self):
        tik = "Lyris Lyris Lyris Lyris"
        self.assertTrue(oido_filtro.es_bucle_degenerado(tik))
        self.assertFalse(oido_filtro.es_bucle_degenerado(NORMALIZADA))
        resultado, salida = self._escuchar(tik)
        self.assertIsNone(resultado)
        self.assertIn("eco_prompt_o_repeticion", salida)

    def test_bucles_historicos_siguen_descartandose(self):
        for texto in ("Chrome, chrome, chrome, chrome, chrome, chrome.",
                      "abre abre abre la ventana por favor",
                      "¿qué hora es?, ¿qué hora es?, ¿cuándo es?, ¿cuándo es?"):
            with self.subTest(texto=texto):
                resultado, _salida = self._escuchar(texto)
                self.assertIsNone(resultado)

    def test_mencionar_contexto_previo_no_se_descarta(self):
        ultimo = "Tienes una entrega de programación pendiente."
        frase = ("Lyris, recuerda que mañana tengo una entrega de "
                 "programación en la FIEC a las 9")
        resultado, salida = self._escuchar(frase, ultimo)
        self.assertEqual(resultado, frase)
        self.assertNotIn("eco_prompt_o_repeticion", salida)


if __name__ == "__main__":
    unittest.main()
