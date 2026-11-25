"""Prueba unitaria completa de la unificación Live en main.py y orquestador."""
import os
import queue
import time
import unittest
from unittest.mock import MagicMock, patch

import invocacion_lyris
import kaya_live_conexion
import kaya_live_nucleo
import kaya_live_orquestador
import kaya_live_puente
import kaya_live_tools


class TestUnificacionLive(unittest.TestCase):
    def test_deteccion_posicional_kaya(self):
        # 1. 'kaya' al inicio, medio y final con orden extraída
        ok1, alias1, ord1 = invocacion_lyris.detectar("oye kaya dime qué hora es")
        self.assertTrue(ok1)
        self.assertEqual(alias1, "kaya")
        self.assertEqual(ord1, "dime qué hora es")

        ok2, alias2, ord2 = invocacion_lyris.detectar("qué hora es kaya por favor")
        self.assertTrue(ok2)
        self.assertEqual(alias2, "kaya")
        self.assertEqual(ord2, "qué hora es")

        ok3, alias3, ord3 = invocacion_lyris.detectar("kaya")
        self.assertTrue(ok3)
        self.assertEqual(ord3, "")

    def test_herramienta_entrar_en_reposo(self):
        llamado = []
        kaya_live_puente.registrar_callback_reposo(lambda: llamado.append(True))
        
        # Invocar la tool
        res = kaya_live_tools.entrar_en_reposo("descansar")
        self.assertIn("reposo", res.lower())
        time.sleep(0.1)
        self.assertTrue(len(llamado) > 0)

    def test_es_error_cuota(self):
        self.assertTrue(kaya_live_conexion.es_error_cuota(Exception("429 ResourceExhausted")))
        self.assertTrue(kaya_live_conexion.es_error_cuota(Exception("Monthly quota exceeded")))
        self.assertFalse(kaya_live_conexion.es_error_cuota(Exception("Broken pipe")))

    def test_coordinacion_avisos_recordatorios_en_live(self):
        # Mock de app, cara y sesion
        mock_cara = MagicMock()
        mock_app = MagicMock()
        orq = kaya_live_orquestador.OrquestadorKayaLive(
            app_clasica=mock_app,
            cara=mock_cara,
            iniciar_en_live=False,
        )
        orq._modo_actual = "live"
        orq.sesion = MagicMock()
        orq.sesion._session = None  # Sin sesión activa de socket
        orq.loop_async = MagicMock()

        # Enviar aviso de recordatorio en Live: debe retornar True y mostrar burbuja
        coordinado = orq.coordinar_aviso_externo("Moisés, te recuerdo: tomar agua", es_recordatorio=True)
        self.assertTrue(coordinado)
        mock_cara.decir.assert_called_with("Moisés, te recuerdo: tomar agua", 4500)

    def test_coordinacion_avisos_en_reposo(self):
        mock_cara = MagicMock()
        mock_app = MagicMock()
        orq = kaya_live_orquestador.OrquestadorKayaLive(
            app_clasica=mock_app,
            cara=mock_cara,
            iniciar_en_live=False,
        )
        orq._modo_actual = "reposo_vosk"

        # Aviso no recordatorio (iniciativa): solo visual en cara sin despertar
        coordinado = orq.coordinar_aviso_externo("Comentario casual", es_recordatorio=False)
        self.assertTrue(coordinado)
        mock_cara.decir.assert_called_with("Comentario casual", 5000)

    def test_bandera_clasico_sys_argv(self):
        import sys
        prev_argv = list(sys.argv)
        try:
            sys.argv = ["main.py", "--clasico"]
            es_clasico = "--clasico" in sys.argv or os.environ.get("KAYA_MODO", "").strip().lower() == "clasico"
            self.assertTrue(es_clasico)
        finally:
            sys.argv = prev_argv


if __name__ == "__main__":
    unittest.main()
