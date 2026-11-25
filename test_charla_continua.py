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

    def test_barge_in_adaptativo_voz_normal_vs_eco(self):
        """Verifica que barge-in corte con voz normal (~620 RMS) y NO dispare con eco (~250 RMS)."""
        app = SimpleNamespace(
            voz=SimpleNamespace(ocupada=lambda: True, detener=MagicMock()),
            cola=SimpleNamespace(put=MagicMock())
        )
        charla_continua.reiniciar_estado_barge_in()

        # Simular los primeros 0.2s con eco de parlante a ~250 RMS
        audio_eco = np.full(1600, 250, dtype=np.int16)
        corta_eco = charla_continua.evaluar_barge_in_seguro(app, audio_eco)
        self.assertFalse(corta_eco)
        time.sleep(0.15)
        # Seguir con eco: no debe cortar
        corta_eco2 = charla_continua.evaluar_barge_in_seguro(app, audio_eco)
        self.assertFalse(corta_eco2)
        app.voz.detener.assert_not_called()

        # Usuario habla con voz normal a ~620 RMS
        audio_voz = np.full(1600, 620, dtype=np.int16)
        corta_voz1 = charla_continua.evaluar_barge_in_seguro(app, audio_voz)
        self.assertFalse(corta_voz1)  # Primer bloque registra inicio

        # Sostenido tras ~190 ms -> Debe interrumpir
        time.sleep(0.20)
        corta_voz2 = charla_continua.evaluar_barge_in_seguro(app, audio_voz)
        self.assertTrue(corta_voz2)
        app.voz.detener.assert_called_once_with(motivo="barge_in")
        app.cola.put.assert_called_with(("interrupcion", None))

    def test_barge_in_escala_float32_normalizada(self):
        """Verifica que muestras en float32 [-1.0, 1.0] se normalicen a escala int16."""
        app = SimpleNamespace(
            voz=SimpleNamespace(ocupada=lambda: True, detener=MagicMock()),
            cola=SimpleNamespace(put=MagicMock())
        )
        charla_continua.reiniciar_estado_barge_in()
        # 600 RMS sobre 32768 equivale a ~0.0183 en escala [-1.0, 1.0]
        val_float = 600.0 / 32768.0
        audio_float = np.full(1600, val_float, dtype=np.float32)

        c1 = charla_continua.evaluar_barge_in_seguro(app, audio_float)
        self.assertFalse(c1)
        time.sleep(0.20)
        c2 = charla_continua.evaluar_barge_in_seguro(app, audio_float)
        self.assertTrue(c2)
        app.voz.detener.assert_called_once_with(motivo="barge_in")

    def test_barge_in_laptop_parlante_elevado(self):
        """Verifica que el umbral para parlante con eco de laptop (~800 RMS) no corte en eco pero sí con voz (> 1000 RMS)."""
        app = SimpleNamespace(
            voz=SimpleNamespace(ocupada=lambda: True, detener=MagicMock()),
            cola=SimpleNamespace(put=MagicMock())
        )
        charla_continua.reiniciar_estado_barge_in()
        audio_eco_fuerte = np.full(1600, 350, dtype=np.int16)
        charla_continua.evaluar_barge_in_seguro(app, audio_eco_fuerte)
        time.sleep(0.15)
        # Sigue el eco: no debe cortar
        corta_eco = charla_continua.evaluar_barge_in_seguro(app, audio_eco_fuerte)
        self.assertFalse(corta_eco)
        app.voz.detener.assert_not_called()

        # Usuario habla fuerte sobre el parlante
        audio_usuario = np.full(1600, 750, dtype=np.int16)
        charla_continua.evaluar_barge_in_seguro(app, audio_usuario)
        time.sleep(0.20)
        corta_usuario = charla_continua.evaluar_barge_in_seguro(app, audio_usuario)
        self.assertTrue(corta_usuario)

    def test_barge_in_habilitado(self):
        """Verifica que barge_in_habilitado() retorne True por defecto."""
        self.assertTrue(charla_continua.barge_in_habilitado())

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
