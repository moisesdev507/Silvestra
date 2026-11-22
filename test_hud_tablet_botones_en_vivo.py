"""Pruebas unitarias para la conexión en vivo, autenticación por token y botones del HUD tablet."""
import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from ecosistema_contratos import Scope, TipoDispositivo
from ecosistema_gestor import GestorEcosistema, AlmacenEcosistema
from ecosistema_puente import EcosistemaPuente
from ecosistema_sse import BusSSE
import pantalla_remota_api as pra_api
import pantalla_remota_accion as pra_accion
import voz_dueno


class MockServer:
    def __init__(self, gestor, tls=True):
        self.gestor = gestor
        self.app = gestor.app
        self.bus_sse = gestor.bus_sse
        self.puente = gestor.puente
        self.tls = tls


class MockHandler:
    def __init__(self, server, method="GET", path="/", headers=None, body=None, client_ip="192.168.0.50"):
        self.server = server
        self.command = method
        self.path = path
        self.headers = dict(headers or {})
        self.client_address = (client_ip, 54321)
        if body is not None:
            raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
            self.headers["Content-Length"] = str(len(raw))
            self.rfile = BytesIO(raw)
        else:
            self.rfile = BytesIO(b"")
        if method == "POST" and "Origin" not in self.headers:
            self.headers["Origin"] = "https://192.168.0.7:8765"
        self.wfile = BytesIO()
        self.status = None
        self.response_headers = {}

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.response_headers[k] = v

    def end_headers(self):
        pass


class TestHudTabletBotonesEnVivo(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.cola = MagicMock()
        self.gestor = MagicMock()
        self.gestor.app = self.app
        self.gestor.ecosistema_gestor = GestorEcosistema(AlmacenEcosistema())
        self.gestor.bus_sse = BusSSE()
        self.gestor.puente = EcosistemaPuente(self.gestor.ecosistema_gestor, self.gestor.bus_sse,
                                              ["https://192.168.0.7:8765"])
        self.server = MockServer(self.gestor, tls=True)

    def test_sesion_entrega_token_y_empareja_lan(self):
        h = MockHandler(self.server, "GET", "/api/sesion", headers={"Host": "192.168.0.7:8765"})
        ident = pra_api._identidad(h, Scope.STATE_READ, mutacion=False)
        self.assertIsNotNone(ident)
        pra_api.responder_sesion(h, ident)
        self.assertEqual(h.status, 200)
        resp = json.loads(h.wfile.getvalue().decode("utf-8"))
        self.assertTrue(resp.get("ok"))
        self.assertIn("token", resp)
        self.assertTrue(len(resp["token"]) > 10)
        self.assertIn("Set-Cookie", h.response_headers)

    def test_autenticacion_por_token_header(self):
        pair = self.gestor.ecosistema_gestor.emparejar_lan(
            TipoDispositivo.TABLET_HUD, (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST)
        )
        token = pair["token"]
        h = MockHandler(self.server, "GET", "/api/panel/estado",
                        headers={"Host": "192.168.0.7:8765", "X-Device-Token": token})
        ident = pra_api._identidad(h, Scope.STATE_READ, mutacion=False)
        self.assertIsNotNone(ident)
        self.assertEqual(ident["device_id"], pair["device_id"])

    def test_acciones_botones_directas_sin_error_amarillo(self):
        pair = self.gestor.ecosistema_gestor.emparejar_lan(
            TipoDispositivo.TABLET_HUD, (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST)
        )
        token = pair["token"]

        # 1. Modo Normal / Programación
        for modo in ("normal", "programacion", "estudio", "noche"):
            h = MockHandler(self.server, "POST", "/api/panel/accion",
                            headers={"Host": "192.168.0.7:8765", "X-Device-Token": token,
                                     "Content-Type": "application/json"},
                            body={"accion": "activar_modo", "modo": modo})
            with patch("modos_sistema.activar_modo", return_value=(True, f"Modo {modo}", None)):
                pra_api.manejar_post(h, self.app, self.gestor)
            self.assertEqual(h.status, 200)
            res = json.loads(h.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("modo"), modo)

        # 2. Toggle Solo Dueño
        h_sd = MockHandler(self.server, "POST", "/api/panel/accion",
                           headers={"Host": "192.168.0.7:8765", "X-Device-Token": token,
                                    "Content-Type": "application/json"},
                           body={"accion": "toggle_solo_dueno"})
        with patch("pantalla_biometria.toggle_solo_dueno", return_value=True):
            pra_api.manejar_post(h_sd, self.app, self.gestor)
        self.assertEqual(h_sd.status, 200)
        res_sd = json.loads(h_sd.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res_sd.get("ok"))
        self.assertTrue(res_sd.get("solo_dueno"))

        # 3. Reforzar Voz
        h_rv = MockHandler(self.server, "POST", "/api/panel/accion",
                           headers={"Host": "192.168.0.7:8765", "X-Device-Token": token,
                                    "Content-Type": "application/json"},
                           body={"accion": "reforzar_voz"})
        with patch("pantalla_biometria.disparar_reforzar_voz", return_value={"ok": True}):
            pra_api.manejar_post(h_rv, self.app, self.gestor)
        self.assertEqual(h_rv.status, 200)
        res_rv = json.loads(h_rv.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res_rv.get("ok"))

        # 4. Respaldo
        h_res = MockHandler(self.server, "POST", "/api/panel/accion",
                            headers={"Host": "192.168.0.7:8765", "X-Device-Token": token,
                                     "Content-Type": "application/json"},
                            body={"accion": "crear_respaldo"})
        with patch("respaldo.generar_respaldo", return_value="respaldo.zip"):
            pra_api.manejar_post(h_res, self.app, self.gestor)
        self.assertEqual(h_res.status, 200)
        res_bk = json.loads(h_res.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res_bk.get("ok"))

        # 5. Privado / Normal
        h_priv = MockHandler(self.server, "POST", "/api/panel/accion",
                             headers={"Host": "192.168.0.7:8765", "X-Device-Token": token,
                                      "Content-Type": "application/json"},
                             body={"accion": "tablet_modo_privado"})
        pra_api.manejar_post(h_priv, self.app, self.gestor)
        self.assertEqual(h_priv.status, 200)
        self.assertTrue(self.gestor.ecosistema_gestor.modo_privado())

    def test_activar_hud_sin_duplicar_voz(self):
        mock_gestor = MagicMock()
        mock_gestor._servidor = MagicMock()
        mock_gestor.obtener_url_completa.return_value = "https://192.168.0.7:8765/"
        self.app.pantalla_remota = mock_gestor

        # Por defecto hablar_cola es False
        msg = pra_accion.activar_hud(app=self.app)
        self.assertIn("192.168.0.7:8765", msg)
        llamadas_hablar = [c for c in self.app.cola.put.call_args_list if c[0][0][0] == "hablar"]
        self.assertEqual(len(llamadas_hablar), 0, "No debe encolar hablar cuando hablar_cola=False")

    def test_voz_dueno_umbral_y_sensibilidad(self):
        vd = voz_dueno.VozDueno(self.app)
        self.assertEqual(vd.umbral, 0.35)


if __name__ == "__main__":
    unittest.main()
