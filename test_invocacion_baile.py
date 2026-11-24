"""Pruebas unitarias para tolerancia fonética y parada de baile en invocacion_lyris."""
import unittest

import invocacion_lyris as il


class TestInvocacionBaile(unittest.TestCase):
    """Pruebas de tolerancia fonética ("Viris", "Libres", "Liernes") y parada directa de baile."""

    def test_tolerancia_fonetica_fuertes(self):
        """'viris', 'liris', 'lyrys' disparan como invocación normal en cualquier posición."""
        dispara, var, orden = il.detectar("Viris")
        self.assertTrue(dispara)
        self.assertEqual(var, "viris")

        dispara2, var2, orden2 = il.detectar("oye viris qué hora es")
        self.assertTrue(dispara2)
        self.assertEqual(var2, "viris")
        self.assertIn("hora", orden2)

        dispara3, var3, orden3 = il.detectar("lyrys, para de bailar")
        self.assertTrue(dispara3)
        self.assertEqual(var3, "lyrys")
        self.assertEqual(orden3, "para de bailar")

    def test_tolerancia_fonetica_debiles_al_inicio_o_aisladas(self):
        """'libres' o 'liernes' disparan al inicio o aisladas, pero NO en medio de frases normales."""
        # 1. Al inicio de la orden (típica transcripción fonética errada)
        dispara, var, orden = il.detectar("Libres, para de bailar")
        self.assertTrue(dispara)
        self.assertEqual(var, "libres")
        self.assertEqual(orden, "para de bailar")

        # 2. Invocación aislada
        dispara2, var2, orden2 = il.detectar("Liernes")
        self.assertTrue(dispara2)
        self.assertEqual(var2, "liernes")
        self.assertEqual(orden2, "")

        # 3. Frase normal que contiene "somos libres" NO debe disparar invocación falsa
        dispara3, var3, orden3 = il.detectar("en este país todos somos libres de opinar")
        self.assertFalse(dispara3)
        self.assertEqual(var3, "")

    def test_parada_directa_de_baile_sin_nombre(self):
        """Si la cara está en modo baile, órdenes directas como 'para de bailar' detienen sin decir Lyris."""
        # Sin modo baile activo, "para de bailar" sin nombre no dispara invocación
        dispara_no_baile, _, _ = il.detectar("para de bailar", en_baile=False)
        self.assertFalse(dispara_no_baile)

        # Con modo baile activo (en_baile=True), dispara inmediatamente
        dispara_baile, var, orden = il.detectar("para de bailar", en_baile=True)
        self.assertTrue(dispara_baile)
        self.assertEqual(var, "baile_stop")
        self.assertEqual(orden, "para de bailar")

        dispara_stop, var_s, _ = il.detectar("stop", en_baile=True)
        self.assertTrue(dispara_stop)

        dispara_detente, var_d, _ = il.detectar("detente", en_baile=True)
        self.assertTrue(dispara_detente)


if __name__ == "__main__":
    unittest.main()
