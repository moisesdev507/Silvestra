"""Suite de pruebas de integración para la Etapa 3 del Silvestra Context Engine.

Verifica la conexión pasiva y segura entre contexto_motor, contexto_prompt,
cerebro_prompt y el ciclo de vida de la aplicación.
"""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from cerebro_prompt import construir_prompt
import contexto_motor
import contexto_prompt


class TestContextoIntegracion(unittest.TestCase):
    """Pruebas de integración de contexto situacional con cerebro_prompt y proveedores."""

    def setUp(self) -> None:
        self.mock_memoria = MagicMock()
        self.mock_memoria.nombre = "Silvestra"
        self.mock_memoria.creador = "Moisés"
        self.mock_memoria.proposito = "asistente personal"
        self.mock_memoria.hechos = ["Vive en Panamá", "Le gusta programar"]
        self.mock_memoria.vocabulario = set()

    def test_contexto_disponible_completo_en_prompt(self) -> None:
        motor = contexto_motor.obtener_motor_contexto()
        # Inyectar datos activos
        mock_ctx = {
            "timestamp": time.time(),
            "detectado": {
                "fuentes_estado": {
                    "windows": "ok",
                    "modos_sistema": "ok",
                    "recordatorios": "ok",
                    "presencia": "ok",
                },
                "ventana": {
                    "ejecutable": "Code.exe",
                    "titulo": "main.py - Proyecto_Silvestra - Visual Studio Code",
                    "inactividad_seg": 15.0,
                },
                "modo_sistema": {"modo": "programacion"},
                "presencia": {"activa": True, "ausente": True},
                "recordatorios": {
                    "total_pendientes": 1,
                    "proximos": [{"texto": "reunión equipo"}],
                },
            },
            "probable": {
                "actividad": {"valor": "programando", "confianza": 0.85},
                "proyecto": {"valor": "Proyecto_Silvestra"},
            },
            "confirmado": {
                "foco": {"valor": "depuración", "origen": "usuario"},
            },
        }

        with patch.object(motor, "obtener_contexto", return_value=mock_ctx):
            prompt = construir_prompt(self.mock_memoria, texto_actual="¿Qué hora es?")

            self.assertIn("[CONTEXTO (discreto)]", prompt)
            self.assertIn("Code.exe [Proyecto_Silvestra]", prompt)
            self.assertIn("modo:programacion", prompt)
            self.assertIn("dueño:ausente", prompt)
            self.assertIn("rec:reunión equipo", prompt)
            self.assertIn("PROBABLE: programando", prompt)
            self.assertIn("CONFIRMADO: foco='depuración'", prompt)
            self.assertIn("*Regla: PROBABLE es hipótesis", prompt)

            # Verificar presupuesto aproximado de tokens del bloque de contexto
            directiva = contexto_prompt.generar_directiva_contexto()
            toks_est = len(directiva) / 3.6
            self.assertLessEqual(toks_est, 80.0)

    def test_contexto_no_disponible_o_fallo_motor(self) -> None:
        with patch("contexto_prompt.generar_directiva_contexto", return_value=""):
            prompt = construir_prompt(self.mock_memoria, texto_actual="hola")
            self.assertNotIn("[CONTEXTO", prompt)
            self.assertIn("Te llamas Silvestra", prompt)

        # Simular que el motor lanza excepción al consultarse
        with patch("contexto_motor.obtener_motor_contexto", side_effect=RuntimeError("Fallo motor")):
            directiva = contexto_prompt.generar_directiva_contexto()
            self.assertEqual(directiva, "")
            prompt2 = construir_prompt(self.mock_memoria, texto_actual="hola")
            self.assertNotIn("[CONTEXTO", prompt2)

    def test_descarte_por_antiguedad_staleness(self) -> None:
        # Snapshot viejo (> 20 segundos en el pasado)
        mock_ctx_viejo = {
            "timestamp": time.time() - 25.0,
            "detectado": {
                "fuentes_estado": {"windows": "ok"},
                "ventana": {"ejecutable": "chrome.exe", "inactividad_seg": 0.0},
            },
            "probable": {"actividad": {"valor": "navegando"}},
            "confirmado": {},
        }
        res = contexto_prompt.formatear_contexto_para_prompt(mock_ctx_viejo)
        self.assertEqual(res, "")

    def test_certeza_vs_incertidumbre_reglas_discrecion(self) -> None:
        ctx_prob = {
            "timestamp": time.time(),
            "detectado": {
                "fuentes_estado": {"windows": "ok"},
                "ventana": {"ejecutable": "Code.exe", "inactividad_seg": 2.0},
            },
            "probable": {"actividad": {"valor": "programando", "confianza": 0.85}},
            "confirmado": {},
        }
        res = contexto_prompt.formatear_contexto_para_prompt(ctx_prob)
        self.assertIn("PROBABLE: programando (hipótesis)", res)
        self.assertNotIn("CONFIRMADO: programando", res)
        self.assertIn("jamás finjas ver su pantalla", res)

    def test_compatibilidad_flujo_cerebro(self) -> None:
        from cerebro import Cerebro
        cerebro = Cerebro(cliente=MagicMock(), memoria=self.mock_memoria)
        inst = cerebro.instrucciones("consulta de prueba")
        self.assertIsInstance(inst, str)
        self.assertIn("Te llamas Silvestra", inst)

    def test_concurrencia_construccion_prompt_y_actualizacion_motor(self) -> None:
        motor = contexto_motor.obtener_motor_contexto()
        errores: list[Exception] = []

        def worker_prompt():
            try:
                for _ in range(20):
                    p = construir_prompt(self.mock_memoria, texto_actual="probando")
                    self.assertTrue(len(p) > 200)
                    time.sleep(0.005)
            except Exception as e:
                errores.append(e)

        def worker_motor():
            try:
                for i in range(20):
                    motor.confirmar_contexto("estado", f"paso_{i}", ttl_seg=1.0)
                    motor.actualizar(forzar=False)
                    time.sleep(0.005)
            except Exception as e:
                errores.append(e)

        hilos = [
            threading.Thread(target=worker_prompt),
            threading.Thread(target=worker_prompt),
            threading.Thread(target=worker_motor),
            threading.Thread(target=worker_motor),
        ]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=4.0)

        self.assertEqual(len(errores), 0)


if __name__ == "__main__":
    unittest.main()
