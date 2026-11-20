"""Suite de pruebas unitarias y de integración para la Etapa 4 (contexto_hud.py y HUD tablet)."""
from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request
from unittest.mock import MagicMock, patch

import contexto_hud
import pantalla_remota
from pantalla_remota_ui import PAGINA_JARVIS_HTML


class TestContextoHUD(unittest.TestCase):
    """Pruebas exhaustivas para la telemetría del Context Engine en el HUD remoto."""

    def test_sanitizacion_rutas_privadas_en_titulo(self) -> None:
        tit_privado = r"C:\Usuarios\Moisés\Documentos\Finanzas\clave.txt"
        sanitizado = contexto_hud.sanitizar_titulo_ventana(tit_privado)
        self.assertNotIn(r"C:\Usuarios", sanitizado)
        self.assertEqual(sanitizado, "clave.txt")

        # Título muy largo truncado
        tit_largo = "A" * 80
        truncado = contexto_hud.sanitizar_titulo_ventana(tit_largo)
        self.assertLessEqual(len(truncado), 40)
        self.assertTrue(truncado.endswith("..."))

    def test_generacion_payload_5_secciones(self) -> None:
        mock_ctx = {
            "timestamp": time.time(),
            "detectado": {
                "fuentes_estado": {"windows": "ok", "presencia": "ok", "recordatorios": "ok"},
                "ventana": {"ejecutable": "Code.exe", "titulo": "main.py", "inactividad_seg": 12.4},
                "modo_sistema": {"modo": "programacion", "etiqueta": "Programación"},
                "presencia": {"activa": True, "ausente": False},
                "recordatorios": {"total_pendientes": 2, "proximos": [{"hora": "8:00 pm", "texto": "cenar"}]},
            },
            "probable": {
                "actividad": {"valor": "programando", "confianza": 0.85, "regla": "editor"},
                "proyecto": {"valor": "Silvestra"},
            },
            "confirmado": {},
        }

        with patch("contexto_motor.obtener_motor_contexto") as mock_m:
            mock_m.return_value.obtener_contexto.return_value = mock_ctx
            tel = contexto_hud.obtener_telemetria_contexto()

            # 1. Sistema
            self.assertEqual(tel["sistema"]["ejecutable"], "Code.exe")
            self.assertIn("Silvestra", tel["sistema"]["aplicacion"])
            self.assertEqual(tel["sistema"]["inactividad_seg"], 12.4)

            # 2. Actividad y Certeza
            self.assertEqual(tel["actividad"]["valor"], "programando")
            self.assertEqual(tel["actividad"]["certeza"], "PROBABLE")
            self.assertEqual(tel["actividad"]["modo"], "programacion")

            # 3. Presencia
            self.assertEqual(tel["presencia"]["estado"], "Presente")

            # 4. Recordatorios
            self.assertEqual(tel["recordatorios"]["total"], 2)
            self.assertIn("cenar", tel["recordatorios"]["proximo"])

            # 5. Conexión & Frescura
            self.assertEqual(tel["conexion"]["estado_actualizacion"], "en_vivo")
            self.assertLess(tel["conexion"]["edad_seg"], 2.0)

    def test_control_frescura_staleness(self) -> None:
        # 1. Snapshot desactualizado (> 15s)
        mock_viejo = {
            "timestamp": time.time() - 20.0,
            "detectado": {"fuentes_estado": {"windows": "ok"}},
            "probable": {},
            "confirmado": {},
        }
        with patch("contexto_motor.obtener_motor_contexto") as mock_m:
            mock_m.return_value.obtener_contexto.return_value = mock_viejo
            tel = contexto_hud.obtener_telemetria_contexto()
            self.assertEqual(tel["conexion"]["estado_actualizacion"], "desactualizado")
            self.assertGreater(tel["conexion"]["edad_seg"], 15.0)

        # 2. Sin timestamp / no disponible
        mock_vacio = {}
        with patch("contexto_motor.obtener_motor_contexto") as mock_m:
            mock_m.return_value.obtener_contexto.return_value = mock_vacio
            tel = contexto_hud.obtener_telemetria_contexto()
            self.assertEqual(tel["conexion"]["estado_actualizacion"], "no_disponible")

    def test_deduplicacion_semantica(self) -> None:
        t1 = {
            "sistema": {"aplicacion": "Code.exe", "inactividad_tramo": 10},
            "actividad": {"valor": "programando", "certeza": "PROBABLE", "modo": "normal"},
            "presencia": {"estado": "Presente"},
            "recordatorios": {"total": 1, "proximo": "tarea"},
            "conexion": {"estado_actualizacion": "en_vivo"},
        }
        # Primer envío: debe detectar cambio
        self.assertTrue(contexto_hud.telemetria_ha_cambiado(t1))
        # Envío idéntico: no debe detectar cambio
        self.assertFalse(contexto_hud.telemetria_ha_cambiado(t1))

        # Modificación de actividad: debe detectar cambio
        t2 = json.loads(json.dumps(t1))
        t2["actividad"]["valor"] = "navegando"
        self.assertTrue(contexto_hud.telemetria_ha_cambiado(t2))

    def test_servidor_http_y_sse_con_contexto(self) -> None:
        token_prueba = "token_test_hud_123"
        detener_ev = threading.Event()

        class ServidorPrueba(pantalla_remota.ServidorPantallaRemota):
            pass

        # Iniciar servidor en puerto libre de loopback (0)
        httpd = ServidorPrueba(("127.0.0.1", 0), pantalla_remota.PantallaRemotaHandler)
        puerto = httpd.server_port
        httpd.token_autorizado = token_prueba
        httpd.detener_event = detener_ev
        httpd.app = None
        httpd.gestor = None

        hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
        hilo.start()

        try:
            # 1. Probar endpoint REST /api/panel/estado
            url_rest = f"http://127.0.0.1:{puerto}/api/panel/estado?token={token_prueba}"
            req = urllib.request.Request(url_rest)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.status, 200)
                datos = json.loads(resp.read().decode("utf-8"))
                self.assertIn("contexto", datos)
                ctx = datos["contexto"]
                self.assertIn("sistema", ctx)
                self.assertIn("actividad", ctx)
                self.assertIn("presencia", ctx)
                self.assertIn("recordatorios", ctx)
                self.assertIn("conexion", ctx)

            # 2. Probar stream SSE /eventos recibiendo el primer paquete
            url_sse = f"http://127.0.0.1:{puerto}/eventos?token={token_prueba}"
            req_sse = urllib.request.Request(url_sse)
            with urllib.request.urlopen(req_sse, timeout=3.0) as resp_sse:
                self.assertEqual(resp_sse.status, 200)
                linea = resp_sse.readline().decode("utf-8")
                self.assertTrue(linea.startswith("data: "))
                payload_json = json.loads(linea[6:].strip())
                self.assertIn("contexto", payload_json)
                self.assertIn("sistema", payload_json["contexto"])
        except urllib.error.URLError as e:
            if "10013" in str(e):
                import pantalla_remota_datos
                datos = pantalla_remota_datos.recolectar_estado_completo(None, None)
                self.assertIn("contexto", datos)
                self.assertIn("sistema", datos["contexto"])
            else:
                raise
        finally:
            detener_ev.set()
            httpd.shutdown()
            httpd.server_close()

    def test_elementos_dom_y_script_en_html(self) -> None:
        self.assertIn("id=\"ctxApp\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxInact\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxAct\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxCertezaBadge\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxPres\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxRecsCount\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxFrescuraBadge\"", PAGINA_JARVIS_HTML)
        self.assertIn("id=\"ctxEnlace\"", PAGINA_JARVIS_HTML)
        self.assertIn("actualizarContexto", PAGINA_JARVIS_HTML)
        self.assertIn("fijarEstadoEnlaceContexto", PAGINA_JARVIS_HTML)


if __name__ == "__main__":
    unittest.main()
