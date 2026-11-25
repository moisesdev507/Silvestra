"""Pruebas del onboarding inicial y del empaquetado limpio para amigos."""
import os
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import construir_exe
import construir_paquete_amigos as empaquetador
import onboarding_qt as onboarding
import rutas_app
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

RAIZ = os.path.dirname(os.path.abspath(__file__))
CLAVES_PRUEBA = {
    "GEMINI_API_KEY": "AIzaFakeKeyParaPruebas123456789012345",
    "GROQ_API_KEY": "gsk_FakeGroqKeyParaPruebas1234567890",
    "DEEPGRAM_API_KEY": "0123456789abcdef0123456789abcdef01234567",
}
SECRETOS = tuple(CLAVES_PRUEBA.values())


def escribir(ruta, contenido):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", errors="replace") as f:
        f.write(contenido)


def texto_de(ruta):
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


class OnboardingTests(unittest.TestCase):
    """Detección de primer arranque y guardado limpio en modo offscreen."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = self.temporal.name
        self.ruta_env = os.path.join(self.base, ".env")

    def tearDown(self):
        self.temporal.cleanup()

    def test_primer_arranque_sin_env(self):
        self.assertFalse(os.path.exists(self.ruta_env))
        self.assertTrue(onboarding.necesita_onboarding(self.ruta_env))
        self.assertEqual(len(onboarding.CLAVES), 3)

    def test_guardado_limpio_offscreen(self):
        dialogo = onboarding.OnboardingDialog(base=self.base)
        dialogo.campo_nombre.setText("Alex")
        for clave, valor in CLAVES_PRUEBA.items():
            dialogo.campos[clave].setText(valor)
        with patch.dict(os.environ):
            dialogo._guardar()
            self.assertTrue(dialogo.resultado)
            self.assertFalse(onboarding.necesita_onboarding(self.ruta_env))
            self.assertEqual(os.environ["GROQ_API_KEY"], CLAVES_PRUEBA["GROQ_API_KEY"])

        contenido = texto_de(self.ruta_env)
        for clave, valor in CLAVES_PRUEBA.items():
            self.assertIn(f"{clave}={valor}", contenido)
        perfil = os.path.join(self.base, "datos", "perfil_usuario.json")
        self.assertTrue(os.path.exists(perfil))
        self.assertIn("Alex", texto_de(perfil))
        memoria = os.path.join(self.base, "memoria.json")
        self.assertIn("Alex", texto_de(memoria))

    def test_validacion_rechaza_claves_invalidas(self):
        self.assertFalse(onboarding.validar_clave("GROQ_API_KEY", "corta")[0])
        self.assertFalse(onboarding.validar_clave("GROQ_API_KEY", "tu_clave_de_prueba")[0])
        self.assertTrue(onboarding.validar_clave("GROQ_API_KEY", CLAVES_PRUEBA["GROQ_API_KEY"])[0])
        malas = dict(CLAVES_PRUEBA, GROQ_API_KEY="abc")
        ok, mensaje = onboarding.guardar_configuracion(
            "Alex", malas, base=self.base, ruta_env=self.ruta_env)
        self.assertFalse(ok)
        self.assertIn("GROQ_API_KEY", mensaje)
        self.assertFalse(os.path.exists(self.ruta_env))

    def test_mostrar_ocultar_claves(self):
        dialogo = onboarding.OnboardingDialog(base=self.base)
        dialogo.campos["GEMINI_API_KEY"].setText(CLAVES_PRUEBA["GEMINI_API_KEY"])
        self.assertEqual(dialogo.campos["GEMINI_API_KEY"].echoMode(), QLineEdit.Password)
        botones = [b for b in dialogo.findChildren(QPushButton) if b.text() == "👁"]
        self.assertTrue(botones)
        botones[0].setChecked(True)
        self.assertEqual(dialogo.campos["GEMINI_API_KEY"].echoMode(), QLineEdit.Normal)
        botones[0].setChecked(False)
        self.assertEqual(dialogo.campos["GEMINI_API_KEY"].echoMode(), QLineEdit.Password)


class PaqueteTests(unittest.TestCase):
    """Generación del paquete en temporal con exclusión total de datos privados."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.origen = os.path.join(self.tmp.name, "fuente")
        self.destino = os.path.join(self.tmp.name, "salida")
        os.makedirs(self.origen)
        escribir(os.path.join(self.origen, "main.py"), "print('kaya')\n")
        escribir(os.path.join(self.origen, "config.py"),
                 'CLAVE = "gsk_ClavePrivadaDelDueno1234567890"\n'
                 'DEEPGRAM_API_KEY = "0123456789abcdef0123456789abcdef01234567"\n')
        escribir(os.path.join(self.origen, "config.example.py"),
                 texto_de(os.path.join(RAIZ, "config.example.py")))
        escribir(os.path.join(self.origen, "requirements.txt"), "PySide6==6.12.0\n")
        escribir(os.path.join(self.origen, ".env"), "\n".join(
            f"{k}={v}" for k, v in CLAVES_PRUEBA.items()))
        escribir(os.path.join(self.origen, "datos", "privado.json"), '{"nombre": "Moisés"}')
        escribir(os.path.join(self.origen, "silvestra.log"), "registro privado")
        escribir(os.path.join(self.origen, ".git", "config"), "remote privado")
        escribir(os.path.join(self.origen, "__pycache__", "x.pyc"), "bytecode")
        escribir(os.path.join(self.origen, ".venv", "pyvenv.cfg"), "home privado")
        escribir(os.path.join(self.origen, "temporal.tmp"), "temporal")
        escribir(os.path.join(self.origen, "modelos", "silero_vad.onnx"), "modelo generico")
        escribir(os.path.join(self.origen, "sonidos", "baile.wav"), "audio generico")
        self.resultado = empaquetador.construir(self.origen, self.destino)
        self.paquete = self.resultado["carpeta"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_estructura_y_archivos_incluidos(self):
        self.assertTrue(os.path.isdir(self.paquete))
        self.assertTrue(os.path.isfile(self.resultado["zip"]))
        for nombre in ("main.py", "config.py", "config.example.py", "requirements.txt",
                       ".env.example", "Iniciar_Kaya.bat", "LEEME_INSTALACION.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.paquete, nombre)), nombre)
        self.assertIn("_cfg(", texto_de(os.path.join(self.paquete, "config.py")))
        self.assertTrue(os.path.exists(os.path.join(
            self.paquete, "modelos", "silero_vad.onnx")))
        pasos = [ln for ln in texto_de(os.path.join(
            self.paquete, "LEEME_INSTALACION.txt")).splitlines()
            if ln.strip()[:2] in ("1.", "2.", "3.", "4.", "5.")]
        self.assertEqual(len(pasos), 5)

    def test_exclusion_estricta(self):
        prohibidos = (".env", "datos", "silvestra.log", ".git", "__pycache__",
                      ".venv", "temporal.tmp")
        for nombre in prohibidos:
            self.assertFalse(os.path.exists(os.path.join(self.paquete, nombre)), nombre)
        self.assertEqual(empaquetador.auditar(self.paquete), [])
        with zipfile.ZipFile(self.resultado["zip"]) as zf:
            nombres = zf.namelist()
        self.assertIn("Kaya_Portable/main.py", nombres)
        for nombre in prohibidos:
            ruta = f"Kaya_Portable/{nombre}"
            self.assertFalse(any(n == ruta or n.startswith(ruta + "/") for n in nombres), nombre)

    def test_sin_claves_reales_en_el_contenido(self):
        for raiz, _, archivos in os.walk(self.paquete):
            for nombre in archivos:
                ruta = os.path.join(raiz, nombre)
                if os.path.splitext(nombre)[1].lower() not in empaquetador.EXT_TEXTO:
                    continue
                contenido = texto_de(ruta)
                for secreto in SECRETOS:
                    self.assertNotIn(secreto, contenido, ruta)
        self.assertEqual(empaquetador.auditar(self.paquete), [])

    def test_auditoria_detecta_secreto_plantado(self):
        escribir(os.path.join(self.paquete, "filtrado.py"),
                 'CLAVE = "gsk_FiltradoDelDueno1234567890"\n')
        problemas = empaquetador.auditar(self.paquete)
        self.assertTrue(problemas)
        self.assertTrue(any("filtrado.py" in p for p in problemas), problemas)


class RutasTests(unittest.TestCase):
    """Rutas en desarrollo y simulación del ejecutable congelado."""

    def test_rutas_en_desarrollo(self):
        self.assertEqual(rutas_app.dir_recursos(), RAIZ)
        self.assertEqual(rutas_app.dir_usuario(), RAIZ)

    def test_rutas_congeladas_y_preparacion(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        interno = os.path.join(temporal.name, "_internal")
        ejecutable = os.path.join(temporal.name, "Kaya.exe")
        parches = (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "_MEIPASS", interno, create=True),
            patch.object(sys, "executable", ejecutable),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.assertEqual(rutas_app.dir_recursos(), interno)
        self.assertEqual(rutas_app.dir_usuario(), temporal.name)
        self.assertEqual(rutas_app.ruta_recurso("modelos", "silero_vad.onnx"),
                         os.path.join(interno, "modelos", "silero_vad.onnx"))
        base = rutas_app.preparar_dir_usuario()
        self.assertEqual(base, temporal.name)
        self.assertTrue(os.path.isfile(os.path.join(base, ".env")))
        self.assertTrue(os.path.isdir(os.path.join(base, "datos")))


class ExeAuditoriaTests(unittest.TestCase):
    """Auditoría fail-closed del paquete Kaya.exe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = os.path.join(self.tmp.name, "Kaya")
        os.makedirs(os.path.join(self.carpeta, "_internal"))
        escribir(os.path.join(self.carpeta, "Kaya.exe"), "binario falso")

    def test_paquete_limpio(self):
        self.assertEqual(construir_exe.auditar(self.carpeta), [])

    def test_escaneo_excluye_pruebas_y_scripts_de_compilacion(self):
        mods = construir_exe.modulos_activos()
        for esperado in ("main", "rutas_app", "onboarding_qt", "oido_ws"):
            self.assertIn(esperado, mods)
        for excluido in ("construir_exe", "construir_paquete_amigos",
                         "prueba_onboarding_paquete", "test_oido_adaptacion"):
            self.assertNotIn(excluido, mods)

    def test_detecta_codigo_datos_y_secretos(self):
        interna = os.path.join(self.carpeta, "_internal")
        escribir(os.path.join(interna, "config.py"), 'CLAVE = "valor"\n')
        escribir(os.path.join(interna, "config.json"),
                 '{"clave": "' + CLAVES_PRUEBA["GROQ_API_KEY"] + '"}')
        escribir(os.path.join(self.carpeta, ".env"), "GROQ_API_KEY=privada\n")
        escribir(os.path.join(self.carpeta, "silvestra.log"), "registro privado")
        os.makedirs(os.path.join(self.carpeta, "datos"))
        problemas = construir_exe.auditar(self.carpeta)
        for esperado in ("config.py", "config.json", ".env", "silvestra.log", "datos"):
            self.assertTrue(any(esperado in p for p in problemas), (esperado, problemas))

    def test_distingue_datos_de_biblioteca_y_fuente_de_kaya(self):
        interna = os.path.join(self.carpeta, "_internal")
        escribir(os.path.join(interna, "cv2", "config.py"), "RUTA = 1\n")
        escribir(os.path.join(interna, "google", "genai", "client.py"), "x = 1\n")
        escribir(os.path.join(interna, "main.py"), "x = 1\n")
        escribir(os.path.join(self.carpeta, "rutas_app.py"), "x = 1\n")
        problemas = construir_exe.auditar(self.carpeta)
        for permitido in ("cv2/config.py", "google/genai/client.py"):
            self.assertFalse(any(permitido in p for p in problemas), (permitido, problemas))
        for prohibido in ("_internal/main.py", "rutas_app.py"):
            self.assertTrue(any(prohibido in p for p in problemas), (prohibido, problemas))

    def test_datos_publicos_no_se_cuentan_como_secretos(self):
        ruta = os.path.join(self.carpeta, "_internal", "googleapiclient",
                            "discovery_cache", "documents", "api.json")
        escribir(ruta, '{"hash": "' + "a" * 40 + '"}')
        self.assertEqual(construir_exe.auditar(self.carpeta), [])

    def test_falta_el_ejecutable(self):
        os.remove(os.path.join(self.carpeta, "Kaya.exe"))
        problemas = construir_exe.auditar(self.carpeta)
        self.assertTrue(any("Kaya.exe" in p for p in problemas), problemas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
