"""Pruebas del nivel de voz en vivo y de la sincronía con el orbe."""
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import live_motor_audio
import live_orquestador


class _SesionPrueba(live_motor_audio.CapaAudioLive):
    def __init__(self):
        self.activo = True
        self.niveles = []

    def _notificar_nivel(self, nivel, salida=False):
        self.niveles.append((nivel, salida))


class TestNivelVozLive(unittest.TestCase):

    def test_energia_salida_con_ataque_suave(self):
        sesion = _SesionPrueba()
        with patch("live_audio.calcular_energia_pcm16", return_value=0.8), \
                patch("live_audio.registrar_tiempo_primera_voz"):
            sesion._notificar_nivel_salida(b"\x00\x00" * 100)
            self.assertAlmostEqual(sesion._nivel_salida_suave, 0.36)
            sesion._notificar_nivel_salida(b"\x00\x00" * 100)
            self.assertGreater(sesion._nivel_salida_suave, 0.36)
            self.assertLess(sesion._nivel_salida_suave, 0.8)
        self.assertEqual(len(sesion.niveles), 2)
        self.assertTrue(all(salida for _, salida in sesion.niveles))
        sesion.activo = False
        sesion._hilo_decaimiento.join(timeout=1.0)

    def test_decaimiento_cierra_a_cero(self):
        sesion = _SesionPrueba()
        sesion._nivel_salida_gen = 1
        sesion._nivel_salida_t = time.monotonic() - 1.0
        sesion._nivel_salida_suave = 0.003

        def notificar(nivel, salida=False):
            sesion.niveles.append((nivel, salida))
            if nivel == 0.0:
                sesion.activo = False

        sesion._notificar_nivel = notificar
        sesion._decaer_nivel_salida()
        self.assertEqual(sesion.niveles[-1][0], 0.0)
        self.assertEqual(sesion._nivel_salida_gen, 0)

    def test_nivel_live_se_encola_y_se_aplica_en_el_hilo_ui(self):
        app = SimpleNamespace(
            cola=queue.Queue(),
            cara=SimpleNamespace(nivel_volumen=0.0, _ref_voz=SimpleNamespace(nivel_volumen=0.0)),
            voz=SimpleNamespace(nivel_volumen=0.0),
        )
        coordinador = object.__new__(live_orquestador.CoordinadorLiveSilvestra)
        coordinador.app = app

        coordinador._al_nivel_voz(0.75)
        tipo, dato = app.cola.get_nowait()
        self.assertEqual((tipo, dato), ("nivel_voz_live", 0.75))
        self.assertTrue(live_orquestador.despachar_evento_live(app, tipo, dato))
        self.assertEqual(app.cara.nivel_volumen, 0.75)
        self.assertEqual(app.cara._ref_voz.nivel_volumen, 0.75)

    def test_voz_clasica_actualiza_la_referencia_del_orbe(self):
        import cara_sincronia

        voz = SimpleNamespace(
            _estado_lock=threading.RLock(), version=1, _generacion_audio=3,
            nivel_volumen=0.0,
        )
        sincronia = cara_sincronia.SincroniaLabial()
        sincronia.preparar(3, "hola, Moisés")
        _inicio, nivel = sincronia.callbacks(voz, 3, 1, lambda: None)
        nivel(0.65)

        class CaraFalsa:
            def __init__(self, ref):
                self._ref_voz = ref

            @property
            def nivel_volumen(self):
                return getattr(self._ref_voz, "nivel_volumen", 0.0)

        self.assertAlmostEqual(CaraFalsa(voz).nivel_volumen, 0.65)
        self.assertEqual(sincronia.snapshot()[2], 0.65)


if __name__ == "__main__":
    unittest.main()
