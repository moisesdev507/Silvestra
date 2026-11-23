"""Regresión: manos libres 'Lyris' al arranque y silenciador rápido sin hablar."""
import os
import queue
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import conversacion
import estado
import eventos
import palabra_clave


class TestManosLibres(unittest.TestCase):
    @staticmethod
    def _app(en_conversacion=False, escuchando=False):
        app = SimpleNamespace(
            memoria=SimpleNamespace(nombre="Lyris", creador="Usuario"),
            cara=SimpleNamespace(poner_escuchando=lambda *_a: None),
            cola=queue.Queue(),
            voz=SimpleNamespace(ocupada=lambda: False),
            oido=SimpleNamespace(bloqueo=threading.RLock()),
            conversacion=en_conversacion,
            escuchando=escuchando,
            descansando=False,
            musica_activa=False,
            silencios=0,
            _generacion_escucha=0,
            _iniciar_reflexion=lambda: None,
            decir=lambda *_a, **_k: None,
            puede_hablar_sola=lambda: True,
        )
        app.alternar_conversacion = lambda motivo="evento": (
            conversacion.alternar_conversacion(app, motivo=motivo))
        return app

    @staticmethod
    def _detector(app):
        """Detector con estado sin clave (default True) y modelo simulado, sin Vosk."""
        with patch.object(estado, "cargar", lambda: {}), \
             patch.object(palabra_clave.PalabraClave, "_cargar_modelo", lambda self: None):
            detector = palabra_clave.PalabraClave(app)
        detector.modelo = object()
        return detector

    def test_default_estado_y_arranque_atento(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = os.path.join(temporal, "sin_estado.json")
            with patch.object(estado, "RUTA", ruta):
                self.assertIs(estado.cargar()["palabra_clave"], True)

        app = self._app()
        detector = self._detector(app)
        self.assertTrue(detector.siempre_atenta)
        self.assertTrue(detector.debe_escuchar())

    def test_silenciar_corta_escucha_y_bloquea_wakeword(self):
        app = self._app(en_conversacion=True, escuchando=True)
        detector = self._detector(app)
        app.palabra_clave = detector
        hablado = []
        app.decir = lambda *a, **k: hablado.append(a)

        self.assertTrue(conversacion.alternar_silencio(app))
        self.assertTrue(app.voz_silenciada)
        self.assertFalse(app.conversacion)
        self.assertFalse(app.escuchando)
        self.assertFalse(detector.siempre_atenta)
        self.assertFalse(detector.debe_escuchar())
        detector._disparar()
        self.assertTrue(app.cola.empty())
        self.assertEqual(hablado, [])

    def test_reanudar_reactiva_manos_libres(self):
        app = self._app()
        detector = self._detector(app)
        app.palabra_clave = detector
        hablado = []
        app.decir = lambda *a, **k: hablado.append(a)

        conversacion.alternar_silencio(app)
        hablado.clear()
        self.assertFalse(conversacion.alternar_silencio(app))
        self.assertFalse(app.voz_silenciada)
        self.assertTrue(detector.siempre_atenta)
        self.assertTrue(detector.debe_escuchar())
        detector._disparar()
        self.assertEqual(app.cola.get_nowait(),
                         ("alternar_conversacion", "palabra_clave_vosk"))
        self.assertEqual(hablado, [])

    def test_lyris_sigue_encolando_y_alternar_conversacion_intacto(self):
        app = self._app()
        detector = self._detector(app)
        app.palabra_clave = detector

        detector._disparar()
        self.assertEqual(app.cola.get_nowait(),
                         ("alternar_conversacion", "palabra_clave_vosk"))
        app.descansando = True
        detector._disparar()
        self.assertEqual(app.cola.get_nowait(), ("despertar", None))
        app.descansando = False

        with patch.object(conversacion, "escuchar", lambda _app: None):
            eventos.atender_evento(app, "alternar_conversacion", "palabra_clave_vosk")
        self.assertTrue(app.conversacion)
        conversacion.alternar_conversacion(app, "interfaz")
        self.assertFalse(app.conversacion)


if __name__ == "__main__":
    unittest.main()
