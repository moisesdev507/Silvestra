"""Pruebas unitarias para kaya_live_web.py y la suite PWA."""
import os
import unittest
from unittest.mock import MagicMock

import kaya_live_nucleo
import kaya_live_web


class TestKayaLiveWeb(unittest.TestCase):

    def test_archivos_pwa_existen(self):
        """Verifica que todos los archivos estáticos de la PWA existan y tengan contenido."""
        archivos = ["index.html", "app.js", "styles.css", "manifest.json"]
        for arch in archivos:
            ruta = os.path.join(kaya_live_web.RUTA_WEB, arch)
            self.assertTrue(os.path.exists(ruta), f"Falta {arch}")
            self.assertGreater(os.path.getsize(ruta), 50, f"{arch} está vacío")

    def test_instanciacion_servidor_web(self):
        """Verifica la configuración de rutas en aiohttp."""
        servidor = kaya_live_web.ServidorKayaLiveWeb(puerto=9876)
        rutas = [r.resource.canonical for r in servidor.app.router.routes() if r.resource]
        self.assertIn("/", rutas)
        self.assertIn("/ws/live", rutas)

    def test_inyectar_audio_pcm16_nucleo(self):
        """Verifica que inyectar_audio_pcm16 encole datos en la cola sin errores."""
        sesion = kaya_live_nucleo.SesionKayaLive(audio_local=False)
        cola_mock = MagicMock()
        loop_mock = MagicMock()
        sesion._cola_entrada = cola_mock
        sesion._loop = loop_mock

        chunk = b"\x00\x00" * 100
        sesion.inyectar_audio_pcm16(chunk)

        loop_mock.call_soon_threadsafe.assert_called_once_with(cola_mock.put_nowait, chunk)

    def test_verificar_web(self):
        """Verifica la función de auto-comprobación del servidor web."""
        self.assertTrue(kaya_live_web.verificar_web())


if __name__ == "__main__":
    unittest.main()
