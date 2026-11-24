"""Pruebas unitarias para el módulo de búsqueda web en vivo con Tavily."""
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import agente_herramientas
import busqueda_web


class TestBusquedaWeb(unittest.TestCase):
    """Test suite para busqueda_web y su integración con agente_herramientas."""

    def test_limpieza_para_voz(self):
        """Verifica que se eliminen URLs, markdown, corchetes y citas."""
        texto_sucio = (
            "El precio de Bitcoin es $95,000 USD [1]. "
            "Más información en https://ejemplo.com/noticia y [fuente externa]. "
            "**Subió** un *5%* hoy #cripto."
        )
        limpio = busqueda_web._limpiar_para_voz(texto_sucio)
        self.assertNotIn("https://", limpio)
        self.assertNotIn("[1]", limpio)
        self.assertNotIn("[fuente externa]", limpio)
        self.assertNotIn("**", limpio)
        self.assertNotIn("#", limpio)
        self.assertIn("Bitcoin es $95,000 USD", limpio)

    def test_clave_vacia(self):
        """Sin clave de Tavily, devuelve mensaje corto y limpio sin excepciones."""
        with patch("config.TAVILY_API_KEY", "", create=True):
            res = busqueda_web.buscar_web("noticias hoy")
            self.assertIn("falta la clave de Tavily", res)

    def test_consulta_vacia(self):
        """Consulta vacía devuelve mensaje informativo."""
        res = busqueda_web.buscar_web("   ")
        self.assertIn("No indicaste ninguna consulta", res)

    def test_respuesta_exitosa_sin_urls(self):
        """Respuesta exitosa de Tavily se formatea sin URLs ni markdown."""
        mock_resp_data = {
            "answer": "La temperatura en Bogotá es de 18°C con cielo nublado [1].",
            "results": [
                {
                    "title": "Clima Bogotá",
                    "url": "https://weather.com/bogota",
                    "content": "Pronóstico extendido de lluvia para Bogotá https://weather.com/detalles.",
                }
            ],
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        with patch("config.TAVILY_API_KEY", "tvly-testkey-12345", create=True):
            with patch("urllib.request.urlopen", return_value=mock_cm):
                res = busqueda_web.buscar_web("clima en Bogotá")
                self.assertIn("temperatura en Bogotá es de 18°C", res)
                self.assertNotIn("https://", res)
                self.assertNotIn("[1]", res)

    def test_timeout_y_error_red(self):
        """Timeout o fallo de red se manejan de forma silenciosa y elegante."""
        with patch("config.TAVILY_API_KEY", "tvly-testkey-12345", create=True):
            with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
                res = busqueda_web.buscar_web("precio del dolar")
                self.assertIn("tiempo de espera", res)

            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
                "https://api.tavily.com/search", 401, "Unauthorized", {}, io.BytesIO()
            )):
                res_http = busqueda_web.buscar_web("noticias")
                self.assertIn("no disponible", res_http)

    def test_deteccion_en_agente_herramientas(self):
        """Verifica que agente_herramientas detecte intenciones web y no incluya prefijos técnicos."""
        intenciones = agente_herramientas.detectar_intencion("busca en internet las noticias de Colombia")
        herramientas = [h[0] for h in intenciones]
        self.assertIn("buscar_web", herramientas)

        intenciones_clima = agente_herramientas.detectar_intencion("cual es el clima en Cali")
        self.assertIn("buscar_web", [h[0] for h in intenciones_clima])

        # Verificar que responder_directo y limpiar_para_voz limpien prefijos
        with patch.dict(agente_herramientas.CATALOGO, {"buscar_web": lambda arg: "El clima en Cali es soleado"}):
            resp_dir = agente_herramientas.responder_directo("clima en Cali")
            self.assertIsNotNone(resp_dir)
            voz_limpia = agente_herramientas.limpiar_para_voz(resp_dir)
            self.assertFalse(voz_limpia.lower().startswith("datos reales:"))
            self.assertFalse(voz_limpia.lower().startswith("buscar_web:"))
            self.assertIn("El clima en Cali es soleado", voz_limpia)


if __name__ == "__main__":
    unittest.main()
