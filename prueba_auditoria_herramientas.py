"""Pruebas de paridad de herramientas y visión de pantalla en ambos motores."""
import asyncio
import base64
import unittest
from unittest.mock import patch

import acciones
import capacidades_extra
import live_audio
import live_herramientas
import live_herramientas_extra
import vision_compartida


class TestAuditoriaHerramientas(unittest.TestCase):

    def test_declaraciones_live_incluyen_capacidades_nuevas(self):
        tools = live_herramientas.declarar_declaraciones_herramientas()
        nombres = {f.name for f in tools[0].function_declarations}
        for esperado in (
            "revisar_pantalla", "leer_portapapeles", "listar_ventanas",
            "ventana_activa", "listar_procesos", "activar_hud",
            "control_multimedia",
        ):
            self.assertIn(esperado, nombres)

    def test_revisar_pantalla_con_genai(self):
        with patch.object(vision_compartida, "_clave", return_value="clave"), \
             patch("vision_pantalla.es_modo_privado", return_value=False), \
             patch("vision_pantalla.capturar_pantalla_b64", return_value="abc"), \
             patch.object(vision_compartida, "_analizar_genai",
                          return_value="Veo Chrome abierto con un error."):
            res = vision_compartida.revisar_pantalla("lee el error")
        self.assertIn("Chrome", res)

    def test_revisar_pantalla_fallback_rest(self):
        with patch.object(vision_compartida, "_clave", return_value=""), \
             patch("vision_pantalla.es_modo_privado", return_value=False), \
             patch("vision_pantalla.capturar_pantalla_b64", return_value="abc"), \
             patch("vision_pantalla.analizar_pantalla",
                   return_value="Veo el escritorio."):
            res = vision_compartida.revisar_pantalla()
        self.assertEqual(res, "Veo el escritorio.")

    def test_revisar_pantalla_modo_privado(self):
        with patch("vision_pantalla.es_modo_privado", return_value=True):
            res = vision_compartida.revisar_pantalla()
        self.assertIn("Privado", res)

    def test_despacho_live_revisar_pantalla(self):
        with patch.object(capacidades_extra, "revisar_pantalla",
                          return_value="Veo Visual Studio Code."):
            res = asyncio.run(
                live_herramientas_extra.despachar(
                    "revisar_pantalla", {"pregunta": "qué hay"}
                )
            )
        self.assertIn("Visual Studio", res)

    def test_accion_clasica_revisar_pantalla(self):
        with patch.object(capacidades_extra, "revisar_pantalla",
                          return_value="Veo una terminal."):
            ok, msg = acciones.ejecutar("revisar_pantalla", "lee la pantalla")
        self.assertTrue(ok)
        self.assertIn("terminal", msg)

    def test_deteccion_clasica_ventanas(self):
        with patch.object(capacidades_extra, "listar_ventanas",
                          return_value="Ventanas abiertas: Chrome."):
            res = capacidades_extra.detectar_y_ejecutar(
                "¿qué ventanas tengo abiertas?"
            )
        self.assertIn("Chrome", res)

    def test_deteccion_clasica_procesos(self):
        with patch.object(capacidades_extra, "listar_procesos",
                          return_value="Procesos activos: python."):
            res = capacidades_extra.detectar_y_ejecutar(
                "¿qué procesos están corriendo?"
            )
        self.assertIn("python", res)

    def test_portapapeles_compartido(self):
        with patch("portapapeles.leer_portapapeles", return_value="texto copiado"):
            res = capacidades_extra.leer_portapapeles()
        self.assertIn("texto copiado", res)

    def test_instruccion_live_autoriza_pantalla(self):
        texto = live_audio.construir_instruccion_sistema()
        self.assertIn("revisar_pantalla", texto)
        self.assertIn("pantalla", texto.lower())
        rapido = live_audio.construir_instruccion_arranque_rapido()
        self.assertIn("revisar_pantalla", rapido)

    def test_ejecutar_accion_local_usa_capacidades_extra(self):
        with patch.object(live_herramientas_extra, "ejecutar_por_texto",
                          return_value="Ventanas abiertas: Edge."):
            res = live_herramientas.ejecutar_accion_local(
                "qué ventanas tengo abiertas"
            )
        self.assertIn("Edge", res)

    def test_control_multimedia_delegado(self):
        with patch("control_laptop.multimedia") as mock_media:
            res = capacidades_extra.control_multimedia("pausa la música")
        self.assertIn("reproducción", res)
        mock_media.assert_called_once()

    def test_vision_compartida_usa_captura_en_memoria(self):
        with patch.object(vision_compartida, "_clave", return_value=""), \
             patch("vision_pantalla.es_modo_privado", return_value=False), \
             patch("vision_pantalla.capturar_pantalla_b64",
                   return_value=base64.b64encode(b"jpeg").decode()) as mock_cap, \
             patch("vision_pantalla.analizar_pantalla", return_value="ok"):
            vision_compartida.revisar_pantalla()
        mock_cap.assert_called_once()


if __name__ == "__main__":
    unittest.main()
