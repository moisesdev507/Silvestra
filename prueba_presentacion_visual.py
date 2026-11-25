"""Pruebas de estados visuales del orbe y del HUD (Qt offscreen)."""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestPresentacionVisual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app_qt = QApplication.instance() or QApplication([])

    def test_estados_y_onda_sin_errores(self):
        import cara_presentacion
        import cara_qt

        cara = cara_qt.Cara(lambda: None, lambda: None, lambda: None, lambda: None)
        try:
            cara.poner_escuchando(True)
            self.assertEqual(cara._presentacion_estado, "escuchando")
            cara.poner_escuchando(False)
            cara.poner_herramienta(True)
            self.assertEqual(cara._presentacion_estado, "herramienta")
            self.assertTrue(cara.pensando)
            cara.decir("Hola Moisés, estoy lista.")
            self.assertGreaterEqual(cara._presentacion_progreso, 0.0)
            cara_presentacion.avanzar(cara, time.time() + 0.4)
            self.assertLessEqual(cara._presentacion_progreso, 1.0)
            self.assertGreater(cara._presentacion_nivel, 0.0)
            cara.paintEvent(None)
            cara.poner_hablando(True)
            self.assertEqual(cara._presentacion_estado, "hablando")
            cara.paintEvent(None)
        finally:
            cara.close()
            cara.deleteLater()

    def test_opacidad_de_despliegue_es_suave(self):
        import cara_presentacion

        self.assertEqual(cara_presentacion.opacidad_despliegue(0), 0.0)
        self.assertEqual(cara_presentacion.opacidad_despliegue(1), 1.0)
        medio = cara_presentacion.opacidad_despliegue(0.5)
        self.assertGreater(medio, 0.5)
        self.assertLess(medio, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
