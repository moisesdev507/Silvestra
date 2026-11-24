"""Regresión: pre-roll de 800 ms para no recortar la palabra inicial."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import oido_vad


class DetectorFalso:
    """Silero de prueba: dispara después de N bloques y entrega un segmento corto."""

    def __init__(self, disparar_en):
        self.disparar_en = disparar_en
        self.llamadas = 0
        self.vacio = True

    def accept_waveform(self, _chunk):
        self.llamadas += 1

    def is_speech_detected(self):
        return self.llamadas >= self.disparar_en

    def empty(self):
        return self.vacio

    @property
    def front(self):
        return SimpleNamespace(samples=np.full(512, 0.9, dtype=np.float32))

    def pop(self):
        self.vacio = True

    def flush(self):
        self.vacio = False

    def reset(self):
        self.llamadas = 0
        self.vacio = True


class TestPreRoll(unittest.TestCase):
    def _vad(self, disparar_en):
        with patch.object(oido_vad.DetectorVozSilero, "_iniciar_detector",
                          lambda self: None):
            vad = oido_vad.DetectorVozSilero(sample_rate=16000)
        falso = DetectorFalso(disparar_en)
        vad._detector = falso
        vad._disponible = True
        falso.vacio = False
        return vad, falso

    @staticmethod
    def _bloque(valor):
        return (np.full(800, valor, dtype=np.float32) * 32767).astype(np.int16)

    def test_pre_roll_se_antepone_al_segmento(self):
        vad, _ = self._vad(disparar_en=12)
        for i in range(20):
            vad.alimentar(self._bloque(0.25 if i < 4 else 0.0))
        self.assertTrue(vad.detectando_voz())
        self.assertIsNotNone(vad._pre_roll_congelado)
        segmento = vad.extraer_segmento()
        self.assertTrue(np.any(np.isclose(segmento, 0.25, atol=0.01)),
                        "El inicio de «Lyris» debe sobrevivir al recorte del VAD")
        self.assertGreater(len(segmento), 12 * 800)
        self.assertIsNone(vad._pre_roll_congelado)

    def test_pre_roll_no_supera_800ms(self):
        vad, _ = self._vad(disparar_en=40)
        for _ in range(45):
            vad.alimentar(self._bloque(0.1))
        congelado = vad._pre_roll_congelado
        self.assertLessEqual(len(congelado), int(oido_vad.PRERROLL_SEG * 16000) + 800)

    def test_reset_limpia_el_pre_roll(self):
        vad, falso = self._vad(disparar_en=2)
        vad.alimentar(self._bloque(0.2))
        vad.reset()
        self.assertEqual(len(vad._pre_roll), 0)
        self.assertIsNone(vad._pre_roll_congelado)
        self.assertFalse(vad._voz_antes)
        self.assertEqual(falso.llamadas, 0)


if __name__ == "__main__":
    unittest.main()
