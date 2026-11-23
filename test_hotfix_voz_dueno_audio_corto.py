"""Regresión: gracia breve tras verificar al dueño permite frases cortas por voz.

Bug real: el turno 1 verificaba al dueño (similitud=0.61 >= 0.35) y, segundos
después, una frase de 0.92s sin cámara se descartaba como audio de invitado.
"""
import contextlib
import io
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import voz_dueno


class TestAudioCortoDuenoReciente(unittest.TestCase):
    def _crear(self, duracion=0.92, camara=False):
        oido = SimpleNamespace(duracion_ultimo_audio=duracion, ultimo_audio=None)
        cam = SimpleNamespace(activa=camara, permite=lambda: camara)
        app = SimpleNamespace(oido=oido, camara=cam, origen_entrada_actual="microfono")

        # Construcción aislada: sin leer configuración ni banco biométrico reales.
        vd = voz_dueno.VozDueno.__new__(voz_dueno.VozDueno)
        vd.app = app
        vd.banco_dueno = object()
        vd.vector_dueno = vd.banco_dueno
        vd.ultimo_embedding = None
        vd.activa = True
        vd.umbral = 0.35
        vd.modo_solo_dueno = True
        vd.ultima_verificacion = {"es_dueno": True, "similitud": 1.0, "motivo": "inicial"}
        vd._dueno_verificado_ts = 0.0
        return vd

    def _verificar_biometria(self, vd, score=0.61):
        """Simula un audio de 3.64s con el score biométrico indicado."""
        vd.app.oido.ultimo_audio = [0.0] * 16000
        vd.app.oido.duracion_ultimo_audio = 3.64
        buf = io.StringIO()
        with contextlib.ExitStack() as pila:
            pila.enter_context(patch.object(
                voz_dueno, "preparar_audio_biometria",
                return_value=([0.0] * 16000, 2.37)))
            pila.enter_context(patch.object(
                voz_dueno, "extraer_embedding", return_value=[0.0] * 192))
            pila.enter_context(patch.object(
                voz_dueno, "calcular_similitud_banco", return_value=(score, 0.62, 12)))
            with contextlib.redirect_stdout(buf):
                vd.evaluar_entrada_voz("minimaliza las ventanas")
        return buf.getvalue()

    def _audio_corto(self, vd, duracion=0.92):
        """Simula la frase corta '¿Qué le dices?' sin cámara."""
        vd.app.oido.ultimo_audio = None
        vd.app.oido.duracion_ultimo_audio = duracion
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vd.evaluar_entrada_voz("¿Qué le dices?")
        return buf.getvalue()

    def test_audio_corto_sin_verificacion_ni_camara_se_rechaza(self):
        vd = self._crear()
        salida = self._audio_corto(vd)
        uv = vd.ultima_verificacion
        self.assertFalse(uv["es_dueno"])
        self.assertEqual(uv["motivo"], "audio_corto_sin_camara")
        self.assertFalse(uv["gracia_dueno_reciente"])
        self.assertIn("gracia_dueno_reciente=False permitido=False", salida)
        with contextlib.redirect_stdout(io.StringIO()):
            permite, _ = vd.autorizar_accion("minimizar_todo")
        self.assertFalse(permite)

    def test_gracia_tras_verificacion_exitosa_permite_audio_corto(self):
        vd = self._crear()
        self._verificar_biometria(vd, score=0.61)
        self.assertTrue(vd.ultima_verificacion["es_dueno"])

        # "Segundos después": la verificación positiva aún está dentro de la ventana.
        vd._dueno_verificado_ts = time.monotonic() - 2.0
        salida = self._audio_corto(vd)
        uv = vd.ultima_verificacion
        self.assertTrue(uv["es_dueno"])
        self.assertTrue(uv["gracia_dueno_reciente"])
        self.assertEqual(uv["motivo"], "audio_corto_gracia_dueno")
        self.assertIn("gracia_dueno_reciente=True permitido=True", salida)

        # La gracia permanece durante toda la ventana, no solo para un audio.
        salida2 = self._audio_corto(vd, duracion=0.69)
        self.assertTrue(vd.ultima_verificacion["es_dueno"])
        self.assertIn("gracia_dueno_reciente=True permitido=True", salida2)

    def test_gracia_expirada_vuelve_a_rechazar(self):
        vd = self._crear()
        self._verificar_biometria(vd)
        vd._dueno_verificado_ts = time.monotonic() - (voz_dueno.GRACIA_DUENO_SEG + 31.0)
        salida = self._audio_corto(vd)
        self.assertFalse(vd.ultima_verificacion["es_dueno"])
        self.assertFalse(vd.ultima_verificacion["gracia_dueno_reciente"])
        self.assertIn("gracia_dueno_reciente=False permitido=False", salida)
        self.assertEqual(vd._dueno_verificado_ts, 0.0)

    def test_extrano_con_similitud_baja_cancela_la_gracia(self):
        vd = self._crear()
        self._verificar_biometria(vd, score=0.61)
        salida_rechazo = self._verificar_biometria(vd, score=0.12)
        self.assertFalse(vd.ultima_verificacion["es_dueno"])
        self.assertIn("similitud=0.12", salida_rechazo)

        salida = self._audio_corto(vd)
        self.assertFalse(vd.ultima_verificacion["es_dueno"])
        self.assertIn("gracia_dueno_reciente=False permitido=False", salida)

    def test_audio_corto_con_camara_sigue_permitido_sin_gracia(self):
        vd = self._crear(camara=True)
        salida = self._audio_corto(vd)
        uv = vd.ultima_verificacion
        self.assertTrue(uv["es_dueno"])
        self.assertEqual(uv["motivo"], "audio_corto_camara_ok")
        self.assertFalse(uv["gracia_dueno_reciente"])
        self.assertIn("gracia_dueno_reciente=False permitido=True", salida)


if __name__ == "__main__":
    unittest.main()
