"""Pruebas unitarias para el motor seguro de cálculo matemático local (sandbox_calculo.py)."""
import math
import unittest

import sandbox_calculo as sc


class TestSandboxCalculo(unittest.TestCase):

    def test_evaluacion_aritmetica_basica(self):
        self.assertEqual(sc.evaluar_expresion("2 + 2"), 4)
        self.assertEqual(sc.evaluar_expresion("10 - 3 * 2"), 4)
        self.assertEqual(sc.evaluar_expresion("(25 * 48) + 12"), 1212)
        self.assertEqual(sc.evaluar_expresion("2^16"), 65536)
        self.assertAlmostEqual(sc.evaluar_expresion("sqrt(144) + 25"), 37.0)
        self.assertAlmostEqual(sc.evaluar_expresion("sin(pi / 2)"), 1.0)
        self.assertEqual(sc.evaluar_expresion("factorial(5)"), 120)
        self.assertEqual(sc.evaluar_expresion("gcd(36, 60)"), 12)

    def test_bloqueo_de_payloads_inseguros(self):
        ataques = [
            "__import__('os').system('dir')",
            "open('config.py').read()",
            "eval('1+1')",
            "exec('pass')",
            "[x for x in ().__class__.__bases__[0].__subclasses__()]",
            "math.sqrt(16)",  # Llamadas con atributo
            "9**9**9",
            "factorial(10000)",
            "1; import sys",
            "\\x61\\x62",
        ]
        for payload in ataques:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception):
                    sc.evaluar_expresion(payload)

    def test_teoria_numeros_primos_y_factores(self):
        self.assertTrue(sc.es_primo(2))
        self.assertTrue(sc.es_primo(97))
        self.assertTrue(sc.es_primo(104729))
        self.assertFalse(sc.es_primo(1))
        self.assertFalse(sc.es_primo(4))
        self.assertFalse(sc.es_primo(100))

        self.assertEqual(sc.factores_primos(360), [2, 2, 2, 3, 3, 5])
        self.assertEqual(sc.divisores_primos(360), [2, 3, 5])
        self.assertEqual(sc.divisores_primos(17), [17])

    def test_algebra_lineal_y_matrices(self):
        # 2x2: |1 2| / |3 4| = 1*4 - 2*3 = -2
        mat2 = [[1, 2], [3, 4]]
        self.assertAlmostEqual(sc.determinante_matriz(mat2), -2.0)

        # 3x3: determinante
        # |1 2 3|
        # |0 1 4|
        # |5 6 0| = 1*(0-24) - 2*(0-20) + 3*(0-5) = -24 + 40 - 15 = 1
        mat3 = [[1, 2, 3], [0, 1, 4], [5, 6, 0]]
        self.assertAlmostEqual(sc.determinante_matriz(mat3), 1.0)

        # Producto escalar
        v1 = [1, 2, 3]
        v2 = [4, 5, 6]
        self.assertEqual(sc.producto_escalar(v1, v2), 32.0)

    def test_estadistica_rapida(self):
        datos = [10, 20, 30, 40, 50]
        res = sc.estadistica_rapida(datos)
        self.assertEqual(res["promedio"], 30.0)
        self.assertEqual(res["mediana"], 30.0)
        self.assertAlmostEqual(res["desviacion_estandar"], 15.8113883, places=5)

    def test_extraccion_lenguaje_natural_precalcular(self):
        # Aritmética
        res_arit = sc.precalcular_contexto("cuánto es 128 * 37 + 15")
        self.assertIn("128 * 37 + 15 = 4751", res_arit)
        self.assertIn("CÁLCULO VERIFICADO EN PYTHON LOCAL", res_arit)

        # Primos
        res_primo = sc.precalcular_contexto("es primo el 97?")
        self.assertIn("97 SÍ es primo", res_primo)

        # Factores primos
        res_fact = sc.precalcular_contexto("divisores primos de 360")
        self.assertIn("360", res_fact)
        self.assertIn("[2, 3, 5]", res_fact)

        # Determinante
        res_det = sc.precalcular_contexto("Calcula el determinante de la matriz [[1, 2], [3, 4]]")
        self.assertIn("Determinante de la matriz", res_det)
        self.assertIn("-2", res_det)

        # Porcentaje
        res_pct = sc.precalcular_contexto("cuanto es el 15% de 80")
        self.assertIn("15% de 80 = 12", res_pct)

    def test_cero_falsos_positivos_en_teoria_sin_numeros(self):
        consultas_teoricas = [
            "Explícame qué es una derivada parcial",
            "¿Quién descubrió el cálculo infinitesimal?",
            "¿Qué significa la hipótesis de Riemann?",
            "Dime las fórmulas de trigonometría básica",
            "Hola Lyris, ¿cómo estás?",
        ]
        for q in consultas_teoricas:
            with self.subTest(q=q):
                self.assertEqual(sc.precalcular_contexto(q), "")


if __name__ == "__main__":
    unittest.main()
