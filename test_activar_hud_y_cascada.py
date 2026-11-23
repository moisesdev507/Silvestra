"""Pruebas unitarias para la acción activar_hud, detección rápida y cascada Groq rápida."""
import unittest
from unittest.mock import MagicMock, patch

import acciones
import pantalla_remota_accion as pra
import proveedores_cadenas as pc


class TestActivarHudYCascada(unittest.TestCase):
    def test_detectar_orden_hud_variantes(self):
        casos_positivos = [
            "activa el hud",
            "activar hud",
            "Activa la pantalla notable",
            "Activa el HUD en la tabla",
            "Les activa el HVD",
            "activa la pantalla de la tablet",
            "activa pantalla remota",
            "conecta la tablet",
            "conectar tablet",
            "abre el hud",
            "abrir hud",
            "inicia el hud",
            "abrir la tablet",
        ]
        for caso in casos_positivos:
            self.assertTrue(pra.detectar_orden_hud(caso), f"Falló en caso positivo: {caso}")

        casos_negativos = [
            "Dime como esta el clima hoy",
            "Hola Lyris, como estas?",
            "Que hora es en Panama",
            "Cuentame un chiste",
            "pon musica de rock",
        ]
        for caso in casos_negativos:
            self.assertFalse(pra.detectar_orden_hud(caso), f"Falso positivo en: {caso}")

    def test_activar_hud_levanta_servidor_y_retorna_url(self):
        mock_app = MagicMock()
        mock_gestor = MagicMock()
        mock_gestor._servidor = None
        mock_gestor.obtener_url_completa.return_value = "https://192.168.0.7:8765/"
        mock_app.pantalla_remota = mock_gestor
        mock_app.cola = MagicMock()

        with patch("os.path.exists", return_value=True):
            res = pra.activar_hud(app=mock_app)

        self.assertIn("192.168.0.7:8765", res)
        mock_gestor.activar_red_tls.assert_called_with("hud_cert.pem", "hud_key.pem", "0.0.0.0")
        mock_gestor.registrar_evento.assert_called()

    def test_acciones_ejecutar_activar_hud(self):
        mock_app = MagicMock()
        mock_gestor = MagicMock()
        mock_gestor._servidor = MagicMock()
        mock_gestor.obtener_url_completa.return_value = "https://192.168.0.7:8765/"
        mock_app.pantalla_remota = mock_gestor
        pra.fijar_app(mock_app)

        ok, msg = acciones.ejecutar("activar_hud")
        self.assertTrue(ok)

        ok_alias, _ = acciones.ejecutar("abrir_hud")
        self.assertTrue(ok_alias)

    def test_groq_prioriza_modelos_vivos(self):
        prov = {
            "nombre": "Groq",
            "modelos": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
            "modelos_charla": ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"],
        }
        from unittest.mock import patch
        with patch("proveedores_validador.esta_desactivado", return_value=False):
            mods = pc.obtener_modelos_tarea(prov, "charla")
        self.assertEqual(mods[0], "openai/gpt-oss-120b")
        self.assertIn("qwen/qwen3.8-27b", mods)
        self.assertNotIn("llama-3.1-8b-instant", mods)
        self.assertNotIn("llama-3.3-70b-versatile", mods)


if __name__ == "__main__":
    unittest.main()
