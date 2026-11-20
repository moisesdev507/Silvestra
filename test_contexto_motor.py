"""Suite de pruebas unitarias y de integración para contexto_motor.py (Etapa 2)."""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from contexto_motor import (
    MotorContexto,
    obtener_contexto_actual,
    obtener_motor_contexto,
    resumen_contexto_compacto,
)


class TestMotorContexto(unittest.TestCase):
    """Pruebas exhaustivas para el Motor de Contexto Situacional de Silvestra."""

    def setUp(self) -> None:
        self.mock_sensor = MagicMock()
        self.mock_sensor.leer.return_value = {
            "hwnd": 1234,
            "titulo": "contexto_motor.py - Proyecto_Silvestra - Visual Studio Code",
            "pid": 5678,
            "ejecutable": "Code.exe",
            "inactividad_seg": 15.0,
            "disponible": True,
        }
        self.mock_app = MagicMock()
        self.mock_app.modo_activo = "normal"
        self.mock_app.presencia = None
        self.mock_app.iniciativa = None
        self.mock_app.memoria = None
        self.motor = MotorContexto(app=self.mock_app, sensor_windows=self.mock_sensor)

    def tearDown(self) -> None:
        self.motor.detener()

    def test_lectura_y_normalizacion_3_niveles(self) -> None:
        ctx = self.motor.actualizar(forzar=True)

        self.assertIn("detectado", ctx)
        self.assertIn("probable", ctx)
        self.assertIn("confirmado", ctx)

        det = ctx["detectado"]
        self.assertEqual(det["ventana"]["ejecutable"], "Code.exe")
        self.assertEqual(det["fuentes_estado"]["windows"], "ok")

        prob = ctx["probable"]
        self.assertEqual(prob["actividad"]["valor"], "programando")
        self.assertGreaterEqual(prob["actividad"]["confianza"], 0.8)
        self.assertFalse(prob["actividad"]["permite_accion_automatica"])
        self.assertEqual(prob["proyecto"]["valor"], "Proyecto_Silvestra")

        conf = ctx["confirmado"]
        self.assertEqual(conf, {})

    def test_tolerancia_a_fallos_fuentes(self) -> None:
        self.mock_sensor.leer.side_effect = RuntimeError("Fallo driver user32")

        with patch("modos_sistema.obtener_modo_activo", side_effect=Exception("Error DB")):
            with patch("recordatorios._cargar", side_effect=IOError("Disco inaccesible")):
                ctx = self.motor.actualizar(forzar=True)

        det = ctx["detectado"]
        self.assertEqual(det["fuentes_estado"]["windows"], "error")
        self.assertEqual(det["fuentes_estado"]["modos_sistema"], "error")
        self.assertEqual(det["fuentes_estado"]["recordatorios"], "error")

        # El motor no colapsa y entrega valores por defecto seguros
        self.assertEqual(det["modo_sistema"]["modo"], "normal")
        self.assertEqual(det["recordatorios"]["total_pendientes"], 0)

    def test_confirmacion_contexto_y_expiracion_ttl(self) -> None:
        # Confirmar dato con TTL corto (0.15s)
        self.motor.confirmar_contexto("estado_animo", "cansado", origen="usuario", ttl_seg=0.15)
        # Confirmar dato persistente (sin TTL)
        self.motor.confirmar_contexto("tarea_actual", "auditoría", origen="manual", ttl_seg=None)

        ctx = self.motor.obtener_contexto()
        conf = ctx["confirmado"]
        self.assertIn("estado_animo", conf)
        self.assertEqual(conf["estado_animo"]["valor"], "cansado")
        self.assertEqual(conf["tarea_actual"]["valor"], "auditoría")

        # Esperar expiración de estado_animo
        time.sleep(0.20)
        ctx2 = self.motor.actualizar(forzar=True)
        conf2 = ctx2["confirmado"]
        self.assertNotIn("estado_animo", conf2)
        self.assertIn("tarea_actual", conf2)

        # Limpiar individual y total
        self.motor.limpiar_confirmado("tarea_actual")
        self.assertNotIn("tarea_actual", self.motor._obtener_confirmados_vigentes())

    def test_resumen_compacto_formato(self) -> None:
        self.motor.confirmar_contexto("cafe", "listo", origen="usuario", ttl_seg=3600)
        res = self.motor.resumen_compacto()

        self.assertIn("[DETECTADO]", res)
        self.assertIn("[PROBABLE]", res)
        self.assertIn("[CONFIRMADO]", res)
        self.assertIn("Code.exe", res)
        self.assertIn("programando", res)
        self.assertIn("cafe: 'listo'", res)

    def test_cache_anti_consultas_repetitivas(self) -> None:
        # Primera consulta
        self.motor.actualizar(forzar=True)
        self.assertEqual(self.mock_sensor.leer.call_count, 1)

        # Segunda consulta dentro de 1.0s sin forzar -> usa cache sin llamar al sensor
        self.motor.actualizar(forzar=False)
        self.assertEqual(self.mock_sensor.leer.call_count, 1)

        # Consulta forzada -> llama al sensor
        self.motor.actualizar(forzar=True)
        self.assertEqual(self.mock_sensor.leer.call_count, 2)

    def test_ciclo_de_vida_hilo_daemon(self) -> None:
        self.motor.iniciar(intervalo_seg=0.1)
        self.assertTrue(self.motor._hilo.is_alive())
        time.sleep(0.25)
        self.motor.detener(timeout=1.0)
        self.assertFalse(self.motor._hilo.is_alive())

    def test_concurrencia_multihilo_segura(self) -> None:
        errores: list[Exception] = []

        def worker_lectura():
            try:
                for _ in range(25):
                    self.motor.obtener_contexto()
                    self.motor.resumen_compacto()
                    time.sleep(0.005)
            except Exception as e:
                errores.append(e)

        def worker_escritura():
            try:
                for i in range(25):
                    self.motor.confirmar_contexto(f"clave_{i % 3}", i, ttl_seg=1.0)
                    if i % 5 == 0:
                        self.motor.limpiar_confirmado(f"clave_{i % 3}")
                    time.sleep(0.005)
            except Exception as e:
                errores.append(e)

        hilos = [
            threading.Thread(target=worker_lectura),
            threading.Thread(target=worker_lectura),
            threading.Thread(target=worker_escritura),
            threading.Thread(target=worker_escritura),
        ]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=3.0)

        self.assertEqual(len(errores), 0)

    def test_funciones_conveniencia_modulo(self) -> None:
        m = obtener_motor_contexto()
        self.assertIsInstance(m, MotorContexto)
        ctx = obtener_contexto_actual()
        self.assertIsInstance(ctx, dict)
        res = resumen_contexto_compacto()
        self.assertIsInstance(res, str)
        self.assertIn("[DETECTADO]", res)


if __name__ == "__main__":
    unittest.main()
