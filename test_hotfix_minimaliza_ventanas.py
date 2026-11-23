"""Regresión: 'minimaliza' se resuelve a minimizar_todo sin carencia falsa."""
import unittest
from types import SimpleNamespace

import acciones
import main
import respuesta_flujo


class TestMinimalizaVentanas(unittest.TestCase):
    def setUp(self):
        self.original = acciones.VIVAS.get("minimizar_todo")
        self.ejecutadas = []
        acciones.registrar(
            "minimizar_todo",
            lambda: self.ejecutadas.append("minimizar_todo") or (True, "Listo."),
            "minimiza todas las ventanas",
        )
        self.carencias = []
        self.app = SimpleNamespace(
            puede_hablar_sola=lambda: True,
            cara=SimpleNamespace(decir=lambda *_a, **_k: None),
            propuestas=SimpleNamespace(
                detectar_carencia_accion=lambda n: self.carencias.append(n)),
        )
        self.cerebro = SimpleNamespace(
            historial=[], app=self.app,
            instrucciones=lambda _t: "sistema",
            _podar_historial=lambda: None,
        )

    def tearDown(self):
        if self.original is None:
            acciones.VIVAS.pop("minimizar_todo", None)
        else:
            acciones.VIVAS["minimizar_todo"] = self.original

    def test_detecta_variantes_whisper_y_no_negaciones(self):
        for texto in ("Minimaliza las ventanas, por favor.",
                      "Liris, minimaliza la ventana actual, por favor."):
            self.assertTrue(acciones.es_minimizar(texto), texto)
        self.assertFalse(acciones.es_minimizar("No minimices la ventana."))
        self.assertFalse(acciones.es_minimizar("¿Qué ves en la ventana?"))

    def test_alias_del_llm_no_dispara_carencia(self):
        main.Silvestra.ejecutar(self.app, "minimizar_ventanas")
        self.assertEqual(self.ejecutadas, ["minimizar_todo"])
        self.assertEqual(self.carencias, [])

    def test_textos_del_usuario_resuelven_y_ejecutan_sin_carencia(self):
        textos = ("Minimaliza las ventanas, por favor.",
                  "Liris, minimaliza la ventana actual, por favor.")
        for texto in textos:
            respuesta, accion, emocion = respuesta_flujo.responder_flujo(
                self.cerebro, texto, lambda _frase: None)
            self.assertEqual(accion, "minimizar_todo")
            self.assertIn("minimiz", respuesta.lower())
            self.assertEqual(emocion, "alegre")
            main.Silvestra.ejecutar(self.app, accion)
        self.assertEqual(self.ejecutadas, ["minimizar_todo", "minimizar_todo"])
        self.assertEqual(self.carencias, [])


if __name__ == "__main__":
    unittest.main()
