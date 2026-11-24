"""Pruebas unitarias para tolerancia fonética y parada de baile en invocacion_lyris."""
import unittest

import invocacion_lyris as il


class TestInvocacionBaile(unittest.TestCase):
    """Pruebas de tolerancia fonética ("Viris", "Libres", "Liernes") y parada directa de baile."""

    def test_tolerancia_fonetica_fuertes(self):
        """'viris', 'liris', 'lyrys' disparan como invocación normal en cualquier posición."""
        dispara, var, orden = il.detectar("Viris")
        self.assertTrue(dispara)
        self.assertEqual(var, "viris")

        dispara2, var2, orden2 = il.detectar("oye viris qué hora es")
        self.assertTrue(dispara2)
        self.assertEqual(var2, "viris")
        self.assertIn("hora", orden2)

        dispara3, var3, orden3 = il.detectar("lyrys, para de bailar")
        self.assertTrue(dispara3)
        self.assertEqual(var3, "lyrys")
        self.assertEqual(orden3, "para de bailar")

    def test_tolerancia_fonetica_debiles_al_inicio_o_aisladas(self):
        """'libres' o 'liernes' disparan al inicio o aisladas, pero NO en medio de frases normales."""
        # 1. Al inicio de la orden (típica transcripción fonética errada)
        dispara, var, orden = il.detectar("Libres, para de bailar")
        self.assertTrue(dispara)
        self.assertEqual(var, "libres")
        self.assertEqual(orden, "para de bailar")

        # 2. Invocación aislada
        dispara2, var2, orden2 = il.detectar("Liernes")
        self.assertTrue(dispara2)
        self.assertEqual(var2, "liernes")
        self.assertEqual(orden2, "")

        # 3. Frase normal que contiene "somos libres" NO debe disparar invocación falsa
        dispara3, var3, orden3 = il.detectar("en este país todos somos libres de opinar")
        self.assertFalse(dispara3)
        self.assertEqual(var3, "")

    def test_parada_directa_de_baile_sin_nombre(self):
        """Si la cara está en modo baile, órdenes directas como 'para de bailar' detienen sin decir Lyris."""
        # Sin modo baile activo, "para de bailar" sin nombre no dispara invocación
        dispara_no_baile, _, _ = il.detectar("para de bailar", en_baile=False)
        self.assertFalse(dispara_no_baile)

        # Con modo baile activo (en_baile=True), dispara inmediatamente
        dispara_baile, var, orden = il.detectar("para de bailar", en_baile=True)
        self.assertTrue(dispara_baile)
        self.assertEqual(var, "baile_stop")
        self.assertEqual(orden, "para de bailar")

        dispara_stop, var_s, _ = il.detectar("stop", en_baile=True)
        self.assertTrue(dispara_stop)

        dispara_detente, var_d, _ = il.detectar("detente", en_baile=True)
        self.assertTrue(dispara_detente)

    def test_orden_antes_y_despues_de_lyris(self):
        """Verifica que la orden se capture correctamente esté antes, después o rodeando a Lyris."""
        # 1. Orden ANTES de la invocación
        dispara1, var1, orden1 = il.detectar("Preséntate, Lyris")
        self.assertTrue(dispara1)
        self.assertEqual(var1, "lyris")
        self.assertIn("presentate", orden1.lower().replace("é", "e"))

        dispara2, var2, orden2 = il.detectar("Baila salsa, Lyris")
        self.assertTrue(dispara2)
        self.assertEqual(var2, "lyris")
        self.assertEqual(orden2, "baila salsa")

        dispara3, var3, orden3 = il.detectar("Qué hora es, Lyris")
        self.assertTrue(dispara3)
        self.assertEqual(var3, "lyris")
        self.assertIn("hora", orden3)

        # 2. Lyris sola -> orden vacía (dispara "¿Sí?" en el flujo)
        dispara_sola, var_s, orden_s = il.detectar("Lyris")
        self.assertTrue(dispara_sola)
        self.assertEqual(var_s, "lyris")
        self.assertEqual(orden_s, "")

        # 3. Orden después de Lyris
        dispara_post, var_p, orden_p = il.detectar("Lyris, cuéntame un chiste")
        self.assertTrue(dispara_post)
        self.assertEqual(var_p, "lyris")
        self.assertIn("chiste", orden_p)

    def test_deepgram_y_whisper_configuracion(self):
        """Verifica que Deepgram use es-419 y Whisper incluya el prompt contextual."""
        import oido
        import oido_deepgram
        import oido_stream
        from unittest.mock import patch, MagicMock

        # Verificar URL_WS de oido_stream
        self.assertIn("language=es-419", oido_stream.URL_WS)

        # Verificar parámetros HTTP en oido_deepgram
        llamadas_post = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": {"channels": [{"alternatives": [{"transcript": "hola"}]}]}}

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            with patch("config.DEEPGRAM_API_KEY", "fake_key", create=True):
                oido_deepgram.transcribir(b"fake_wav_data")
                self.assertTrue(mock_post.called)
                params = mock_post.call_args[1].get("params", {})
                self.assertEqual(params.get("language"), "es-419")

        # Verificar prompt enriquecido de Whisper
        self.assertIn("español latinoamericano", oido.PROMPT_WHISPER)
        self.assertIn("preséntate", oido.PROMPT_WHISPER)


if __name__ == "__main__":
    unittest.main()
