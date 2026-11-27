"""Regresión: modo compartido solo se activa en el .exe con marcador."""
import os
import tempfile
import unittest
from unittest.mock import patch

import construir_exe
import live_prompt
import modo_compartido


class TestModoCompartido(unittest.TestCase):
    def test_desarrollo_siempre_false_aunque_exista_el_marcador(self):
        with patch.object(modo_compartido.sys, "frozen", False, create=True), \
             patch.object(modo_compartido, "ruta_flag", lambda: __file__):
            self.assertFalse(modo_compartido.es_version_compartida())

    def test_frozen_con_marcador_true(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, modo_compartido.NOMBRE_FLAG)
            with open(ruta, "wb"):
                pass
            with patch.object(modo_compartido.sys, "frozen", True, create=True), \
                 patch.object(modo_compartido, "ruta_flag", lambda: ruta):
                self.assertTrue(modo_compartido.es_version_compartida())

    def test_frozen_sin_marcador_false(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, modo_compartido.NOMBRE_FLAG)
            with patch.object(modo_compartido.sys, "frozen", True, create=True), \
                 patch.object(modo_compartido, "ruta_flag", lambda: ruta):
                self.assertFalse(modo_compartido.es_version_compartida())

    def test_ruta_flag_queda_junto_al_ejecutable(self):
        ruta = modo_compartido.ruta_flag()
        self.assertEqual(os.path.basename(ruta), "beta_compartida.flag")
        self.assertEqual(os.path.dirname(ruta),
                         os.path.dirname(os.path.abspath(modo_compartido.sys.executable)))

    def test_bloque_prompt_solo_en_compartida(self):
        with patch.object(modo_compartido, "es_version_compartida", return_value=False):
            guia_local = live_prompt.guia_vocal()
        with patch.object(modo_compartido, "es_version_compartida", return_value=True):
            guia_compartida = live_prompt.guia_vocal()
        self.assertNotIn("Versión compartida de prueba", guia_local)
        self.assertIn("Versión compartida de prueba", guia_compartida)
        self.assertIn("pequeños errores", guia_compartida)
        self.assertIn("primer saludo de voz", guia_compartida)

    def test_bloque_prompt_va_al_inicio_para_no_recortarse(self):
        with patch.object(modo_compartido, "es_version_compartida", return_value=True):
            guia = live_prompt.guia_vocal()
        self.assertLess(guia.index("[Versión compartida de prueba]"),
                        guia.index("- Eres una persona real"))

    def test_auditoria_permite_el_marcador(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with open(os.path.join(carpeta, "Kaya.exe"), "wb"):
                pass
            with open(os.path.join(carpeta, "beta_compartida.flag"), "wb"):
                pass
            self.assertEqual(construir_exe.auditar(carpeta), [])


if __name__ == "__main__":
    unittest.main()
