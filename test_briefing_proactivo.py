"""Pruebas unitarias para el módulo briefing_proactivo (Gmail, Calendar y Memoria)."""
import unittest
from unittest.mock import MagicMock, patch

import briefing_proactivo as bp


class TestBriefingProactivo(unittest.TestCase):
    """Test suite para filtrado de ruido, anti-repetición y paralelismo de briefing."""

    def test_filtro_correos_ruidosos(self):
        """Detecta y filtra correos publicitarios, newsletters y bots."""
        self.assertTrue(bp._es_correo_ruidoso("newsletter@tech.com", "Novedades de la semana"))
        self.assertTrue(bp._es_correo_ruidoso("no-reply@tienda.com", "Oferta exclusiva 50% de descuento"))
        self.assertTrue(bp._es_correo_ruidoso("Marketing Team <promo@banco.com>", "Actualizacion de terminos"))
        self.assertFalse(bp._es_correo_ruidoso("Carlos Gomez <carlos@empresa.com>", "Revisión del sprint de desarrollo"))
        self.assertFalse(bp._es_correo_ruidoso("Profesor Soto <docente@uni.edu>", "Notas finales del examen"))

    def test_limpiar_remitente(self):
        """Limpia cadenas de remitente complejas."""
        self.assertEqual(bp._limpiar_remitente("GitHub Notifications <notifications@github.com>"), "GitHub Notifications")
        self.assertEqual(bp._limpiar_remitente("soporte@miempresa.com"), "soporte")
        self.assertEqual(bp._limpiar_remitente("Moisés Guerrero"), "Moisés Guerrero")

    def test_anti_repeticion_de_alertas(self):
        """No repite correos o alertas ya avisadas en inicios recientes."""
        with patch("estado.cargar", return_value={"briefing_avisados": ["Carlos:Sprint"]}):
            with patch("estado.guardar") as mock_guardar:
                avisados = bp._obtener_avisados_recientes()
                self.assertIn("Carlos:Sprint", avisados)

                bp.registrar_alerta_avisada("Profesor:Examen")
                mock_guardar.assert_called_once()
                est_guardado = mock_guardar.call_args.args[0]
                self.assertIn("Profesor:Examen", est_guardado["briefing_avisados"])

    def test_recopilar_briefing_con_gmail_calendar_y_memoria(self):
        """Arma el dict de novedades en paralelo con mocks de Google Workspace."""
        mock_gmail = {
            "ok": True,
            "correos": [
                {"remitente": "marketing@spam.com", "asunto": "Descuento del mes"},
                {"remitente": "Ing. Morales <morales@obra.com>", "asunto": "Planos revisados"},
            ],
        }
        mock_cal = {
            "ok": True,
            "eventos": [
                {"titulo": "Entrega de Proyecto", "hora": "10:30 AM"},
            ],
        }

        with patch("google_workspace.resumen_correos", return_value=mock_gmail):
            with patch("google_workspace.agenda_hoy", return_value=mock_cal):
                with patch("briefing_proactivo._leer_memoria_hilos", return_value={"hilo_activo": "optimizar latencia"}):
                    with patch("briefing_proactivo._obtener_avisados_recientes", return_value=[]):
                        briefing = bp.recopilar_briefing_arranque(timeout_total=1.0)
                        self.assertIsNotNone(briefing.get("correo"))
                        self.assertEqual(briefing["correo"]["remitente"], "Ing. Morales")
                        self.assertEqual(briefing["correo"]["asunto"], "Planos revisados")
                        self.assertIsNotNone(briefing.get("evento"))
                        self.assertEqual(briefing["evento"]["titulo"], "Entrega de Proyecto")
                        self.assertEqual(briefing.get("hilo_activo"), "optimizar latencia")

    def test_timeout_y_fallo_silencioso(self):
        """Fallo en APIs o tiempo límite no rompe el flujo ni lanza excepciones."""
        with patch("google_workspace.resumen_correos", side_effect=TimeoutError("timed out")):
            with patch("google_workspace.agenda_hoy", side_effect=RuntimeError("no connection")):
                with patch("briefing_proactivo._leer_memoria_hilos", return_value={}):
                    res = bp.recopilar_briefing_arranque(timeout_total=0.2)
                    self.assertIsInstance(res, dict)
                    self.assertIsNone(res.get("correo"))
                    self.assertIsNone(res.get("evento"))


if __name__ == "__main__":
    unittest.main()
