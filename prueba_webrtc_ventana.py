"""Regresión: puente WebRTC oculto sin bienvenida y sin tocar el audio."""
import ctypes
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import live_webrtc
import webrtc_ventana as wv


class TestWebRTCVentana(unittest.TestCase):
    def test_preparar_perfil_crea_first_run_y_preferencias(self):
        with tempfile.TemporaryDirectory(prefix="kaya_edge_") as perfil:
            self.assertTrue(wv.preparar_perfil(perfil))
            self.assertTrue(os.path.isfile(os.path.join(perfil, "First Run")))
            ruta = os.path.join(perfil, "Default", "Preferences")
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
        self.assertTrue(datos["browser"]["has_seen_welcome_page"])
        self.assertFalse(datos["browser"]["show_welcome_page"])
        self.assertFalse(datos["edge"]["show_welcome_page"])
        self.assertEqual(datos["profile"]["exit_type"], "Normal")

    def test_preparar_perfil_conserva_preferencias_existentes(self):
        with tempfile.TemporaryDirectory(prefix="kaya_edge_") as perfil:
            os.makedirs(os.path.join(perfil, "Default"), exist_ok=True)
            ruta = os.path.join(perfil, "Default", "Preferences")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"browser": {"otro": 7}, "custom": "mantener"}, f)
            wv.preparar_perfil(perfil)
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
        self.assertEqual(datos["custom"], "mantener")
        self.assertEqual(datos["browser"]["otro"], 7)
        self.assertTrue(datos["browser"]["has_seen_welcome_page"])

    def test_comando_edge_incluye_flags_y_conserva_audio(self):
        cmd = wv.comando_edge("msedge.exe", r"C:\perfil", "http://127.0.0.1:1/#2")
        for flag in ("--no-first-run", "--no-default-browser-check", "--disable-sync",
                     "--use-fake-ui-for-media-stream",
                     "--autoplay-policy=no-user-gesture-required",
                     r"--user-data-dir=C:\perfil", "--app=http://127.0.0.1:1/#2"):
            self.assertIn(flag, cmd)

    @unittest.skipUnless(os.name == "nt", "STARTUPINFO existe solo en Windows")
    def test_startupinfo_oculta_proceso(self):
        info = wv.startupinfo_oculto()
        self.assertIsNotNone(info)
        self.assertEqual(info.wShowWindow, 0)
        self.assertTrue(info.dwFlags & 0x0001)

    def test_ocultar_ventana_pid_aplica_show_window(self):
        with patch.object(wv.os, "name", "nt"), \
             patch.object(ctypes, "windll", MagicMock()) as windll, \
             patch.object(ctypes, "byref", lambda valor: valor):
            user32 = windll.user32

            def _enum(callback, _dato):
                callback(123, 0)
                return 1

            user32.EnumWindows.side_effect = _enum
            user32.GetWindowThreadProcessId.side_effect = (
                lambda hwnd, ptr: setattr(ptr, "value", 4321))
            user32.GetWindowLongW.return_value = 0
            self.assertTrue(wv.ocultar_ventana_pid(4321, intentos=1, espera=0))
            user32.ShowWindow.assert_called_once_with(123, 0)

    def test_iniciar_puente_usa_helper_y_startupinfo(self):
        proceso = SimpleNamespace(pid=4321, terminate=MagicMock())
        captura = {}

        def _popen(cmd, **kwargs):
            captura["cmd"] = list(cmd)
            captura["kwargs"] = kwargs
            return proceso

        hilos = MagicMock()
        preparar = MagicMock(return_value=True)
        startup = MagicMock(return_value="SI")
        ocultar = MagicMock()
        with patch.object(live_webrtc, "buscar_navegador_webrtc", lambda: "msedge.exe"), \
             patch.object(live_webrtc, "_puerto_libre", side_effect=[18080, 18081]), \
             patch.object(live_webrtc, "_HTTPReutilizable", MagicMock()), \
             patch.object(live_webrtc, "threading", SimpleNamespace(Thread=hilos)), \
             patch.object(live_webrtc, "subprocess",
                          SimpleNamespace(Popen=_popen, CREATE_NO_WINDOW=0)), \
             patch.object(live_webrtc.wv, "preparar_perfil", preparar), \
             patch.object(live_webrtc.wv, "startupinfo_oculto", startup), \
             patch.object(live_webrtc.wv, "ocultar_ventana_pid", ocultar):
            puente = live_webrtc.PuenteWebRTC()
            self.assertTrue(puente.iniciar())
            puente.detener()

        self.assertTrue(preparar.called)
        self.assertEqual(captura["kwargs"]["startupinfo"], "SI")
        for flag in ("--no-first-run", "--no-default-browser-check", "--disable-sync"):
            self.assertIn(flag, captura["cmd"])
        llamadas_ocultar = [c for c in hilos.call_args_list
                            if c.kwargs.get("target") is ocultar]
        self.assertTrue(llamadas_ocultar)
        self.assertEqual(llamadas_ocultar[0].kwargs["args"], (4321,))

    def test_audio_y_websocket_quedan_intactos(self):
        with open("live_webrtc.py", encoding="utf-8") as f:
            codigo = f.read()
        for marca in ("getUserMedia(", "new AudioContext({sampleRate:16000})",
                      "createBufferSource()", "new Int16Array(pcm.length).buffer",
                      "websockets.serve", "24000", "bargeHasta"):
            self.assertIn(marca, codigo)


if __name__ == "__main__":
    unittest.main()
