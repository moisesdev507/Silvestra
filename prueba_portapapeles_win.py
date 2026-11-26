"""Portapapeles Windows: hilos, reintentos, bloqueo, Live, Celeste y ambiente."""
import asyncio
import concurrent.futures
import os
import threading
import unittest
from unittest.mock import patch

import capacidades_extra
import contexto_ambiental
import live_herramientas_extra
import portapapeles
import portapapeles_win
import resumen_media

RAIZ = os.path.dirname(os.path.abspath(__file__))


class _User32Falso:
    def __init__(self, fallos=0):
        self.fallos = fallos
        self.intentos = 0
        self.cierres = 0

    def OpenClipboard(self, _hwnd):
        self.intentos += 1
        return self.intentos > self.fallos

    def IsClipboardFormatAvailable(self, formato):
        return formato == portapapeles_win.CF_UNICODETEXT

    def GetClipboardData(self, _formato):
        return 1234

    def CloseClipboard(self):
        self.cierres += 1


class _Kernel32Falso:
    def __init__(self):
        self.bloqueos = 0
        self.desbloqueos = 0

    def GlobalLock(self, _handle):
        self.bloqueos += 1
        return 5678

    def GlobalUnlock(self, _handle):
        self.desbloqueos += 1


class TestLecturaWin32(unittest.TestCase):
    def test_reintentos_y_cierre_unico(self):
        user32, kernel32 = _User32Falso(fallos=3), _Kernel32Falso()
        dormidos = []
        with patch.object(portapapeles_win, "_api",
                          return_value=(user32, kernel32, lambda _p: "texto reintentado")), \
             patch.object(portapapeles_win.time, "sleep", side_effect=dormidos.append):
            texto = portapapeles_win.leer_portapapeles_windows(max_chars=1200)
        self.assertEqual(texto, "texto reintentado")
        self.assertEqual(user32.intentos, 4)
        self.assertEqual(dormidos, [portapapeles_win.ESPERA_REINTENTO_S] * 3)
        self.assertEqual(user32.cierres, 1)
        self.assertEqual((kernel32.bloqueos, kernel32.desbloqueos), (1, 1))

    def test_bloqueo_total_cae_a_powershell(self):
        user32, kernel32 = _User32Falso(fallos=99), _Kernel32Falso()
        with patch.object(portapapeles_win, "_api",
                          return_value=(user32, kernel32, lambda _p: "nunca")), \
             patch.object(portapapeles_win, "_leer_powershell", return_value="texto respaldo"), \
             patch.object(portapapeles_win.time, "sleep", side_effect=lambda _s: None):
            texto = portapapeles_win.leer_portapapeles_windows(max_chars=50)
        self.assertEqual(texto, "texto respaldo")
        self.assertEqual(user32.intentos, portapapeles_win.INTENTOS)
        self.assertEqual(user32.cierres, 0)
        self.assertEqual(kernel32.bloqueos, 0)

    def test_indisponible_devuelve_none_y_recorta(self):
        with patch.object(portapapeles_win, "_leer_win32_crudo", side_effect=RuntimeError), \
             patch.object(portapapeles_win, "_leer_powershell", return_value=None):
            self.assertIsNone(portapapeles_win.leer_portapapeles_windows())
        with patch.object(portapapeles_win, "_leer_win32_crudo", return_value="a" * 500):
            self.assertEqual(portapapeles_win.leer_portapapeles_windows(20), "a" * 20)

    def test_lectura_concurrente_desde_hilos(self):
        barrera = threading.Barrier(8)

        def crudo():
            barrera.wait(2)
            return threading.current_thread().name

        def leer(_i):
            return portapapeles_win.leer_portapapeles_windows()

        with patch.object(portapapeles_win, "_leer_win32_crudo", side_effect=crudo):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                resultados = list(pool.map(leer, range(8)))
        self.assertEqual(len(set(resultados)), 8)
        self.assertTrue(all(str(n).startswith("ThreadPoolExecutor") for n in resultados))

    def test_sin_tkinter_y_respaldo_raw(self):
        with open(os.path.join(RAIZ, "portapapeles_win.py"), encoding="utf-8") as f:
            fuente = f.read()
        self.assertNotIn("import tkinter", fuente)
        self.assertNotIn("from tkinter", fuente)
        self.assertIn("Get-Clipboard -Raw", fuente)
        self.assertIn("CloseClipboard()", fuente)


class TestIntegraciones(unittest.TestCase):
    def setUp(self):
        contexto_ambiental.limpiar()

    def tearDown(self):
        contexto_ambiental.limpiar()

    def test_contexto_usa_lector_y_no_sobrescribe_si_bloqueado(self):
        datos = contexto_ambiental.capturar(ventana="Editor", portapapeles="texto válido")
        self.assertEqual(datos["clipboard"], "texto válido")
        with patch.object(portapapeles_win, "leer_portapapeles_windows", return_value=None):
            bloqueado = contexto_ambiental.capturar(ventana="Editor")
        self.assertEqual(bloqueado["clipboard"], "texto válido")
        self.assertEqual(bloqueado["hash"], datos["hash"])
        self.assertEqual(bloqueado["cambio"], datos["cambio"])
        with patch.object(portapapeles_win, "leer_portapapeles_windows", return_value="") as leer:
            vacio = contexto_ambiental.capturar(ventana="Editor")
        self.assertTrue(leer.called)
        self.assertEqual(vacio["clipboard"], "")
        self.assertEqual(vacio["cambio"], 0.0)

    def test_herramienta_live_usa_lector(self):
        with patch.object(portapapeles_win, "leer_portapapeles_windows",
                          return_value="del live") as leer:
            res = asyncio.run(live_herramientas_extra.despachar("leer_portapapeles", {}))
        self.assertTrue(leer.called)
        self.assertIn("del live", res)

    def test_celeste_usa_lector_sin_qt(self):
        with patch.object(portapapeles_win, "leer_portapapeles_windows",
                          return_value="https://ejemplo.com") as leer:
            texto = resumen_media.obtener_texto_portapapeles()
        self.assertTrue(leer.called)
        self.assertEqual(texto, "https://ejemplo.com")
        with open(os.path.join(RAIZ, "resumen_media.py"), encoding="utf-8") as f:
            self.assertNotIn("QGuiApplication", f.read())

    def test_copiloto_clasico_y_capacidades_compartidas(self):
        with patch.object(portapapeles_win, "leer_portapapeles_windows",
                          return_value="tracebackreal"):
            self.assertEqual(portapapeles.leer_portapapeles(max_chars=100), "tracebackreal")
        with patch("portapapeles.leer_portapapeles", return_value="texto copiado"):
            self.assertIn("texto copiado", capacidades_extra.leer_portapapeles())


if __name__ == "__main__":
    unittest.main(verbosity=2)
