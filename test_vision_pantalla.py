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

    def test_cadena_modelos_ignora_no_gemini_y_prioriza_lite(self):
        """Verifica que modelos no-gemini o de audio se ignoren y gemini-flash-lite-latest sea primero."""
        with patch("config.MODELOS_VISION", ["qwen/qwen3.8-27b", "gemini-tts-1", "llama-3.2-11b", "gemini-1.5-pro"], create=True):
            modelos = vision_pantalla._obtener_modelos_candidatos()
            self.assertEqual(modelos[0], "gemini-flash-lite-latest")
            self.assertIn("gemini-3.1-flash-lite", modelos)
            self.assertIn("gemini-1.5-pro", modelos)
            self.assertNotIn("qwen/qwen3.8-27b", modelos)
            self.assertNotIn("llama-3.2-11b", modelos)
            self.assertNotIn("gemini-tts-1", modelos)

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
            with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy") as mock_cap:
                with patch("urllib.request.urlopen", return_value=mock_cm):
                    res = vision_pantalla.analizar_pantalla("qué error sale aquí")
                    self.assertIn("Tienes abierto VS Code", res)
                    self.assertNotIn("https://", res)
                    self.assertNotIn("[1]", res)
                    self.assertNotIn("`", res)
                    mock_cap.assert_called_with(ancho_max=960, calidad=60)

    def test_fallback_respuesta_sin_parts_o_http_error(self):
        """Si un modelo responde sin 'parts' o da HTTP 404/429/503, pasa al siguiente sin fallar."""
        mock_sin_parts = {"candidates": [{"content": {}}]}
        mock_cm_sin_parts = MagicMock()
        mock_cm_sin_parts.read.return_value = json.dumps(mock_sin_parts).encode("utf-8")
        mock_cm_sin_parts.__enter__.return_value = mock_cm_sin_parts

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

        intentos = []

        def urlopen_side_effect(req, timeout=None):
            intentos.append(req.full_url)
            if "gemini-flash-lite-latest" in req.full_url:
                # Primer modelo responde sin parts
                return mock_cm_sin_parts
            if "gemini-3.1-flash-lite" in req.full_url:
                # Segundo modelo da error HTTP 429
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO())
            # Tercer modelo responde OK
            return mock_cm_ok

        with patch("config.CLAVE_GOOGLE", "google-gemini-testkey", create=True):
            with patch("vision_pantalla.capturar_pantalla_b64", return_value="base64dummy"):
                with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
                    res = vision_pantalla.analizar_pantalla("mira mi pantalla")
                    self.assertIn("proceso de compilación terminó correctamente", res)
                    self.assertTrue(len(intentos) >= 3)

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
