"""Pruebas unitarias y de integración para contexto_windows.py."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import MagicMock

from contexto_windows import (
    LASTINPUTINFO,
    PROCESS_QUERY_LIMITED_INFORMATION,
    SensorContextoWindows,
    obtener_contexto_windows,
)


class TestSensorContextoWindows(unittest.TestCase):
    """Batería de pruebas unitarias simulando escenarios reales de Windows."""

    def test_lectura_normal_exitosa(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        # Simular GetForegroundWindow -> 1001
        mock_u32.GetForegroundWindow.return_value = 1001

        # Simular GetWindowTextLengthW -> 8
        mock_u32.GetWindowTextLengthW.return_value = 8

        def fake_get_text(hwnd, buf, max_count):
            buf.value = "VS Code"
            return 8

        mock_u32.GetWindowTextW.side_effect = fake_get_text

        # Simular GetWindowThreadProcessId -> PID 5432
        def fake_get_pid(hwnd, byref_pid):
            byref_pid._obj.value = 5432
            return 1

        mock_u32.GetWindowThreadProcessId.side_effect = fake_get_pid

        # Simular OpenProcess -> Handle válido (ej. 999)
        mock_k32.OpenProcess.return_value = 999

        def fake_query_image(handle, flags, buf, size_ptr):
            buf.value = r"C:\Program Files\Microsoft VS Code\Code.exe"
            return 1

        mock_k32.QueryFullProcessImageNameW.side_effect = fake_query_image
        mock_k32.CloseHandle.return_value = 1

        # Simular GetLastInputInfo (inactividad 2500 ms = 2.5 s)
        def fake_last_input(byref_lii):
            byref_lii._obj.dwTime = 100000
            return 1

        mock_u32.GetLastInputInfo.side_effect = fake_last_input
        mock_k32.GetTickCount.return_value = 102500

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        res = sensor.leer()

        self.assertEqual(res["hwnd"], 1001)
        self.assertEqual(res["titulo"], "VS Code")
        self.assertEqual(res["pid"], 5432)
        self.assertEqual(res["ejecutable"], "Code.exe")
        self.assertEqual(res["inactividad_seg"], 2.5)
        self.assertEqual(res["nivel"], "detectado")
        self.assertTrue(res["disponible"])
        self.assertIsInstance(res["timestamp"], float)

        # Verificar que OpenProcess usó PROCESS_QUERY_LIMITED_INFORMATION
        mock_k32.OpenProcess.assert_called_once_with(
            PROCESS_QUERY_LIMITED_INFORMATION, False, 5432
        )
        # Verificar que CloseHandle SIEMPRE se llamó
        mock_k32.CloseHandle.assert_called_once_with(999)

    def test_hwnd_cero_pantalla_bloqueada_o_escritorio(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        # Sin ventana activa (0 o None)
        mock_u32.GetForegroundWindow.return_value = 0
        mock_u32.GetLastInputInfo.return_value = 0

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        res = sensor.leer()

        self.assertIsNone(res["hwnd"])
        self.assertEqual(res["titulo"], "")
        self.assertIsNone(res["pid"])
        self.assertEqual(res["ejecutable"], "")
        self.assertEqual(res["inactividad_seg"], 0.0)
        self.assertTrue(res["disponible"])
        mock_k32.OpenProcess.assert_not_called()

    def test_error_permisos_openprocess_access_denied(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        mock_u32.GetForegroundWindow.return_value = 2002
        mock_u32.GetWindowTextLengthW.return_value = 14

        def fake_text(h, b, m):
            b.value = "Administrador"
            return 14

        mock_u32.GetWindowTextW.side_effect = fake_text

        def fake_pid(h, bp):
            bp._obj.value = 4  # Proceso System / protegido
            return 1

        mock_u32.GetWindowThreadProcessId.side_effect = fake_pid

        # OpenProcess falla con 0 (NULL) por permisos insuficientes
        mock_k32.OpenProcess.return_value = 0

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        res = sensor.leer()

        self.assertEqual(res["hwnd"], 2002)
        self.assertEqual(res["titulo"], "Administrador")
        self.assertEqual(res["pid"], 4)
        self.assertEqual(res["ejecutable"], "")
        self.assertTrue(res["disponible"])
        mock_k32.CloseHandle.assert_not_called()

    def test_proceso_desaparece_a_mitad_de_consulta(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        mock_u32.GetForegroundWindow.return_value = 3003
        mock_u32.GetWindowTextLengthW.return_value = 0

        def fake_pid(h, bp):
            bp._obj.value = 9876
            return 1

        mock_u32.GetWindowThreadProcessId.side_effect = fake_pid

        # OpenProcess lanza excepción porque el proceso murió
        mock_k32.OpenProcess.side_effect = OSError("Proceso terminado")

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        res = sensor.leer()

        self.assertEqual(res["hwnd"], 3003)
        self.assertEqual(res["titulo"], "")
        self.assertEqual(res["pid"], 9876)
        self.assertEqual(res["ejecutable"], "")
        self.assertTrue(res["disponible"])

    def test_desbordamiento_32bits_get_tick_count(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        # Simular caso de wrap-around: lii.dwTime cercano a 0xFFFFFFFF y tick_actual ya reiniciado
        def fake_last_input(byref_lii):
            byref_lii._obj.dwTime = 0xFFFFFF00  # Cerca del máximo de 32 bits
            return 1

        mock_u32.GetLastInputInfo.side_effect = fake_last_input
        # Tick tras desborde (ej. 0x00000100) -> delta = 0x200 = 512 ms
        mock_k32.GetTickCount.return_value = 0x00000100

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        inact = sensor._obtener_inactividad_segundos()

        self.assertAlmostEqual(inact, 0.512, places=3)

    def test_close_handle_garantizado_ante_error_en_query(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()

        mock_k32.OpenProcess.return_value = 888
        mock_k32.QueryFullProcessImageNameW.side_effect = RuntimeError("Error I/O")

        sensor = SensorContextoWindows(user32_lib=mock_u32, kernel32_lib=mock_k32)
        nombre = sensor._obtener_nombre_ejecutable(1234)

        self.assertEqual(nombre, "")
        mock_k32.CloseHandle.assert_called_once_with(888)

    def test_input_desktop_descarta_cloaked_y_clases_sistema(self) -> None:
        mock_u32 = MagicMock()
        mock_k32 = MagicMock()
        mock_dwm = MagicMock()

        # Simular OpenInputDesktop válido
        mock_u32.OpenInputDesktop.return_value = 777
        mock_u32.IsWindowVisible.return_value = 1
        mock_u32.IsIconic.return_value = 0

        # HWND 101 está cloaked (1), los demás no (0)
        def fake_dwm_attr(hwnd, attr, ptr, size):
            ptr._obj.value = 1 if hwnd == 101 else 0
            return 0  # S_OK

        mock_dwm.DwmGetWindowAttribute.side_effect = fake_dwm_attr

        def fake_get_class(hwnd, buf, max_count):
            if hwnd == 102:
                buf.value = "Progman"
                return 7
            buf.value = "Notepad"
            return 7

        mock_u32.GetClassNameW.side_effect = fake_get_class

        def fake_get_text(hwnd, buf, max_count):
            buf.value = "Editor"
            return 6

        mock_u32.GetWindowTextLengthW.return_value = 6
        mock_u32.GetWindowTextW.side_effect = fake_get_text

        def fake_get_pid(hwnd, byref_pid):
            byref_pid._obj.value = 5000 + hwnd
            return 1

        mock_u32.GetWindowThreadProcessId.side_effect = fake_get_pid
        mock_k32.OpenProcess.return_value = 999

        def fake_query_img(h, f, buf, s):
            buf.value = r"C:\Windows\notepad.exe"
            return 1

        mock_k32.QueryFullProcessImageNameW.side_effect = fake_query_img

        def fake_enum(handle, cb, lparam):
            cb(101, 0)
            cb(102, 0)
            cb(103, 0)
            return 1

        mock_u32.EnumDesktopWindows.side_effect = fake_enum

        sensor = SensorContextoWindows(
            user32_lib=mock_u32, kernel32_lib=mock_k32, dwmapi_lib=mock_dwm
        )
        res = sensor._obtener_ventana_input_desktop()

        self.assertIsNotNone(res)
        self.assertEqual(res[0], 103)
        self.assertEqual(res[2], "notepad.exe")
        mock_u32.CloseDesktop.assert_called_once_with(777)

    def test_funcion_conveniencia_obtener_contexto_windows(self) -> None:
        ctx = obtener_contexto_windows()
        self.assertIsInstance(ctx, dict)
        self.assertIn("hwnd", ctx)
        self.assertIn("titulo", ctx)
        self.assertIn("pid", ctx)
        self.assertIn("ejecutable", ctx)
        self.assertIn("inactividad_seg", ctx)
        self.assertEqual(ctx.get("nivel"), "detectado")
        self.assertTrue(ctx.get("disponible"))


if __name__ == "__main__":
    unittest.main()
