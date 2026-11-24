"""Pruebas unitarias para tts_aura_stream.py con mocks para streaming PCM, cancelación y fallback."""
import io
import unittest
from unittest.mock import MagicMock, patch

import tts_aura_stream as tas


class FakeResponse:
    def __init__(self, chunks, status_code=200):
        self.chunks = chunks
        self.status_code = status_code
        self.closed = False

    def iter_bytes(self):
        for c in self.chunks:
            if self.closed:
                break
            yield c

    def close(self):
        self.closed = True


class TestTtsAuraStream(unittest.TestCase):

    def setUp(self):
        self.pcm_16bit = b"\x00\x00\x10\x00\x20\x00\x00\x00" * 128  # 1024 bytes (múltiplo de 2)

    @patch("config.DEEPGRAM_API_KEY", "fake_key_12345")
    def test_stream_exitoso_y_chunks_impares(self):
        # 3 trozos donde los primeros tienen tamaño impar para probar ensamblado de bytes
        c1 = b"\x00\x00\x10"  # 3 bytes
        c2 = b"\x00\x20\x00\x00"  # 4 bytes -> total 7
        c3 = b"\x00"  # 1 byte -> total 8 bytes exactos
        fake_resp = FakeResponse([c1, c2, c3], status_code=200)

        iniciado = []
        niveles = []

        fake_stream = MagicMock()
        fake_stream.__enter__.return_value = fake_stream

        with patch.object(tas, "_obtener_cliente") as mock_cli, \
             patch("sounddevice.RawOutputStream", return_value=fake_stream):
            mock_client_inst = MagicMock()
            mock_client_inst.send.return_value = fake_resp
            mock_cli.return_value = mock_client_inst

            ok = tas.reproducir_stream_aura(
                "Hola mundo",
                cancelar_fn=lambda: False,
                al_iniciar=lambda: iniciado.append(True),
                al_nivel=lambda n: niveles.append(n),
            )

            self.assertTrue(ok)
            self.assertTrue(len(iniciado) > 0)
            self.assertTrue(len(niveles) > 0)
            self.assertTrue(fake_stream.write.called)

    @patch("config.DEEPGRAM_API_KEY", "fake_key_12345")
    def test_interrupcion_inmediata_por_cancelar_fn(self):
        fake_resp = FakeResponse([self.pcm_16bit, self.pcm_16bit], status_code=200)
        llamadas = [0]

        def check_cancelar():
            llamadas[0] += 1
            return llamadas[0] > 1  # cancela en el segundo trozo

        fake_stream = MagicMock()
        fake_stream.__enter__.return_value = fake_stream

        with patch.object(tas, "_obtener_cliente") as mock_cli, \
             patch("sounddevice.RawOutputStream", return_value=fake_stream):
            mock_client_inst = MagicMock()
            mock_client_inst.send.return_value = fake_resp
            mock_cli.return_value = mock_client_inst

            ok = tas.reproducir_stream_aura(
                "Texto largo que se cancela",
                cancelar_fn=check_cancelar,
            )

            # Debe retornar True indicando que fue cancelado limpiamente (no activar fallback)
            self.assertTrue(ok)
            self.assertTrue(fake_resp.closed)

    @patch("config.DEEPGRAM_API_KEY", "")
    def test_fallback_si_no_hay_clave(self):
        with patch.dict("os.environ", {}, clear=True):
            ok = tas.reproducir_stream_aura("Hola")
            self.assertFalse(ok)

    @patch("config.DEEPGRAM_API_KEY", "fake_key")
    def test_fallback_si_http_no_200(self):
        fake_resp = FakeResponse([], status_code=401)
        with patch.object(tas, "_obtener_cliente") as mock_cli:
            mock_client_inst = MagicMock()
            mock_client_inst.send.return_value = fake_resp
            mock_cli.return_value = mock_client_inst

            ok = tas.reproducir_stream_aura("Hola")
            self.assertFalse(ok)
            self.assertTrue(fake_resp.closed)

    @patch("config.DEEPGRAM_API_KEY", "fake_key")
    def test_fallback_si_sounddevice_falla(self):
        fake_resp = FakeResponse([self.pcm_16bit], status_code=200)
        with patch.object(tas, "_obtener_cliente") as mock_cli, \
             patch("sounddevice.RawOutputStream", side_effect=Exception("Dispositivo ocupado")):
            mock_client_inst = MagicMock()
            mock_client_inst.send.return_value = fake_resp
            mock_cli.return_value = mock_client_inst

            ok = tas.reproducir_stream_aura("Hola")
            self.assertFalse(ok)

    def test_intentar_stream_frase_respeta_local_primero(self):
        voz_mock = MagicMock()
        voz_mock.version = 1
        with patch("voz_local.debe_ir_local_primero", return_value=True):
            res = tas.intentar_stream_frase(voz_mock, "Prueba", 1, 1, None, None)
            self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
