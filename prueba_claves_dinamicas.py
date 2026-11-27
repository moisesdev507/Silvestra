"""Claves API leídas en caliente: sin reinicio tras el onboarding."""
import importlib.util
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import claves_dinamicas
import construir_paquete_amigos as empaquetador
import onboarding_qt
import rutas_app
import vision_compartida

CLAVES_PRUEBA = {
    "GEMINI_API_KEY": "AIzaFakeKeyParaPruebas123456789012345",
    "GROQ_API_KEY": "gsk_FakeGroqKeyParaPruebas1234567890",
    "DEEPGRAM_API_KEY": "0123456789abcdef0123456789abcdef01234567",
}
GEMINI_NUEVA = "AIzaFakeKeyCambiadaSinReinicio1234567890"


def _escribir_env(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as archivo:
        for nombre, valor in datos.items():
            archivo.write(f"{nombre}={valor}\n")


class ClavesDinamicasTests(unittest.TestCase):
    def test_valor_lee_env_recien_escrito(self):
        with tempfile.TemporaryDirectory() as base:
            ruta = os.path.join(base, ".env")
            _escribir_env(ruta, {"GEMINI_API_KEY": GEMINI_NUEVA})
            with patch.object(rutas_app, "dir_usuario", return_value=base), patch.dict(os.environ):
                os.environ.pop("GEMINI_API_KEY", None)
                self.assertEqual(claves_dinamicas.valor("GEMINI_API_KEY"), GEMINI_NUEVA)
                self.assertEqual(os.environ["GEMINI_API_KEY"], GEMINI_NUEVA)

    def test_recargar_actualiza_config_y_vision(self):
        config_falso = SimpleNamespace(CLAVE_GOOGLE="", CLAVE="", GEMINI_API_KEY="")
        with tempfile.TemporaryDirectory() as base:
            ruta = os.path.join(base, ".env")
            _escribir_env(ruta, {"GEMINI_API_KEY": GEMINI_NUEVA,
                                 "GROQ_API_KEY": CLAVES_PRUEBA["GROQ_API_KEY"]})
            parches = (
                patch.object(rutas_app, "dir_usuario", return_value=base),
                patch.dict(os.environ),
                patch.dict(sys.modules, {"config": config_falso}),
            )
            for parche in parches:
                parche.start()
                self.addCleanup(parche.stop)
            datos = claves_dinamicas.recargar(ruta)
            self.assertEqual(datos["GEMINI_API_KEY"], GEMINI_NUEVA)
            self.assertEqual(config_falso.CLAVE_GOOGLE, GEMINI_NUEVA)
            self.assertEqual(config_falso.GEMINI_API_KEY, GEMINI_NUEVA)
            self.assertEqual(config_falso.CLAVE, CLAVES_PRUEBA["GROQ_API_KEY"])
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertEqual(vision_compartida._clave(), GEMINI_NUEVA)

    def test_config_generado_no_cachea_claves(self):
        with tempfile.TemporaryDirectory() as base:
            usuario = os.path.join(base, "usuario")
            os.makedirs(usuario)
            empaquetador._generar_config(empaquetador.BASE, base)
            ruta_cfg = os.path.join(base, "config.py")
            with open(ruta_cfg, "r", encoding="utf-8") as archivo:
                texto = archivo.read()
            self.assertIn("__getattr__", texto)
            self.assertIn("_cfg(", texto)
            for linea in texto.splitlines():
                self.assertNotRegex(linea, r"^[A-Z][A-Z0-9_]* = _cfg\(")

            ruta_env = os.path.join(usuario, ".env")
            _escribir_env(ruta_env, {"GEMINI_API_KEY": GEMINI_NUEVA})
            with patch.object(rutas_app, "dir_usuario", return_value=usuario), patch.dict(os.environ):
                os.environ.pop("GEMINI_API_KEY", None)
                especificacion = importlib.util.spec_from_file_location("config_generado_prueba", ruta_cfg)
                modulo = importlib.util.module_from_spec(especificacion)
                especificacion.loader.exec_module(modulo)
                self.assertEqual(modulo.CLAVE_GOOGLE, GEMINI_NUEVA)
                _escribir_env(ruta_env, {"GEMINI_API_KEY": CLAVES_PRUEBA["GEMINI_API_KEY"]})
                self.assertEqual(modulo.CLAVE_GOOGLE, CLAVES_PRUEBA["GEMINI_API_KEY"])

    def test_onboarding_refresca_config_al_guardar(self):
        config_falso = SimpleNamespace()
        with tempfile.TemporaryDirectory() as base:
            ruta_env = os.path.join(base, ".env")
            parches = (
                patch.dict(sys.modules, {"config": config_falso}),
                patch.dict(os.environ),
                patch.object(rutas_app, "dir_usuario", return_value=base),
            )
            for parche in parches:
                parche.start()
                self.addCleanup(parche.stop)
            ok, mensaje = onboarding_qt.guardar_configuracion(
                "Alex", CLAVES_PRUEBA, base=base, ruta_env=ruta_env)
            self.assertTrue(ok, mensaje)
            self.assertEqual(config_falso.CLAVE_GOOGLE, CLAVES_PRUEBA["GEMINI_API_KEY"])
            self.assertEqual(config_falso.CLAVE, CLAVES_PRUEBA["GROQ_API_KEY"])
            self.assertEqual(config_falso.DEEPGRAM_API_KEY, CLAVES_PRUEBA["DEEPGRAM_API_KEY"])


if __name__ == "__main__":
    unittest.main()
