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

    def test_procesar_frase_productor_salta_edge_tts_si_aura_activo(self):
        voz_mock = MagicMock()
        voz_mock._audio.return_value = b"edge_audio"

        with patch.object(tas, "aura_disponible", return_value=True), \
             patch("voz_cache.obtener_audio_cache", return_value=None), \
             patch("voz_local.debe_ir_local_primero", return_value=False):
            # Debe devolver None (sin sintetizar con Edge-TTS por adelantado)
            res = tas.procesar_frase_productor(voz_mock, "Hola mundo", "neutral")
            self.assertIsNone(res)
            self.assertFalse(voz_mock._audio.called)

        # Si Aura NO está disponible, sí debe llamar a pre-síntesis
        with patch.object(tas, "aura_disponible", return_value=False), \
             patch("voz_cache.obtener_audio_cache", return_value=None), \
             patch("voz_local.debe_ir_local_primero", return_value=False):
            res = tas.procesar_frase_productor(voz_mock, "Hola mundo", "neutral")
            self.assertEqual(res, b"edge_audio")
            self.assertTrue(voz_mock._audio.called)

    def test_micro_cache_biometria_dueno(self):
        import numpy as np
        import voz_dueno

        vd = voz_dueno.VozDueno(app=MagicMock())
        vd.activa = True
        vd.banco_dueno = np.ones((5, 192), dtype=np.float32)

        # Buffer simulado
        audio_sim = np.sin(np.linspace(0, 100, 16000 * 3, dtype=np.float32))
        vd.app.oido.ultimo_audio = audio_sim
        vd.app.oido.duracion_ultimo_audio = 3.0

        with patch("voz_dueno.preparar_audio_biometria", return_value=(audio_sim, 3.0)) as mock_prep, \
             patch("voz_dueno.extraer_embedding", return_value=np.ones(192, dtype=np.float32)) as mock_emb, \
             patch("voz_dueno.calcular_similitud_banco", return_value=(0.85, 0.85, 5)) as mock_sim:

            # 1. Primera inferencia
            vd.evaluar_entrada_voz("hola")
            self.assertEqual(mock_emb.call_count, 1)
            self.assertTrue(vd.ultima_verificacion["es_dueno"])

            # 2. Segunda inferencia inmediata con el mismo audio
            vd.evaluar_entrada_voz("hola de nuevo")
            # El extractor CAM++ no debe llamarse una segunda vez
            self.assertEqual(mock_emb.call_count, 1)
            self.assertTrue(vd.ultima_verificacion["es_dueno"])


if __name__ == "__main__":
    unittest.main()
