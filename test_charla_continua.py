"""Pruebas unitarias para charla continua (10s), barge-in seguro y humanización de resultados."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np

import charla_continua
import habla_espontanea
import telemetria


class TestCharlaContinua(unittest.TestCase):
    def setUp(self):
        charla_continua.cerrar_ventana_charla()

    def tearDown(self):
        charla_continua.cerrar_ventana_charla()

    def test_ventana_10s_y_expiracion(self):
        """Verifica que abrir_ventana_charla active la ventana y que expire tras el tiempo límite."""
        self.assertFalse(charla_continua.ventana_charla_activa())
        charla_continua.abrir_ventana_charla(duracion=0.15)
        self.assertTrue(charla_continua.ventana_charla_activa())
        time.sleep(0.18)
        self.assertFalse(charla_continua.ventana_charla_activa())

    def test_cierre_inmediato_ante_despedidas(self):
        """Verifica que es_cierre_conversacion reconozca cierres cotidianos y rechace preguntas normales."""
        cierres = ["gracias", "ok gracias", "muchas gracias", "listo", "ya está", "eso era todo", "nada más", "chao"]
        for c in cierres:
            self.assertTrue(charla_continua.es_cierre_conversacion(c), f"Debería ser cierre: '{c}'")

        no_cierres = ["cómo está mi compu", "revisa la memoria", "qué hora es", "Kaya, cuéntame un chiste"]
        for nc in no_cierres:
            self.assertFalse(charla_continua.es_cierre_conversacion(nc), f"No debería ser cierre: '{nc}'")

    def test_barge_in_ignora_ruido_bajo_y_corta_ante_voz_sostenida(self):
        """Verifica que barge-in seguro ignore silencio/ruido bajo y corte ante energía vocal sostenida."""
        app = SimpleNamespace(
            voz=SimpleNamespace(ocupada=lambda: True, detener=MagicMock()),
            cola=SimpleNamespace(put=MagicMock())
        )

        # 1. Silencio o ruido bajo (RMS < 850) -> No corta
        audio_bajo = np.zeros(1600, dtype=np.int16)
        corta = charla_continua.evaluar_barge_in_seguro(app, audio_bajo)
        self.assertFalse(corta)
        app.voz.detener.assert_not_called()

        # 2. Voz fuerte instantánea (impulso o clic < 0.22s) -> Primer frame no corta de golpe
        audio_fuerte = np.full(1600, 2000, dtype=np.int16)
        corta1 = charla_continua.evaluar_barge_in_seguro(app, audio_fuerte)
        self.assertFalse(corta1)

        # Simular energía sostenida tras el umbral de duración
        time.sleep(0.24)
        corta2 = charla_continua.evaluar_barge_in_seguro(app, audio_fuerte)
        self.assertTrue(corta2)
        app.voz.detener.assert_called_once()
        app.cola.put.assert_called_with(("interrupcion", None))

    def test_humanizar_resultado_accion_preserva_cifras(self):
        """Verifica que humanizar_resultado_accion conserve cifras reales sin clichés robóticos."""
        orden = "cómo está mi compu"
        crudo = "CPU al 25%, RAM 8.0 de 16.0 GB (50%). Batería al 85%, cargando."

        # Prueba con LLM simulado
        cerebro = SimpleNamespace(
            _pedir=lambda *a, **k: "Tu equipo anda relajado: CPU al 25%, RAM 8.0 de 16.0 GB y batería al 85% cargando."
        )
        app = SimpleNamespace(cerebro=cerebro, memoria=SimpleNamespace(creador="Moisés"))

        humano = habla_espontanea.humanizar_resultado_accion(orden, crudo, app)
        self.assertIn("25%", humano)
        self.assertIn("85%", humano)
        self.assertNotIn("sistemas en línea", humano.lower())
        self.assertNotIn("en qué te ayudo", humano.lower())

        # Prueba de fallback offline
        humano_offline = habla_espontanea.humanizar_resultado_accion(orden, crudo, None)
        self.assertIn("25%", humano_offline)
        self.assertIn("8.0 de 16.0 GB", humano_offline)
        self.assertTrue(len(humano_offline) > len(crudo))

    def test_atajo_telemetria_reconoce_compu_y_pc(self):
        """Verifica que responder_telemetria atienda 'compu', 'computador' y 'pc'."""
        with patch.object(telemetria, "estado_sistema", return_value={"texto": "CPU al 15%, RAM al 40%."}):
            r1 = telemetria.responder_telemetria("cómo está mi compu")
            self.assertIsNotNone(r1)
            r2 = telemetria.responder_telemetria("revisa el estado de mi computador")
            self.assertIsNotNone(r2)
            r3 = telemetria.responder_telemetria("estado de mi pc")
            self.assertIsNotNone(r3)


if __name__ == "__main__":
    unittest.main()
