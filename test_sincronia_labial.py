"""Pruebas sin dispositivo de audio ni widgets Qt."""
import threading
import time
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

from cara_sincronia import SincroniaLabial, forma_boca
from voz_reproductor import ReproductorAudio, calcular_envolvente_rms


class CaraSyncTests(unittest.TestCase):
    def setUp(self):
        self.sync = SincroniaLabial()
        self.voz = SimpleNamespace(sincronia_labial=self.sync)
        self.cara = SimpleNamespace(_ref_voz=self.voz, hablando=True, val_boca_ancho=28.0)

    def test_1_audio_real_supera_tiempo_burbuja(self):
        self.sync.preparar(1, "Hola, estoy hablando")
        self.sync.iniciar(1)
        self.sync.actualizar(1, .25)
        t = time.monotonic()
        self.cara._boca_tiempo = t
        self.cara.hablando = False  # la burbuja ya expiró
        visible, apertura, _ = forma_boca(self.cara, 0, t + .04)
        self.assertTrue(visible)
        self.assertGreater(apertura, 0)
        self.assertTrue(self.sync.snapshot()[1])

    def test_2_cierre_suave_solo_al_fin_del_canal(self):
        t = time.monotonic()
        self.cara._boca_tiempo = t
        self.sync.preparar(2, "Probando audio")
        self.sync.iniciar(2)
        self.sync.actualizar(2, .4)
        _, alto, _ = forma_boca(self.cara, 0, t + .04)
        self.sync.finalizar(2)
        visible, decay, _ = forma_boca(self.cara, 0, t + .08)
        self.assertTrue(visible)
        self.assertLess(decay, alto)
        for i in range(4, 25):
            visible, _, _ = forma_boca(self.cara, 0, t + i * .04)
        self.assertFalse(visible)

    def test_3_cancelacion_cierra_sin_residuos(self):
        self.sync.preparar(3, "Interrumpida")
        self.sync.iniciar(3)
        self.sync.actualizar(3, .8)
        forma_boca(self.cara, 0, time.monotonic() + .04)
        cancel = threading.Event()
        class Canal:
            def get_busy(self): return True
            def stop(self): pass
        channel = Canal()
        class Sound:
            def play(self): return channel
        class Music:
            def stop(self): pass
            def unload(self): pass
            def get_busy(self): return False
        class Mixer:
            music = Music()
            def Sound(self, _bio): return Sound()
            def stop(self): pass
            def get_busy(self): return False
        player = ReproductorAudio(SimpleNamespace(mixer=Mixer()))
        def nivel(value):
            if cancel.is_set(): return
            self.sync.actualizar(3, value)
            if value > 0:
                cancel.set()
                self.sync.cancelar()
        with patch("voz_reproductor.calcular_envolvente_rms", return_value=([.8], Sound())):
            result = player.reproducir(b"pcm", lambda: not cancel.is_set(), nivel,
                                       lambda: self.sync.iniciar(3))
        self.assertFalse(result)
        visible, alto, _ = forma_boca(self.cara, 0, time.monotonic() + .05)
        self.assertFalse(visible)
        self.assertEqual(alto, 0)

    def test_4_ignora_callbacks_de_generacion_anterior(self):
        self.sync.preparar(4, "Primera frase")
        self.sync.iniciar(4)
        self.sync.preparar(5, "Frase nueva")
        self.assertFalse(self.sync.actualizar(4, .9))
        self.assertFalse(self.sync.iniciar(4))
        gen, activa, nivel, _patron, _inicio, _cancelada = self.sync.snapshot()
        self.assertEqual(gen, 5)
        self.assertFalse(activa)
        self.assertEqual(nivel, -1.0)

    def test_5_respaldo_sin_rms_tiene_pulsos_silabicos(self):
        self.sync.preparar(6, "silabas naturales")
        self.sync.iniciar(6)
        self.sync.actualizar(6, -1)
        t = time.monotonic()
        self.cara._boca_tiempo = t
        _, a, _ = forma_boca(self.cara, 0, t + .12)
        _, b, _ = forma_boca(self.cara, 0, t + .31)
        self.assertNotEqual(round(a, 2), round(b, 2))
        self.assertTrue(self.sync.snapshot()[1])
        self.sync.finalizar(6)
        self.assertFalse(self.sync.snapshot()[1])

    def test_reproductor_emite_inicio_niveles_y_fin_real(self):
        class Canal:
            def __init__(self): self.lecturas = 0
            def get_busy(self):
                self.lecturas += 1
                return self.lecturas < 4
            def stop(self): pass
        canal = Canal()
        class Sonido:
            def play(self): return canal
        class Music:
            def stop(self): pass
            def unload(self): pass
            def get_busy(self): return False
        class Mixer:
            music = Music()
            def Sound(self, _bio): return Sonido()
            def stop(self): pass
            def get_busy(self): return False
        pg = SimpleNamespace(mixer=Mixer())
        niveles, inicios = [], []
        player = ReproductorAudio(pg)
        with patch("voz_reproductor.calcular_envolvente_rms", return_value=([.2, .4], Sonido())):
            ok = player.reproducir(b"pcm", lambda: True, niveles.append,
                                   lambda: inicios.append(time.monotonic()))
        self.assertTrue(ok)
        self.assertEqual(len(inicios), 1)
        self.assertEqual(niveles[-1], 0.0)
        self.assertTrue(any(n > 0 for n in niveles))

    def test_envolvente_sintetica_conserva_silencio_y_pico(self):
        import numpy as np
        samples = np.concatenate((np.zeros(100), np.full(100, 8192)))
        sound = object()
        fake = SimpleNamespace(
            mixer=SimpleNamespace(Sound=lambda _bio: sound, get_init=lambda: (1000, -16, 1)),
            sndarray=SimpleNamespace(array=lambda _snd: samples))
        with patch.dict(sys.modules, {"pygame": fake}):
            env, got = calcular_envolvente_rms(b"synthetic", fps=10)
        self.assertIs(got, sound)
        self.assertEqual(len(env), 2)
        self.assertEqual(env[0], 0.0)
        self.assertAlmostEqual(env[1], .25, places=2)


if __name__ == "__main__":
    unittest.main()
