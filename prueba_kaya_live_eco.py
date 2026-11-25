"""Prueba unitaria de la compuerta antieco y helpers de conexión."""
import os
import queue
import time
import unittest

import kaya_live_audio
from kaya_live_audio import CompuertaAntiEco
import kaya_live_conexion
from kaya_live_conexion import es_error_cuota


class TestCompuertaAntiEco(unittest.TestCase):
    def test_ventana_eco_y_silenciado(self):
        q_out = queue.Queue()
        # Ventana de 150 ms para test rápido
        puerta = CompuertaAntiEco(modo_audifonos=False, eco_cola_ms=150.0, cola_salida=q_out)
        
        # Al inicio sin reproducir y sin cola: ventana eco = False
        self.assertFalse(puerta.esta_en_ventana_eco())
        chunk_in = b"\x05\x00" * 800
        res, sil = puerta.filtrar_chunk_entrada(chunk_in)
        self.assertEqual(res, chunk_in)
        self.assertFalse(sil)

        # 1. Durante reproducción activa (_reproduciendo_salida = True)
        puerta.marcar_inicio_escritura()
        self.assertTrue(puerta.esta_en_ventana_eco())
        res, sil = puerta.filtrar_chunk_entrada(chunk_in)
        self.assertEqual(res, bytes(len(chunk_in)))
        self.assertTrue(sil)

        # 2. Termina write(): debe seguir en ventana eco por 150 ms
        puerta.marcar_fin_escritura()
        self.assertTrue(puerta.esta_en_ventana_eco())
        res, sil = puerta.filtrar_chunk_entrada(chunk_in)
        self.assertEqual(res, bytes(len(chunk_in)))
        self.assertTrue(sil)

        # 3. Esperamos 180 ms: la ventana debe haber expirado
        time.sleep(0.18)
        self.assertFalse(puerta.esta_en_ventana_eco())
        res, sil = puerta.filtrar_chunk_entrada(chunk_in)
        self.assertEqual(res, chunk_in)
        self.assertFalse(sil)

    def test_modo_audifonos_desactivado(self):
        q_out = queue.Queue()
        puerta = CompuertaAntiEco(modo_audifonos=True, eco_cola_ms=300.0, cola_salida=q_out)
        puerta.marcar_inicio_escritura()
        # En modo audífonos NUNCA activa la ventana de eco
        self.assertFalse(puerta.esta_en_ventana_eco())
        chunk_in = b"\x10\x00" * 400
        res, sil = puerta.filtrar_chunk_entrada(chunk_in)
        self.assertEqual(res, chunk_in)
        self.assertFalse(sil)

    def test_helper_es_error_cuota(self):
        self.assertFalse(es_error_cuota(None))
        self.assertFalse(es_error_cuota(Exception("Connection timeout")))
        self.assertTrue(es_error_cuota(Exception("429 ResourceExhausted: Quota exceeded")))
        self.assertTrue(es_error_cuota(Exception("resource_exhausted: out of tokens")))
        self.assertTrue(es_error_cuota(Exception("Monthly quota reached")))

    def test_realtime_input_config_en_live_connect(self):
        class DummySesion:
            voz = "Achernar"
        cfg = kaya_live_conexion.crear_configuracion_live(DummySesion())
        self.assertIsNotNone(getattr(cfg, "realtime_input_config", None))
        aad = cfg.realtime_input_config.automatic_activity_detection
        self.assertIsNotNone(aad)
        self.assertEqual(aad.silence_duration_ms, 700)


if __name__ == "__main__":
    unittest.main()
