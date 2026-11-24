"""Pruebas unitarias para el enrutador de expertos y cartuchos de programación/matemáticas."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import enrutador_expertos as ee
from expertos import obtener_cartucho, REGISTRO_EXPERTOS


class TestEnrutadorExpertos(unittest.TestCase):
    """Test suite para clasificación de áreas, carril pesado, cartuchos y modelos."""

    def test_clasificacion_general_charla(self):
        """Charla cotidiana, saludos y preguntas comunes se quedan en general y rapido sin prompt experto."""
        consultas_generales = [
            "Hola Lyris, ¿cómo estás?",
            "¿Qué hora es?",
            "Dime las noticias de hoy",
            "¿Va a llover esta tarde en la ciudad?",
            "Abre el bloc de notas",
        ]
        for q in consultas_generales:
            c = ee.clasificar_consulta(q)
            self.assertEqual(c["area"], "general", f"Fallo en: {q}")
            self.assertEqual(c["carril"], "rapido")
            self.assertEqual(c["prompt_experto"], "")

    def test_clasificacion_programacion(self):
        """Consultas con código, bugs o arquitectura enrutan a programación y carril pesado."""
        consultas_prog = [
            "¿Cómo optimizo esta función con un diccionario en Python?",
            "Tengo un IndexError en mi bucle for, revisa el script",
            "Explícame cómo hacer un SELECT con JOIN en SQL",
            "¿Cuál es la complejidad temporal de quicksort?",
            "def procesar_datos(lista): return [x*2 for x in lista]",
            "Explícame por qué falla mi puntero en C++",
            "Cómo hacer un vector en C++ con scanf y printf",
            "¿Cómo implementar una interfaz en C#?",
            "Tengo un segfault con malloc en mi struct",
            "Revisa este commit en el repositorio y la consulta sql en supabase",
        ]
        for q in consultas_prog:
            c = ee.clasificar_consulta(q)
            self.assertEqual(c["area"], "programacion", f"Fallo en: {q}")
            self.assertEqual(c["carril"], "pesado")
            self.assertIn("CARTUCHO ESPECIALISTA: INGENIERÍA DE SOFTWARE", c["prompt_experto"])

    def test_clasificacion_matematicas(self):
        """Consultas de cálculo, álgebra y matrices enrutan a matemáticas y carril pesado."""
        consultas_mat = [
            "Calcula la derivada de x^3 * sin(x)",
            "¿Cómo se calcula el determinante de una matriz 3x3?",
            "Resuelve esta ecuación diferencial paso a paso",
            "Explícame el teorema de Bayes con probabilidad",
            "¿Cuál es el límite cuando x tiende a cero?",
        ]
        for q in consultas_mat:
            c = ee.clasificar_consulta(q)
            self.assertEqual(c["area"], "matematicas", f"Fallo en: {q}")
            self.assertEqual(c["carril"], "pesado")
            self.assertIn("CARTUCHO ESPECIALISTA: MATEMÁTICAS", c["prompt_experto"])

    def test_cartuchos_registrados(self):
        """El registro central permite obtener cartuchos limpios."""
        self.assertIn("programacion", REGISTRO_EXPERTOS)
        self.assertIn("matematicas", REGISTRO_EXPERTOS)
        self.assertTrue(len(obtener_cartucho("programacion")) > 50)
        self.assertTrue(len(obtener_cartucho("matematicas")) > 50)
        self.assertEqual(obtener_cartucho("inexistente"), "")

    def test_seleccion_modelos_pesados_y_fallback(self):
        """El carril pesado prioriza modelos de razonamiento y deja el rápido como fallback final."""
        cfg_dummy = SimpleNamespace(
            MODELO_RAPIDO="llama-3.1-8b-instant",
        )
        mods_pesado = ee.seleccionar_modelo_experto(cfg_dummy, carril="pesado")
        self.assertEqual(mods_pesado[0], "openai/gpt-oss-120b")
        self.assertEqual(mods_pesado[1], "qwen/qwen3.8-27b")
        self.assertEqual(mods_pesado[2], "openai/gpt-oss-20b")
        self.assertNotIn("llama-3.3-70b-versatile", mods_pesado[:3])
        # El rápido debe estar al final como salvaguarda
        self.assertEqual(mods_pesado[-1], "llama-3.1-8b-instant")

        mods_rapido = ee.seleccionar_modelo_experto(cfg_dummy, carril="rapido")
        self.assertEqual(mods_rapido, ["llama-3.1-8b-instant"])

    def test_inyeccion_selectiva_en_cerebro_instrucciones(self):
        """Cerebro.instrucciones inyecta el cartucho en programación/matemáticas y no en charla."""
        import cerebro as c_mod
        mem = SimpleNamespace(hechos=[], creador="Moisés", nombre="Lyris", proposito="ayudar")
        inst = c_mod.Cerebro(cliente=None, memoria=mem)

        # 1. Consulta normal sin cartucho
        prompt_normal = inst.instrucciones("Hola, buenos días")
        self.assertNotIn("CARTUCHO ESPECIALISTA", prompt_normal)

        # 2. Consulta de programación con cartucho inyectado
        prompt_prog = inst.instrucciones("Tengo un error de sintaxis en mi función def calcular():")
        self.assertIn("CARTUCHO ESPECIALISTA: INGENIERÍA DE SOFTWARE", prompt_prog)

        # 3. Consulta de matemáticas con cartucho inyectado
        prompt_mat = inst.instrucciones("Calcula la derivada e integral de la función")
        self.assertIn("CARTUCHO ESPECIALISTA: MATEMÁTICAS", prompt_mat)


if __name__ == "__main__":
    unittest.main()
