"""Regresion de estabilidad Qt al minimizar o mostrar escritorio."""
from __future__ import annotations

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock

import qt_estabilidad_ui
import contexto_windows


class TestEstabilidadUiMinimizado(unittest.TestCase):
    def setUp(self):
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=False,
            visible=True,
            mostrar_escritorio=False,
        )

    def tearDown(self):
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=False,
            visible=True,
            mostrar_escritorio=False,
        )

    def test_1_ráfaga_cola_drenada_por_lotes(self):
        cola = queue.Queue()
        for i in range(100):
            cola.put(("evento", i))
        atendidos = []
        inicio = time.perf_counter()
        procesados, queda = qt_estabilidad_ui.drenar_cola_acotada(
            cola,
            lambda tipo, texto: atendidos.append((tipo, texto)),
            max_eventos=8,
            presupuesto_ms=15.0,
        )
        transcurrido = time.perf_counter() - inicio
        self.assertEqual(procesados, 8)
        self.assertTrue(queda)
        self.assertLess(transcurrido, 0.100)
        while qt_estabilidad_ui.drenar_cola_acotada(
            cola,
            lambda tipo, texto: atendidos.append((tipo, texto)),
            max_eventos=8,
            presupuesto_ms=15.0,
        )[1]:
            pass
        self.assertEqual(len(atendidos), 100)

    def test_2_minimizado_progman_suspende_ui(self):
        qt_estabilidad_ui.marcar_modo_escritorio("Progman")
        self.assertTrue(qt_estabilidad_ui.ui_suspender())
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=True,
            visible=True,
            mostrar_escritorio=False,
        )
        self.assertTrue(qt_estabilidad_ui.ui_suspender())
        self.assertFalse(qt_estabilidad_ui.puede_actualizar_ui())

    def test_3_restauracion_reanuda_una_vez(self):
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=True,
            visible=True,
            mostrar_escritorio=False,
        )
        self.assertFalse(qt_estabilidad_ui.puede_actualizar_ui())
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=False,
            visible=True,
            mostrar_escritorio=False,
        )
        self.assertTrue(qt_estabilidad_ui.puede_actualizar_ui())
        qt_estabilidad_ui.actualizar_estado_ui(
            minimizada=False,
            visible=True,
            mostrar_escritorio=False,
        )
        self.assertTrue(qt_estabilidad_ui.puede_actualizar_ui())

    def test_4_contexto_hwnd_vacio_y_escritorio(self):
        usuario = MagicMock()
        usuario.GetForegroundWindow.return_value = 0
        usuario.OpenInputDesktop.return_value = 0
        kernel = MagicMock()
        kernel.GetLastInputInfo.return_value = False
        kernel.GetTickCount.return_value = 0
        sensor = contexto_windows.SensorContextoWindows(
            user32_lib=usuario,
            kernel32_lib=kernel,
            dwmapi_lib=None,
        )
        datos = sensor.leer()
        self.assertIsNone(datos["hwnd"])
        self.assertEqual(datos["ejecutable"], "")
        for clase in ("Progman", "WorkerW", "Shell_TrayWnd"):
            qt_estabilidad_ui.marcar_modo_escritorio(clase)
            self.assertTrue(qt_estabilidad_ui.ui_suspender())


if __name__ == "__main__":
    unittest.main()
