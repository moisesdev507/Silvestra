"""Pruebas unitarias para cara_orbe_hibrido.py con renderizado offscreen en QImage."""
import unittest
from types import SimpleNamespace

from PySide6.QtGui import QImage, QPainter

import cara_orbe_hibrido as coh
import enrutador_expertos as ee


class TestCaraOrbeHibrido(unittest.TestCase):

    def setUp(self):
        coh.obtener_orbe().fijar_modo_experto(False)

    def test_deduccion_estados_y_paletas(self):
        cara = SimpleNamespace(
            voz_silenciada=False,
            baile_hasta=0.0,
            hablando=False,
            escuchando=False,
            pensando=False,
            pensando_hasta=0.0,
            nivel_volumen=0.0,
        )
        orbe = coh.GestorOrbeHibrido()

        # 1. Reposo
        self.assertEqual(orbe.deducir_estado(cara), "reposo")

        # 2. Escuchando
        cara.escuchando = True
        self.assertEqual(orbe.deducir_estado(cara), "escuchando")
        cara.escuchando = False

        # 3. Pensando
        cara.pensando = True
        self.assertEqual(orbe.deducir_estado(cara), "pensando")
        cara.pensando = False

        # 4. Modo Experto
        orbe.fijar_modo_experto(True, "programacion")
        self.assertEqual(orbe.deducir_estado(cara), "experto")
        orbe.fijar_modo_experto(False)

        # 5. Hablando
        cara.hablando = True
        self.assertEqual(orbe.deducir_estado(cara), "hablando")
        cara.hablando = False

        # 6. Bailando
        cara.baile_hasta = 9999999999.0
        self.assertEqual(orbe.deducir_estado(cara), "bailando")
        cara.baile_hasta = 0.0

        # 7. Silenciada
        cara.voz_silenciada = True
        self.assertEqual(orbe.deducir_estado(cara), "silenciada")

    def test_renderizado_offscreen_qimage(self):
        """Verifica que el orbe dibuje limpiamente en un QImage sin lanzar excepciones."""
        img = QImage(208, 208, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        cara = SimpleNamespace(
            voz_silenciada=False,
            baile_hasta=0.0,
            hablando=True,
            escuchando=False,
            pensando=False,
            pensando_hasta=0.0,
            nivel_volumen=0.65,
        )
        try:
            coh.dibujar_orbe_hibrido(p, cara, t=1.25, tam=208)
        finally:
            p.end()

        # La imagen no debe quedar totalmente transparente
        self.assertFalse(img.isNull())
        # Verificar que el centro tenga píxeles pintados con alfa > 0
        pixel_centro = img.pixelColor(104, 104)
        self.assertTrue(pixel_centro.alpha() > 0)

    def test_suavizado_rms_y_halos_contrarrotatorios(self):
        orbe = coh.GestorOrbeHibrido()
        cara = SimpleNamespace(
            voz_silenciada=False,
            baile_hasta=0.0,
            hablando=True,
            escuchando=False,
            pensando=False,
            pensando_hasta=0.0,
            nivel_volumen=0.8,
        )
        # Actualización 1
        orbe.actualizar(cara, t=1.0, nivel_rms=0.8)
        self.assertTrue(orbe.rms_suave > 0.0)

        # Actualización 2: arcos deben avanzar
        ang1_antes = orbe.ang_halo_1
        ang2_antes = orbe.ang_halo_2
        orbe.actualizar(cara, t=1.05, nivel_rms=0.5)

        self.assertNotEqual(orbe.ang_halo_1, ang1_antes)
        self.assertNotEqual(orbe.ang_halo_2, ang2_antes)

    def test_activacion_automatica_modo_experto_desde_clasificador(self):
        """Al clasificar programación o matemáticas, se notifica el modo experto."""
        coh.obtener_orbe().fijar_modo_experto(False)
        self.assertFalse(coh.obtener_orbe().modo_experto_activo)

        # 1. Consulta de programación
        c_prog = ee.clasificar_consulta("Tengo un puntero en C++ con segfault")
        self.assertEqual(c_prog["area"], "programacion")
        self.assertTrue(coh.obtener_orbe().modo_experto_activo)
        self.assertEqual(coh.obtener_orbe().area_experto, "programacion")

        # 2. Consulta cotidiana limpia el modo experto
        c_gen = ee.clasificar_consulta("Hola Lyris, ¿qué hora es?")
        self.assertEqual(c_gen["area"], "general")
        self.assertFalse(coh.obtener_orbe().modo_experto_activo)


if __name__ == "__main__":
    unittest.main()
