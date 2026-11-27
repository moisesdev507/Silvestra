"""prueba_actualizador.py - Pruebas unitarias para versionado y actualizador seguro."""

import unittest
from pathlib import Path

import actualizador
import construir_exe
import version


class TestVersionYActualizador(unittest.TestCase):
    def test_version_y_repo(self):
        self.assertTrue(version.VERSION)
        self.assertIn(".", version.VERSION)
        self.assertTrue(version.REPO_GITHUB)
        self.assertIn("/", version.REPO_GITHUB)

    def test_parsear_version(self):
        self.assertEqual(actualizador.parsear_version("1.0.0"), (1, 0, 0))
        self.assertEqual(actualizador.parsear_version("v1.0.1"), (1, 0, 1))
        self.assertEqual(actualizador.parsear_version("V2.3.4-beta"), (2, 3, 4))
        self.assertEqual(actualizador.parsear_version("invalid"), (0, 0, 0))

    def test_es_version_mayor(self):
        self.assertTrue(actualizador.es_version_mayor("1.0.1", "1.0.0"))
        self.assertTrue(actualizador.es_version_mayor("v1.1.0", "1.0.9"))
        self.assertTrue(actualizador.es_version_mayor("v2.0.0", "1.9.9"))
        self.assertFalse(actualizador.es_version_mayor("1.0.0", "1.0.0"))
        self.assertFalse(actualizador.es_version_mayor("0.9.9", "1.0.0"))
        self.assertFalse(actualizador.es_version_mayor("1.0.0", "1.0.1"))

    def test_exclusiones_estrictas(self):
        self.assertIn(".env", actualizador.ARCHIVOS_EXCLUIDOS)
        self.assertIn("memoria.json", actualizador.ARCHIVOS_EXCLUIDOS)
        self.assertIn("silvestra.log", actualizador.ARCHIVOS_EXCLUIDOS)
        self.assertIn("datos", actualizador.CARPETAS_EXCLUIDAS)

    def test_generacion_bat(self):
        bat = actualizador.generar_script_bat(
            directorio_destino=r"C:\Kaya",
            ruta_zip=r"C:\Temp\Kaya_Windows.zip",
            pid_esperar=9999,
            ejecutable_relanzar=r"C:\Kaya\Kaya.exe",
        )
        self.assertIn('PID eq 9999', bat)
        self.assertIn('robocopy', bat)
        self.assertIn('".env"', bat)
        self.assertIn('"memoria.json"', bat)
        self.assertIn('"silvestra.log"', bat)
        self.assertIn('"datos"', bat)
        self.assertIn(r'C:\Kaya\Kaya.exe', bat)

    def test_no_actualiza_en_codigo_fuente(self):
        exito, msg = actualizador.lanzar_actualizacion_binaria({"url_zip": "http://fake.url/zip"})
        self.assertFalse(exito)
        self.assertIn("codigo fuente", msg.lower())

    def test_instalador_iss_existe(self):
        iss_path = Path("instalador_kaya.iss")
        self.assertTrue(iss_path.exists())
        contenido = iss_path.read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", contenido)
        self.assertIn("{localappdata}", contenido)
        self.assertIn("Kaya_Setup", contenido)
        self.assertIn("MyAppVersion", contenido)
        self.assertIn("AppVerName", contenido)

    def test_buscar_iscc(self):
        # Debe retornar str o None sin lanzar excepciones
        resultado = construir_exe.buscar_iscc()
        self.assertTrue(resultado is None or isinstance(resultado, str))

    def test_puente_actualizacion_emite_y_despacha(self):
        from unittest.mock import MagicMock, patch
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        puente = actualizador.PuenteActualizacion()

        with patch.object(actualizador.DialogoActualizacion, "mostrar", return_value=False) as mock_mostrar:
            info = {"tag": "v1.0.1", "notas": "Notas"}
            puente.actualizacion_disponible.emit(info)
            app.processEvents()
            mock_mostrar.assert_called_once_with(info, padre=None)

    def test_verificar_y_notificar_emite_a_puente(self):
        from unittest.mock import MagicMock, patch

        puente_mock = MagicMock()
        with patch("actualizador.consultar_release_remoto", return_value={"tag": "v9.9.9", "url_zip": "http://zip"}), \
             patch("actualizador.time.sleep"):
            actualizador._verificar_y_notificar(None, puente=puente_mock)
            puente_mock.actualizacion_disponible.emit.assert_called_once()

    def test_dialogo_actualizacion_stays_on_top_y_activate(self):
        from unittest.mock import patch
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QDialog

        _ = QApplication.instance() or QApplication([])
        llamadas = []

        with patch.object(QDialog, "exec", return_value=QDialog.Accepted) as mock_exec, \
             patch.object(QDialog, "show", side_effect=lambda *args: llamadas.append("show")), \
             patch.object(QDialog, "raise_", side_effect=lambda *args: llamadas.append("raise_")), \
             patch.object(QDialog, "activateWindow", side_effect=lambda *args: llamadas.append("activateWindow")), \
             patch.object(QDialog, "setWindowFlags") as mock_flags:

            info = {"tag": "v1.0.1", "notas": "Notas de prueba"}
            resultado = actualizador.DialogoActualizacion.mostrar(info)
            self.assertTrue(resultado)

            # Verificar flags de ventana
            mock_flags.assert_called()
            flags_arg = mock_flags.call_args[0][0]
            self.assertTrue(bool(flags_arg & Qt.WindowType.WindowStaysOnTopHint))

            # Verificar show, raise_ y activateWindow
            self.assertEqual(llamadas, ["show", "raise_", "activateWindow"])
            mock_exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
