"""Pruebas unitarias para kaya_live_nucleo.py y kaya_live_tools.py."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import kaya_live_nucleo
import kaya_live_tools


class TestKayaLiveNucleo(unittest.TestCase):

    def setUp(self):
        kaya_live_tools.controlar_ojos(True)

    def test_construccion_instruccion_sistema(self):
        """Verifica que construir_instruccion_sistema incluya alma, guía vocal y temas."""
        instr = kaya_live_nucleo.construir_instruccion_sistema()
        self.assertIn("Kaya", instr)
        self.assertIn("Guía de actuación vocal", instr)
        self.assertIn("español latinoamericano", instr.lower())

    def test_voz_por_defecto_es_achernar(self):
        """Verifica que la voz por defecto del núcleo sea Achernar."""
        self.assertEqual(kaya_live_nucleo.VOZ_DEFECTO, "Achernar")
        sesion = kaya_live_nucleo.SesionKayaLive()
        self.assertEqual(sesion.voz, "Achernar")

    def test_privacidad_controlar_ojos_bloquea_vision(self):
        """Verifica que controlar_ojos(False) impida ver pantalla y cámara."""
        self.assertTrue(kaya_live_tools.obtener_estado_ojos())
        resp_ctrl = kaya_live_tools.controlar_ojos(False)
        self.assertIn("cerrados", resp_ctrl)
        self.assertFalse(kaya_live_tools.obtener_estado_ojos())

        res_pantalla = kaya_live_tools.ver_pantalla("¿Qué ves?")
        self.assertIn("ojos cerrados", res_pantalla.lower())

        res_camara = kaya_live_tools.ver_camara_pc("¿Quién está?")
        self.assertIn("ojos cerrados", res_camara.lower())

        resp_abrir = kaya_live_tools.controlar_ojos(True)
        self.assertIn("abiertos", resp_abrir)
        self.assertTrue(kaya_live_tools.obtener_estado_ojos())

    def test_consultar_sistema_devuelve_metricas(self):
        """Verifica que consultar_sistema retorne fecha y telemetría de CPU/RAM."""
        res = kaya_live_tools.consultar_sistema()
        self.assertIn("Fecha y hora", res)
        self.assertTrue("Estado del equipo" in res or "CPU" in res)

    def test_despachar_herramienta_asincrona(self):
        """Verifica el despacho asíncrono y seguro de tools."""
        async def run_despacho():
            r1 = await kaya_live_tools.despachar_herramienta("consultar_sistema", {})
            self.assertIn("resultado", r1)
            self.assertIn("Fecha", r1["resultado"])

            r2 = await kaya_live_tools.despachar_herramienta("controlar_ojos", {"activo": False})
            self.assertIn("resultado", r2)
            self.assertIn("cerrados", r2["resultado"])

            r3 = await kaya_live_tools.despachar_herramienta("herramienta_fantasma", {})
            self.assertIn("no encontrada", r3["resultado"])

        asyncio.run(run_despacho())

    @patch("busqueda_web.buscar_web", return_value={"results": [{"title": "Noticias", "content": "Sol en Panamá"}]})
    def test_buscar_en_web_formatea_resultados(self, mock_buscar):
        """Verifica que buscar_en_web procese y retorne texto digerible."""
        res = kaya_live_tools.buscar_en_web("clima en Panama")
        self.assertIn("Noticias", res)
        self.assertIn("Sol en Panamá", res)
        mock_buscar.assert_called_once_with("clima en Panama")

    def test_corte_inmediato_ante_1011(self):
        """Verifica que ante un error 1011 en session.receive() el bucle corte de inmediato."""
        sesion = kaya_live_nucleo.SesionKayaLive()
        sesion._evento_parada_async = asyncio.Event()

        class MockSessionError:
            def receive(self):
                async def _gen():
                    if False:
                        yield None
                    raise Exception("1011 (internal error) Internal error occurred")
                return _gen()

        sesion._session = MockSessionError()

        async def run_test():
            with self.assertRaises(Exception) as ctx:
                await sesion._recepcion_servidor()
            self.assertIn("1011", str(ctx.exception))

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
