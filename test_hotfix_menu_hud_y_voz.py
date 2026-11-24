"""Regresión: voz Salomé/FRIDAY-Her y menú de opciones HUD en Qt offscreen."""
import asyncio
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import estado
import menu_hud
import voz
import voz_cache
import voz_estilo


class AppFalsa:
    """Doble mínimo de la aplicación para comprobar cambios en caliente."""

    def __init__(self):
        self.voz_silenciada = False
        self.hablado = []
        self.voz = SimpleNamespace(
            hablar=lambda texto, **kw: self.hablado.append((texto, kw)))
        self.palabra_clave = SimpleNamespace(siempre_atenta=True)
        self.voz_dueno = SimpleNamespace(modo_solo_dueno=False, activa=False)
        self.cara = SimpleNamespace(modo_activo="normal")
        self.modo_activo = "normal"

    def alternar_silencio(self):
        self.voz_silenciada = not self.voz_silenciada


class TestMenuHudYVoz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "estado.json")
        parche = patch.object(estado, "RUTA", self.ruta)
        parche.start()
        self.addCleanup(parche.stop)
        self.addCleanup(self.tmp.cleanup)
        QApplication.instance() or QApplication([])
        voz_cache.limpiar()

    def _guardar(self, **cambios):
        datos = estado.cargar()
        datos.update(cambios)
        estado.guardar(datos)
        return datos

    def test_salome_por_defecto_y_voz_desde_estado(self):
        self.assertEqual(voz.VOZ_EDGE, "es-CO-SalomeNeural")
        self.assertEqual(voz_estilo.voz_actual(), "es-CO-SalomeNeural")

        self._guardar(voz_edge="es-ES-XimenaNeural")
        self.assertEqual(voz_estilo.voz_actual(), "es-ES-XimenaNeural")
        self._guardar(voz_edge="voz-inexistente")
        self.assertEqual(voz_estilo.voz_actual(), "es-PA-MargaritaNeural")

    def test_estilos_auto_friday_y_her(self):
        self.assertEqual(voz_estilo.estilo_actual(), "auto")
        self.assertEqual(voz_estilo.estilo_para("neutral"), "friday")
        self.assertEqual(voz_estilo.ajustes("neutral"),
                         {"rate": "+2%", "pitch": "+1Hz", "volume": "+0%"})

        self.assertEqual(voz_estilo.estilo_para("cálida"), "her")
        self.assertEqual(voz_estilo.ajustes("cálida")["rate"], "-2%")
        self.assertEqual(voz_estilo.ajustes("cálida")["pitch"], "-1Hz")

        self._guardar(estilo_voz="her")
        self.assertEqual(voz_estilo.ajustes("neutral")["rate"], "-2%")
        self._guardar(estilo_voz="friday")
        self.assertEqual(voz_estilo.ajustes("cálida")["rate"], "+2%")

    def test_edge_tts_recibe_voz_y_estilo_elegidos(self):
        captura = {}

        class CommunicateFalso:
            def __init__(self, texto, voz_nombre, **kw):
                captura.update(texto=texto, voz=voz_nombre, **kw)

            async def stream(self):
                yield {"type": "audio", "data": b"AUDIO"}

        self._guardar(voz_edge="es-ES-XimenaNeural", estilo_voz="her")
        falso = SimpleNamespace(Communicate=CommunicateFalso)
        with patch.dict(sys.modules, {"edge_tts": falso}), \
             patch.object(voz_cache, "obtener_audio_cache", lambda *_a: None), \
             patch.object(voz_cache, "guardar_audio_cache", lambda *_a: None), \
             patch("voz_local.debe_ir_local_primero", lambda: False), \
             patch("voz_local.generar_edge",
                   lambda crear, frase, emo: asyncio.run(crear())), \
             patch("voz_local.fallback_local", lambda *_a: None):
            audio = voz.Voz._audio("Hola", "neutral")

        self.assertEqual(audio, b"AUDIO")
        self.assertEqual(captura["voz"], "es-ES-XimenaNeural")
        self.assertEqual(captura["rate"], "-2%")
        self.assertEqual(captura["pitch"], "-1Hz")

    def test_menu_refleja_estado_inicial_y_guarda_cambios(self):
        self._guardar(voz_edge="es-ES-XimenaNeural", estilo_voz="friday",
                      palabra_clave=False, modo_solo_dueno=True,
                      verificacion_voz_activa=True, modo_activo="estudio")
        app = AppFalsa()
        app.palabra_clave.siempre_atenta = False
        app.voz_dueno.modo_solo_dueno = True
        app.modo_activo = "estudio"

        menu = menu_hud.MenuHUD(app)
        try:
            self.assertEqual(menu.combo_voz.currentData(), "es-ES-XimenaNeural")
            self.assertEqual(menu.combo_estilo.currentData(), "friday")
            self.assertFalse(menu.chk_manos.isChecked())
            self.assertTrue(menu.chk_solo.isChecked())
            self.assertEqual(menu.combo_modo.currentData(), "estudio")

            menu.combo_voz.setCurrentIndex(
                menu.combo_voz.findData("es-CO-SalomeNeural"))
            menu.combo_estilo.setCurrentIndex(
                menu.combo_estilo.findData("her"))
            menu.chk_manos.setChecked(True)
            menu.btn_silenciar.click()
            menu.chk_solo.setChecked(False)
            menu.combo_modo.setCurrentIndex(
                menu.combo_modo.findData("programacion"))
            menu.btn_probar.click()

            datos = estado.cargar()
            self.assertEqual(datos["voz_edge"], "es-CO-SalomeNeural")
            self.assertEqual(datos["estilo_voz"], "her")
            self.assertTrue(datos["palabra_clave"])
            self.assertFalse(datos["modo_solo_dueno"])
            self.assertFalse(datos["verificacion_voz_activa"])
            self.assertEqual(datos["modo_activo"], "programacion")

            self.assertTrue(app.palabra_clave.siempre_atenta)
            self.assertTrue(app.voz_silenciada)
            self.assertFalse(app.voz_dueno.modo_solo_dueno)
            self.assertFalse(app.voz_dueno.activa)
            self.assertEqual(app.modo_activo, "programacion")
            self.assertEqual(app.cara.modo_activo, "programacion")
            self.assertEqual(len(app.hablado), 1)
            self.assertIn("Lyris", app.hablado[0][0])
        finally:
            menu.close()

    def test_abrir_desde_cara_reutiliza_un_solo_hud(self):
        app = AppFalsa()
        cara = SimpleNamespace(silvestra_app=app)
        primero = menu_hud.abrir(cara)
        try:
            self.assertIs(menu_hud.abrir(cara), primero)
            self.assertIs(primero.app, app)
        finally:
            primero.close()

    def test_cara_qt_tiene_enganche_del_hud(self):
        with open("cara_qt.py", encoding="utf-8") as archivo:
            fuente = archivo.read()
        self.assertIn('"Opciones HUD..."', fuente)
        self.assertIn("menu_hud.abrir(self)", fuente)


if __name__ == "__main__":
    unittest.main()
