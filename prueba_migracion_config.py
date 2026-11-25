"""Migración de claves antiguas sin onboarding falso ni primer despertar."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import onboarding_qt

VALIDAS = {
    "GEMINI_API_KEY": "AIzaFakeKeyParaPruebas123456789012345",
    "GROQ_API_KEY": "gsk_FakeGroqKeyParaPruebas1234567890",
    "DEEPGRAM_API_KEY": "0123456789abcdef0123456789abcdef01234567",
}


def escribir(ruta, texto):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)


def leer(ruta):
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


class MigracionConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = self.temporal.name
        self.ruta_env = os.path.join(self.base, ".env")
        self.ruta_config = os.path.join(self.base, "config.py")
        self.ruta_perfil = os.path.join(self.base, "datos", "perfil_usuario.json")

    def tearDown(self):
        self.temporal.cleanup()

    def _sin_claves_heredadas(self):
        return patch.dict(os.environ, {k: "" for k in onboarding_qt.CLAVES})

    def test_migra_alias_sin_crear_perfil(self):
        escribir(self.ruta_config,
                 'GOOGLE_API_KEY = "{}"\nGROQ_KEY = "{}"\n'
                 'DEEPGRAM_API_KEY = "{}"\n'.format(
                     VALIDAS["GEMINI_API_KEY"], VALIDAS["GROQ_API_KEY"],
                     VALIDAS["DEEPGRAM_API_KEY"]))
        with self._sin_claves_heredadas():
            migradas = onboarding_qt.migrar_config_local(self.base)
            self.assertFalse(onboarding_qt.necesita_onboarding(self.ruta_env))
        self.assertEqual(set(migradas), set(onboarding_qt.CLAVES))
        self.assertFalse(os.path.exists(self.ruta_perfil))
        contenido = leer(self.ruta_env)
        for canon, valor in VALIDAS.items():
            self.assertIn(f"{canon}={valor}", contenido)

    def test_perfil_existente_no_se_sobrescribe_ni_despierta(self):
        escribir(self.ruta_config, "\n".join(
            f'{k} = "{v}"' for k, v in VALIDAS.items()) + "\n")
        escribir(self.ruta_perfil,
                 '{"nombre": "Alex", "primer_despertar": true}')
        with self._sin_claves_heredadas():
            onboarding_qt.migrar_config_local(self.base)
        with open(self.ruta_perfil, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos, {"nombre": "Alex", "primer_despertar": False})

    def test_guardar_configuracion_respeta_perfil_existente(self):
        escribir(self.ruta_perfil,
                 '{"nombre": "Alex", "primer_despertar": true}')
        with self._sin_claves_heredadas():
            ok, mensaje = onboarding_qt.guardar_configuracion(
                "Otro", VALIDAS, base=self.base, ruta_env=self.ruta_env)
        self.assertTrue(ok, mensaje)
        with open(self.ruta_perfil, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["nombre"], "Alex")
        self.assertFalse(datos["primer_despertar"])

    def test_asegurar_configuracion_no_abre_modal_con_config_alias(self):
        escribir(self.ruta_config, "\n".join(
            f'{k} = "{v}"' for k, v in VALIDAS.items()) + "\n")
        with self._sin_claves_heredadas(), \
                patch.object(onboarding_qt, "OnboardingDialog") as dialogo:
            self.assertTrue(onboarding_qt.asegurar_configuracion(self.base))
        dialogo.assert_not_called()

    def test_carpeta_nueva_sigue_abriendo_onboarding(self):
        with self._sin_claves_heredadas(), \
                patch.object(onboarding_qt, "OnboardingDialog") as dialogo:
            dialogo.return_value.resultado = True
            self.assertTrue(onboarding_qt.asegurar_configuracion(self.base))
        dialogo.return_value.exec.assert_called_once()
        self.assertFalse(os.path.exists(self.ruta_env))
        self.assertFalse(os.path.exists(self.ruta_perfil))


if __name__ == "__main__":
    unittest.main()
