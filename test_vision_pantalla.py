"""Pruebas unitarias para visión de pantalla bajo demanda con Gemini Flash."""
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import agente_herramientas
import vision_pantalla


class TestVisionPantalla(unittest.TestCase):
    """Pruebas de captura en memoria, llamadas REST a Gemini, limpieza y herramientas."""

    def test_clave_vacia(self):
        """Sin clave de Google Gemini devuelve mensaje claro sin lanzar excepción."""
        with patch("config.CLAVE_GOOGLE", "", create=True):
            with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy"):
                res = vision_pantalla.analizar_pantalla("qué ves")
                self.assertIn("falta la clave de Google Gemini", res)

    def test_captura_y_llamada_exitosa_gemini(self):
        """Llamada exitosa a Gemini devuelve texto limpio de markdown y URLs."""
        mock_data = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Tienes abierto VS Code con un error de sintaxis en `app.py` [1]. Visita https://docs.python.org para más detalles."}]
                }
            }]
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        with patch("config.CLAVE_GOOGLE", "google-gemini-testkey", create=True):
            with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy"):
                with patch("urllib.request.urlopen", return_value=mock_cm):
                    res = vision_pantalla.analizar_pantalla("qué error sale aquí")
                    self.assertIn("Tienes abierto VS Code", res)
                    self.assertNotIn("https://", res)
                    self.assertNotIn("[1]", res)
                    self.assertNotIn("`", res)

    def test_fallback_segundo_modelo(self):
        """Si el primer modelo falla con HTTP 404, continúa al segundo exitosamente."""
        mock_data_ok = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "El proceso de compilación terminó correctamente sin advertencias."}]
                }
            }]
        }
        mock_cm_ok = MagicMock()
        mock_cm_ok.read.return_value = json.dumps(mock_data_ok).encode("utf-8")
        mock_cm_ok.__enter__.return_value = mock_cm_ok

        def urlopen_side_effect(req, timeout=None):
            if "gemini-2.5-flash" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO())
            return mock_cm_ok

        with patch("config.CLAVE_GOOGLE", "google-gemini-testkey", create=True):
            with patch("config.MODELOS_VISION", ["gemini-2.5-flash", "gemini-2.0-flash"], create=True):
                with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy"):
                    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
                        res = vision_pantalla.analizar_pantalla("mira mi pantalla")
                        self.assertIn("proceso de compilación terminó correctamente", res)

    def test_timeout_seguro(self):
        """Timeout de red se maneja de forma limpia sin romper el flujo."""
        with patch("config.CLAVE_GOOGLE", "google-gemini-testkey", create=True):
            with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy"):
                with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
                    res = vision_pantalla.analizar_pantalla("qué ves")
                    self.assertIn("No pude obtener una respuesta visual", res)

    def test_deteccion_en_agente_herramientas(self):
        """Verifica que agente_herramientas detecte intenciones de pantalla y limpie la voz."""
        frases = [
            "Lyris, mira mi pantalla por favor",
            "qué ves en mi pantalla",
            "qué error sale aquí",
            "analiza la pantalla",
        ]
        for f in frases:
            intenciones = agente_herramientas.detectar_intencion(f)
            herramientas = [h[0] for h in intenciones]
            self.assertIn("ver_pantalla", herramientas, f"Fallo al detectar en frase: {f}")

        # Ejecución y respuesta hablada sin prefijos
        with patch.dict(agente_herramientas.CATALOGO, {"ver_pantalla": lambda arg: "Tienes abierto el terminal con git status"}):
            resp = agente_herramientas.responder_directo("mira mi pantalla")
            self.assertIsNotNone(resp)
            limpio = agente_herramientas.limpiar_para_voz(resp)
            self.assertFalse(limpio.lower().startswith("datos reales:"))
            self.assertFalse(limpio.lower().startswith("ver_pantalla:"))
            self.assertIn("Tienes abierto el terminal", limpio)


if __name__ == "__main__":
    unittest.main()
