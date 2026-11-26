"""Pruebas aisladas del encendido por tecla de Kaya (sin hotkey nativa real)."""
import os
import queue
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

import tecla_kaya


class EventoFalso:
    def __init__(self, tecla):
        self._tecla = tecla
        self.aceptado = False

    def key(self):
        return self._tecla

    def accept(self):
        self.aceptado = True


class CaraFalsa:
    def __init__(self, app=None):
        self.silvestra_app = app
        self._ref_app = app
        self.visible = False
        self.foco = False

    def mostrar(self):
        self.visible = True

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def setFocus(self):
        self.foco = True


class TeclaKayaTests(unittest.TestCase):
    def test_tecla_configurada_y_mapa(self):
        with patch.dict(os.environ, {"KAYA_TECLA": "F9"}):
            self.assertEqual(tecla_kaya.tecla_desde_env(), "F9")
        with patch.dict(os.environ, {"KAYA_TECLA": "Invalida"}):
            self.assertEqual(tecla_kaya.tecla_desde_env(), tecla_kaya.POR_DEFECTO)
        self.assertEqual(tecla_kaya.modificadores_vk("Ctrl + Alt + K"),
                         (tecla_kaya.MOD_CONTROL | tecla_kaya.MOD_ALT, 0x4B))
        self.assertEqual(tecla_kaya.modificadores_vk("Alt + Espacio"),
                         (tecla_kaya.MOD_ALT, 0x20))
        self.assertEqual(tecla_kaya.modificadores_vk("F10"), (0, 0x79))
        self.assertIsNone(tecla_kaya.modificadores_vk("nada"))

    def test_pulsacion_local_encola_y_acepta(self):
        app = type("App", (), {"cola": queue.Queue()})()
        cara = CaraFalsa(app)
        evento = EventoFalso(Qt.Key_Space)
        self.assertTrue(tecla_kaya.pulsacion_local(cara, evento))
        self.assertTrue(evento.aceptado)
        self.assertEqual(list(app.cola.queue), [("kaya_tecla", "")])

    def test_pulsacion_local_ignora_otras_teclas(self):
        app = type("App", (), {"cola": queue.Queue()})()
        cara = CaraFalsa(app)
        evento = EventoFalso(Qt.Key_A)
        self.assertFalse(tecla_kaya.pulsacion_local(cara, evento))
        self.assertFalse(evento.aceptado)
        self.assertTrue(app.cola.empty())

    def test_atender_despierta_reposo_azul(self):
        llamadas = []

        class Puente:
            dormida = True

            def despertar(self):
                llamadas.append("despertar")

        class Sesion:
            _puente_webrtc = Puente()

        class Coordinador:
            sesion_live = Sesion()
            modo_live_habilitado = True

            def esta_live_activo(self):
                return False

            def intentar_activar_live(self, texto):
                llamadas.append(texto)
                return True

        app = type("App", (), {})()
        app.cara = CaraFalsa(app)
        app.descansando = False
        app.coordinador_live = Coordinador()
        app.alternar_conversacion = lambda motivo: llamadas.append("clasico")
        self.assertTrue(tecla_kaya.atender(app))
        self.assertFalse(app.coordinador_live.sesion_live._puente_webrtc.dormida)
        self.assertEqual(llamadas[0], "despertar")
        self.assertEqual(llamadas[1], "Kaya, estoy aquí.")
        self.assertTrue(app.cara.visible)
        self.assertTrue(app.cara.foco)

    def test_atender_sin_live_cae_al_modo_clasico(self):
        llamadas = []
        app = type("App", (), {})()
        app.cara = CaraFalsa(app)
        app.descansando = False
        app.coordinador_live = None
        app.alternar_conversacion = lambda motivo: llamadas.append(motivo)
        self.assertTrue(tecla_kaya.atender(app))
        self.assertEqual(llamadas, ["tecla"])


if __name__ == "__main__":
    unittest.main()
