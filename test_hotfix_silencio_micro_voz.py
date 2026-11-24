"""Regresión extraída: sonidos_ui silencioso y micro-voz «¿Sí?» de Salomé."""
import io
import unittest
import wave
from types import SimpleNamespace

import micro_voz
import sonidos_ui
import voz_cache


class TestSilencioMicroVoz(unittest.TestCase):
    def test_sonidos_ui_sin_pitidos_y_micro_voz_salome(self):
        with wave.open(io.BytesIO(sonidos_ui.generar_wav("activar"))) as wf:
            muestras = wf.readframes(wf.getnframes())
            self.assertEqual(wf.getframerate(), 44100)
        self.assertEqual(set(muestras), {0})
        for nombre in ("activar", "confirmar", "captado", "accion"):
            self.assertIsNone(getattr(sonidos_ui, nombre)())
        self.assertIsNone(sonidos_ui.reproducir("captado"))

        sonado = []
        app = SimpleNamespace(voz=SimpleNamespace(
            reproductor=SimpleNamespace(
                reproducir_corto=lambda audio, **kw: sonado.append((audio, kw)))))
        voz_cache.guardar_audio_cache(micro_voz.FRASE_INVOCACION, b"audio-salome")
        self.addCleanup(voz_cache.limpiar)
        self.assertTrue(micro_voz.sonar_invocacion(app))
        self.assertEqual(micro_voz.FRASE_INVOCACION, "¿Sí?")
        self.assertEqual(sonado[0][0], b"audio-salome")


if __name__ == "__main__":
    unittest.main()
