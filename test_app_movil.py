"""Pruebas unitarias para la aplicación móvil PWA de Lyris (UI, voz bidireccional y Tailscale)."""
import json
import unittest
from unittest.mock import MagicMock, patch

import app_movil_audio as ama
import app_movil_ui as amui
import pantalla_remota_api as pra


class TestAppMovilPWA(unittest.TestCase):
    """Verifica renderizado de /movil, manifest.json y service worker."""

    def test_despachar_movil_html(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/movil")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(200)
        handler_mock.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")

    def test_despachar_manifest_json(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/manifest.json")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(200)
        handler_mock.send_header.assert_any_call("Content-Type", "application/manifest+json; charset=utf-8")
        manifest_data = json.loads(amui.MANIFEST_JSON)
        self.assertEqual(manifest_data["name"], "Lyris - Asistente Personal")
        self.assertEqual(manifest_data["display"], "standalone")

    def test_despachar_service_worker_js(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/sw.js")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(200)
        handler_mock.send_header.assert_any_call("Content-Type", "application/javascript; charset=utf-8")

    def test_despachar_iconos_png_pwa(self):
        for path, tam in [("/icon-192.png", 192), ("/icon-512.png", 512)]:
            handler_mock = MagicMock()
            ok = amui.despachar_get_movil(handler_mock, path)
            self.assertTrue(ok)
            handler_mock.send_response.assert_called_with(200)
            handler_mock.send_header.assert_any_call("Content-Type", "image/png")
            # Verificar firma de archivo PNG
            png_bytes = amui.generar_icono_png(tam)
            self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_despachar_descarga_certificado_ca(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/movil/cert.pem")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(200)
        handler_mock.send_header.assert_any_call("Content-Type", "application/x-pem-file")
        handler_mock.send_header.assert_any_call("Content-Disposition", 'attachment; filename="lyris_cert.pem"')

    def test_despachar_asistente_instalar_app(self):
        handler_mock = MagicMock()
        handler_mock.headers = {"Host": "192.168.1.100:8765"}
        ok = amui.despachar_get_movil(handler_mock, "/movil/instalar")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(302)
        handler_mock.send_header.assert_any_call("Location", "/movil")

    def test_despachar_movil_html_limpio_sin_8766(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/movil")
        self.assertTrue(ok)
        handler_mock.send_response.assert_called_with(200)
        escrito = b"".join(call[0][0] for call in handler_mock.wfile.write.call_args_list)
        self.assertNotIn(b"8766", escrito)

    def test_despachar_apk_o_redireccion(self):
        handler_mock = MagicMock()
        ok = amui.despachar_get_movil(handler_mock, "/movil/lyris.apk")
        self.assertTrue(ok)
        self.assertIn(handler_mock.send_response.call_args[0][0], (200, 302))


class TestSeguridadRedTailscaleYLAN(unittest.TestCase):
    """Verifica el soporte para Tailscale CGNAT (100.64.0.0/10) y subredes privadas."""

    def test_ip_tailscale_reconocida_como_cliente_permitido(self):
        # Rango Tailscale 100.64.0.0/10
        self.assertTrue(pra._es_lan_cliente("100.64.1.25"))
        self.assertTrue(pra._es_lan_cliente("100.100.100.100"))
        self.assertTrue(pra._es_lan_cliente("100.127.255.254"))

    def test_ip_lan_privada_reconocida(self):
        self.assertTrue(pra._es_lan_cliente("192.168.1.50"))
        self.assertTrue(pra._es_lan_cliente("10.0.0.15"))
        self.assertTrue(pra._es_lan_cliente("172.16.0.5"))
        self.assertTrue(pra._es_lan_cliente("127.0.0.1"))

    def test_ip_publica_externa_rechazada(self):
        self.assertFalse(pra._es_lan_cliente("8.8.8.8"))
        self.assertFalse(pra._es_lan_cliente("1.1.1.1"))
        self.assertFalse(pra._es_lan_cliente("200.50.10.1"))


class TestAudioYConversacionMovil(unittest.TestCase):
    """Verifica transcripción en memoria, llamada al cerebro y síntesis con Edge-TTS."""

    def test_procesar_comando_texto_movil(self):
        app_mock = MagicMock()
        app_mock.cerebro = MagicMock()
        app_mock.cola = MagicMock()

        with patch("respuesta_flujo.responder_flujo", return_value=("Hola, estoy lista.", None, "alegre")):
            with patch("app_movil_audio.sintetizar_respuesta_movil", return_value="base64audiofake"):
                res = ama.procesar_comando_texto_movil(app_mock, "¿Cómo estás, Lyris?", sintetizar_voz=True)

        self.assertTrue(res["ok"])
        self.assertEqual(res["texto_usuario"], "¿Cómo estás, Lyris?")
        self.assertEqual(res["respuesta"], "Hola, estoy lista.")
        self.assertEqual(res["emocion"], "alegre")
        self.assertEqual(res["audio_base64"], "base64audiofake")
        app_mock.cola.put.assert_any_call(("emocion", "alegre"))

    def test_procesar_audio_movil_flujo_completo(self):
        app_mock = MagicMock()
        app_mock.cerebro = MagicMock()
        fake_audio_bytes = b"OggS\x00\x02\x00\x00\x00\x00fakeaudiobytesforwhisper1234567890"

        with patch("app_movil_audio.transcribir_audio_memoria", return_value="activa modo mentora"):
            with patch("respuesta_flujo.responder_flujo", return_value=("Modo mentora socrática activado.", None, "concentrada")):
                with patch("app_movil_audio.sintetizar_respuesta_movil", return_value="base64voice"):
                    res = ama.procesar_audio_movil(app_mock, fake_audio_bytes, mime_type="audio/webm")

        self.assertTrue(res["ok"])
        self.assertEqual(res["texto_usuario"], "activa modo mentora")
        self.assertIn("Modo mentora", res["respuesta"])
        self.assertEqual(res["emocion"], "concentrada")
        self.assertEqual(res["audio_base64"], "base64voice")

    def test_manejar_http_voz_rechaza_tamano_excesivo(self):
        handler_mock = MagicMock()
        handler_mock.headers = {"Content-Type": "audio/webm", "Content-Length": "10485760"}  # 10 MB
        app_mock = MagicMock()

        code, data = ama.manejar_http_voz(handler_mock, app_mock)
        self.assertEqual(code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "audio_size_invalid")

    def test_manejar_http_chat_sincrono(self):
        handler_mock = MagicMock()
        payload = json.dumps({"texto": "¿Cómo está el sistema?", "hablar": False}).encode("utf-8")
        handler_mock.headers = {"Content-Type": "application/json", "Content-Length": str(len(payload))}
        handler_mock.rfile.read.return_value = payload
        app_mock = MagicMock()

        with patch("respuesta_flujo.responder_flujo", return_value=("Todo operativo.", None, "alegre")):
            code, data = ama.manejar_http_movil(handler_mock, app_mock, "/api/movil/chat")

        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["respuesta"], "Todo operativo.")
        self.assertEqual(data["emocion"], "alegre")

    def test_manejar_http_tts_endpoint(self):
        handler_mock = MagicMock()
        payload = json.dumps({"texto": "Hola, voz en segundo plano", "emocion": "alegre"}).encode("utf-8")
        handler_mock.headers = {"Content-Type": "application/json", "Content-Length": str(len(payload))}
        handler_mock.rfile.read.return_value = payload
        app_mock = MagicMock()

        with patch("app_movil_audio.sintetizar_respuesta_movil", return_value="fake_mp3_base64"):
            code, data = ama.manejar_http_movil(handler_mock, app_mock, "/api/movil/tts")

        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["audio_base64"], "fake_mp3_base64")
        self.assertEqual(data["mime"], "audio/mpeg")

    def test_sintetizar_respuesta_movil_filtra_tamano(self):
        try:
            ama.sintetizar_respuesta_movil._mock_audio = lambda t, e: b"pequeno"
            b64 = ama.sintetizar_respuesta_movil("hola", "neutral")
            self.assertEqual(b64, "")

            ama.sintetizar_respuesta_movil._mock_audio = lambda t, e: b"A" * 600
            b64 = ama.sintetizar_respuesta_movil("hola", "neutral")
            self.assertTrue(len(b64) > 10)
        finally:
            ama.sintetizar_respuesta_movil._mock_audio = None

    def test_html_movil_contiene_captura_token_url_y_replace_state(self):
        import app_movil_html as amh
        html = amh.PAGINA_MOVIL_HTML
        self.assertIn("history.replaceState", html)
        self.assertIn("URLSearchParams", html)
        self.assertIn("lyris_device_token", html)

    def test_html_movil_contiene_manejo_401_y_prompt_token(self):
        import app_movil_html as amh
        html = amh.PAGINA_MOVIL_HTML
        self.assertIn("fetchConToken", html)
        self.assertIn("pedirTokenPrompt", html)
        self.assertIn("401", html)
        self.assertIn("Ingresa el token de dispositivo de Lyris", html)


if __name__ == "__main__":
    unittest.main()
