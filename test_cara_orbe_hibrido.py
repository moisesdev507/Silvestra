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
        cara.emocion_objetivo = "alegre"
        self.assertEqual(orbe.deducir_estado(cara), "hablando_calido")
        cara.emocion_objetivo = ""
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

    def test_renderizado_todos_los_estados(self):
        """Verifica que Holograma 2.0 pinte sin error en todos los estados visuales."""
        estados_a_probar = [
            ("reposo", False, False, False, False, 0.0),
            ("escuchando", False, True, False, False, 0.0),
            ("pensando", False, False, True, False, 0.0),
            ("hablando_bajo", True, False, False, False, 0.05),
            ("hablando_alto", True, False, False, False, 0.95),
            ("hablando_calido", True, False, False, False, 0.50),
            ("bailando", False, False, False, True, 0.0),
            ("silenciada", False, False, False, False, 0.0, True),
        ]
        for item in estados_a_probar:
            with self.subTest(estado=item[0]):
                img = QImage(280, 280, QImage.Format_ARGB32_Premultiplied)
                img.fill(0)
                p = QPainter(img)
                cara = SimpleNamespace(
                    hablando=item[1],
                    escuchando=item[2],
                    pensando=item[3],
                    pensando_hasta=0.0,
                    baile_hasta=9999999999.0 if item[4] else 0.0,
                    nivel_volumen=item[5],
                    voz_silenciada=item[6] if len(item) > 6 else False,
                )
                try:
                    coh.dibujar_orbe_hibrido(p, cara, t=2.5, tam=280)
                finally:
                    p.end()
                self.assertFalse(img.isNull())
                px = img.pixelColor(140, 140)
                self.assertTrue(px.alpha() > 0)

    def test_proyeccion_y_separacion_giroscopios_3d(self):
        """Valida matemáticas 3D, perspectiva y división z delantera/trasera."""
        import cara_holo_3d as h3d
        # 1. Rotación y proyección
        x, y, z = h3d.rotar_3d(10.0, 20.0, 30.0, pitch=0.2, yaw=0.3, roll=0.1)
        px, py, k, pz = h3d.proyectar_3d(x, y, z)
        self.assertTrue(k > 0.0)
        self.assertEqual(pz, z)

        # 2. Separación z de anillos
        traseros, delanteros = h3d._calcular_segmentos_anillo(
            r_anillo=50.0, pitch_anillo=0.4, yaw_anillo=0.2,
            vel_roll=1.0, t=1.0, pitch_cur=0.0, yaw_cur=0.0
        )
        self.assertTrue(len(traseros) > 0)
        self.assertTrue(len(delanteros) > 0)
        for _, _, z_med in traseros:
            self.assertTrue(z_med < 0.0)
        for _, _, z_med in delanteros:
            self.assertTrue(z_med >= 0.0)

        # 3. Manejo seguro sin cursor en QImage
        img = QImage(100, 100, QImage.Format_ARGB32)
        p = QPainter(img)
        try:
            pitch, yaw = h3d.obtener_inclinacion_cursor(p)
            self.assertEqual((pitch, yaw), (0.0, 0.0))
        finally:
            p.end()

    def test_centro_obsidiana_no_quemado_en_blanco(self):
        """Verifica que el núcleo use cristal obsidiana oscuro y no una mancha blanca plana."""
        img = QImage(280, 280, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        cara = SimpleNamespace(
            hablando=False,
            escuchando=False,
            pensando=False,
            pensando_hasta=0.0,
            baile_hasta=0.0,
            nivel_volumen=0.0,
            voz_silenciada=False,
        )
        try:
            coh.dibujar_orbe_hibrido(p, cara, t=1.5, tam=280)
        finally:
            p.end()

        px = img.pixelColor(140, 140)
        self.assertTrue(px.alpha() > 0)
        # El centro NO debe ser blanco puro quemado (255, 255, 255)
        es_blanco_quemado = (px.red() >= 250 and px.green() >= 250 and px.blue() >= 250)
        self.assertFalse(es_blanco_quemado, f"Centro quemado en blanco: rgb=({px.red()}, {px.green()}, {px.blue()})")

    def test_diferencia_visual_con_rms_hablando(self):
        """El ecualizador radial y la red 3D reaccionan con diferencia visual visible ante RMS de voz."""
        def render_con_rms(nivel_rms):
            img = QImage(280, 280, QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            cara = SimpleNamespace(
                hablando=True,
                escuchando=False,
                pensando=False,
                pensando_hasta=0.0,
                baile_hasta=0.0,
                nivel_volumen=nivel_rms,
                voz_silenciada=False,
            )
            try:
                coh.dibujar_orbe_hibrido(p, cara, t=2.0, tam=280)
            finally:
                p.end()
            return img

        img_silencio = render_con_rms(0.0)
        img_voz_alta = render_con_rms(0.85)

        # Contar píxeles que difieren entre ambas imágenes en la zona perimétrica
        diferencias = 0
        for y in range(80, 200, 4):
            for x in range(80, 200, 4):
                if img_silencio.pixelColor(x, y) != img_voz_alta.pixelColor(x, y):
                    diferencias += 1
        self.assertTrue(diferencias > 15, f"Esperadas diferencias visuales por RMS, encontradas: {diferencias}")

    def test_proporcion_nucleo_y_margen_exterior(self):
        """El núcleo tiene proporción ~66-70% del radio útil dejando aire libre para anillos 3D."""
        orbe = coh.GestorOrbeHibrido()
        cara = SimpleNamespace(
            hablando=False, escuchando=False, pensando=False,
            pensando_hasta=0.0, baile_hasta=0.0, nivel_volumen=0.0,
            voz_silenciada=False
        )
        img = QImage(280, 280, QImage.Format_ARGB32)
        p = QPainter(img)
        try:
            orbe.dibujar_orbe(p, cara, t=0.0, tam=280)
        finally:
            p.end()

        # El radio suave del núcleo debe ser ~45 px (< 50 px)
        self.assertTrue(orbe.radio_suave < 50.0)
        # El lienzo mide semieje 140 px, dejando > 85 px de margen exterior
        margen = 140.0 - orbe.radio_suave
        self.assertTrue(margen > 85.0)

    def test_fase_giro_acelerada_y_ripples_por_voz(self):
        import cara_holo_3d as h3d

        def _cara(hablando):
            return SimpleNamespace(
                hablando=hablando, escuchando=False, pensando=False,
                pensando_hasta=0.0, baile_hasta=0.0, nivel_volumen=0.0,
                voz_silenciada=False,
            )

        orbe = coh.GestorOrbeHibrido()
        cara = _cara(True)
        orbe.actualizar(cara, t=1.0, nivel_rms=0.0)
        inicio = orbe.fase_giro
        orbe.actualizar(cara, t=1.05, nivel_rms=0.0)
        giro_hablando = orbe.fase_giro - inicio

        cara = _cara(False)
        orbe.actualizar(cara, t=1.10, nivel_rms=0.0)
        inicio = orbe.fase_giro
        orbe.actualizar(cara, t=1.15, nivel_rms=0.0)
        giro_reposo = orbe.fase_giro - inicio
        self.assertGreater(giro_hablando, giro_reposo)

        cara = _cara(True)
        t = 1.20
        for nivel in (0.8, 0.0, 0.9):
            orbe.actualizar(cara, t=t, nivel_rms=nivel)
            t += 0.05
        self.assertGreaterEqual(len(orbe.ripples), 2)
        self.assertGreater(h3d.path_organico(45.0, 1.2, 0.8, True).boundingRect().width(),
                           h3d.path_organico(45.0, 1.2, 0.8, False).boundingRect().width())

    def test_flotacion_y_nucleo_070b14(self):
        orbe = coh.GestorOrbeHibrido()
        cara = SimpleNamespace(
            hablando=False, escuchando=False, pensando=False,
            pensando_hasta=0.0, baile_hasta=0.0, nivel_volumen=0.0,
            voz_silenciada=False,
        )
        img = QImage(280, 280, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        try:
            orbe.dibujar_orbe(p, cara, t=1.2, tam=280)
        finally:
            p.end()
        self.assertNotAlmostEqual(orbe.flotacion_y, 0.0, places=6)
        self.assertEqual((coh._OBSIDIANA.red(), coh._OBSIDIANA.green(), coh._OBSIDIANA.blue()),
                         (7, 11, 20))


if __name__ == "__main__":
    unittest.main()
