"""Regresión: visión natural de pantalla, continuidad multi-turno y prompt Jarvis."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro
import cerebro_estilo
import cerebro_prompt
import respuesta_flujo
import vision_pantalla

FRASES = (
    "mira la pantalla",
    "puedes ver la pantalla",
    "qué errores encuentras",
    "qué ves aquí",
    "revisa mi código en pantalla",
    "analiza lo que tengo abierto",
    "Lyris, puedes ver la pantalla y decirme qué errores encuentras",
)


class TestCerebroVision(unittest.TestCase):
    def _cerebro(self):
        return SimpleNamespace(
            historial=[], app=SimpleNamespace(escuchando=False),
            instrucciones=lambda _t: "Eres Lyris.",
            _podar_historial=lambda: None,
        )

    def test_detector_cubre_peticiones_naturales(self):
        for frase in FRASES:
            with self.subTest(frase=frase):
                self.assertTrue(vision_pantalla.detectar_peticion_vision(frase))
        self.assertFalse(vision_pantalla.detectar_peticion_vision(
            "dime qué hora es y abre el bloc"))

    def test_frase_natural_fuerza_captura_y_modelo_multimodal(self):
        cerebro_falso = self._cerebro()
        frase = FRASES[-1]
        with patch.object(vision_pantalla, "capturar_y_analizar_pantalla",
                          return_value=(True, "Veo un SyntaxError en la línea 4")
                          ) as captura, \
             patch.object(respuesta_flujo.proveedores, "completar_flujo",
                          side_effect=AssertionError("No debe ir al LLM sin imagen")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro_falso, frase, lambda _frase: None)
        captura.assert_called_once()
        self.assertIn("errores", captura.call_args.args[0])
        self.assertIn("SyntaxError", resultado[0])
        self.assertEqual(len(cerebro_falso.historial), 2)

    def test_continuidad_multi_turno_y_memoria_ampliada(self):
        cerebro_falso = self._cerebro()
        with patch.object(vision_pantalla, "capturar_y_analizar_pantalla",
                          return_value=(True, "Veo un error de importación")):
            respuesta_flujo.responder_flujo(
                cerebro_falso, "mira la pantalla", lambda _f: None)
            respuesta_flujo.responder_flujo(
                cerebro_falso, "y ahora qué errores encuentras", lambda _f: None)
        self.assertEqual(len(cerebro_falso.historial), 4)
        self.assertIn("mira la pantalla", cerebro_falso.historial[0]["content"])
        self.assertEqual(cerebro_falso.historial[-1]["content"],
                         "Veo un error de importación")

        real = cerebro.Cerebro(cliente=None, memoria=SimpleNamespace())
        real.historial = [{"role": "user" if i % 2 == 0 else "assistant",
                           "content": f"turno {i}"} for i in range(12)]
        real._podar_historial()
        self.assertEqual(len(real._obtener_historial_podado()), 8)

    def test_prompt_incluye_directiva_jarvis_y_contexto(self):
        self.assertIn("COPILOTO TÉCNICO EJECUTIVO", cerebro_estilo.directiva_estilo())
        memoria = SimpleNamespace(hechos=[], creador="Moisés", nombre="Lyris",
                                  proposito="ayudar")
        prompt = cerebro_prompt.construir_prompt(
            memoria, texto_actual="mira la pantalla",
            contexto_adicional="[TELEMETRÍA] batería 80%")
        self.assertIn("COPILOTO TÉCNICO EJECUTIVO", prompt)
        self.assertIn("telemetría", prompt)
        self.assertIn("[TELEMETRÍA] batería 80%", prompt)


if __name__ == "__main__":
    unittest.main()
