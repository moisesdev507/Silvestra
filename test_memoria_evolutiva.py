"""Pruebas unitarias para la suite de Memoria Evolutiva (Sueño, Progreso y Asociativa)."""
import json
import os
import sqlite3
import tempfile
import time
import unittest

import memoria_asociativa
import memoria_progreso
import memoria_sueno
import recordatorios


class TestMemoriaSueno(unittest.TestCase):
    """Verifica deduplicación y consolidación de recuerdos en SQLite temporal."""

    def setUp(self):
        self.tmp_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE recuerdos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contenido TEXT,
                categoria TEXT,
                estado TEXT DEFAULT 'activo',
                reemplaza_a_id INTEGER,
                creado_en TEXT
            )
        """)
        # Insertar recuerdos de prueba con duplicados intencionales
        cur.execute("INSERT INTO recuerdos (contenido, categoria, creado_en) VALUES (?, ?, ?)",
                    ("Moisés programa en Python y refactoriza módulos de Silvestra.", "general", "2026-11-20T10:00:00"))
        cur.execute("INSERT INTO recuerdos (contenido, categoria, creado_en) VALUES (?, ?, ?)",
                    ("Moisés programa en Python y refactoriza módulos de Silvestra en profundidad.", "general", "2026-11-21T11:00:00"))
        cur.execute("INSERT INTO recuerdos (contenido, categoria, creado_en) VALUES (?, ?, ?)",
                    ("Estudia lingüística y gramática española para la universidad.", "general", "2026-11-20T12:00:00"))
        cur.execute("INSERT INTO recuerdos (contenido, categoria, creado_en) VALUES (?, ?, ?)",
                    ("Estudia lingüística y gramática española para sus clases en la universidad.", "general", "2026-11-21T13:00:00"))
        con.commit()
        con.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_ejecutar_sueno_cognitivo_deduplica_y_resume(self):
        res = memoria_sueno.ejecutar_sueno_cognitivo(db_path=self.db_path, limite_lote=20)
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["duplicados_consolidados"], 1)

        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        consolidados = cur.execute("SELECT COUNT(*) FROM recuerdos WHERE estado = 'consolidado'").fetchone()[0]
        self.assertGreaterEqual(consolidados, 1)

        # Verificar creación de tabla y registros en memoria_resumenes
        resumenes = cur.execute("SELECT tema, sintesis FROM memoria_resumenes").fetchall()
        con.close()

        self.assertGreaterEqual(len(resumenes), 1)

    def test_detectar_orden_sueno(self):
        self.assertTrue(memoria_sueno.detectar_orden_sueno("consolida tu memoria"))
        self.assertTrue(memoria_sueno.detectar_orden_sueno("haz una limpieza de memoria"))
        self.assertTrue(memoria_sueno.detectar_orden_sueno("ejecuta sueño cognitivo"))
        self.assertFalse(memoria_sueno.detectar_orden_sueno("cuál es el clima hoy"))


class TestMemoriaProgreso(unittest.TestCase):
    """Verifica registro de avances y calibración socrática en SQLite temporal."""

    def setUp(self):
        self.tmp_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_registro_avance_y_calibracion_socrata(self):
        ok1 = memoria_progreso.registrar_avance_tecnico("Python", "Refactorización AST modular", "aplicado", db_path=self.db_path)
        ok2 = memoria_progreso.registrar_avance_tecnico("Python", "Generación de código dinámico", "aplicado", db_path=self.db_path)
        ok3 = memoria_progreso.registrar_avance_tecnico("FastAPI", "Rutas SSE y PWA", "practicado", db_path=self.db_path)

        self.assertTrue(ok1 and ok2 and ok3)

        resumen = memoria_progreso.resumen_nivel_programador(db_path=self.db_path)
        self.assertIsInstance(resumen, str)
        self.assertLessEqual(len(resumen), 160)
        self.assertIn("Python", resumen)

        reporte = memoria_progreso.consultar_mi_progreso(db_path=self.db_path)
        self.assertIn("Python", reporte)
        self.assertIn("Refactorización AST modular", reporte)

    def test_detectar_orden_progreso(self):
        self.assertTrue(memoria_progreso.detectar_orden_progreso("qué he aprendido"))
        self.assertTrue(memoria_progreso.detectar_orden_progreso("cómo voy mejorando como programador"))
        self.assertTrue(memoria_progreso.detectar_orden_progreso("cuál es mi progreso"))
        self.assertFalse(memoria_progreso.detectar_orden_progreso("revisa el archivo main.py"))


class TestMemoriaAsociativa(unittest.TestCase):
    """Verifica la consulta asociativa unificada cruzando múltiples fuentes."""

    def setUp(self):
        self.tmp_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.tmp_fd)
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE memoria_resumenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo TEXT,
                tema TEXT,
                sintesis TEXT,
                creado_ts REAL
            )
        """)
        cur.execute(
            "INSERT INTO memoria_resumenes (periodo, tema, sintesis, creado_ts) VALUES (?, ?, ?, ?)",
            ("2026-11-22", "programacion", "Dominio de refactorización modular y contratos de tamaño en Python.", 1000.0),
        )
        con.commit()
        con.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_buscar_contexto_asociativo_compacto(self):
        ctx = memoria_asociativa.buscar_contexto_asociativo("programacion modular en python", limite=2, db_path=self.db_path)
        self.assertIsInstance(ctx, str)
        if ctx:
            self.assertLessEqual(len(ctx), 600)
            self.assertIn("[MEMORIA ASOCIATIVA PROFUNDA]", ctx)
            self.assertIn("Síntesis:", ctx)


class TestProactividadYBlindajePostRespuesta(unittest.TestCase):
    """Verifica ausencia de AttributeError en proactividad y blindaje post-respuesta."""

    def test_motor_proactivo_evalua_sin_attribute_error_ultimo_sueno_ts(self):
        import cerebro_proactivo
        motor = cerebro_proactivo.MotorProactivo()
        self.assertTrue(hasattr(motor, "ultimo_sueno_ts"))
        self.assertEqual(motor.ultimo_sueno_ts, 0.0)
        # La evaluación no debe lanzar excepción
        try:
            res = motor.evaluar_oportunidad(app=None, forzar_cooldown=False)
        except AttributeError as e:
            self.fail(f"MotorProactivo lanzó AttributeError inesperado: {e}")

    def test_fallo_auxiliar_post_respuesta_no_rompe_flujo(self):
        import respuesta_flujo
        from unittest.mock import MagicMock, patch

        cerebro_mock = MagicMock()
        cerebro_mock.historial = []
        cerebro_mock.memoria = MagicMock()
        mock_al_frase = MagicMock()

        with patch("proveedores.completar_flujo", return_value="Todo en orden. [RECUERDO: prueba error]"):
            with patch("memoria_adaptadores.procesar_candidato", side_effect=RuntimeError("Fallo simulado en SQLite")):
                with patch("aprendizaje.registrar_interaccion", side_effect=ValueError("Fallo simulado en aprendizaje")):
                    resp, accion, emo = respuesta_flujo.responder_flujo(
                        cerebro_mock, "hola lyris", al_frase=mock_al_frase
                    )

        self.assertIn("Todo en orden", resp)
        self.assertEqual(emo, "neutral")
        self.assertGreaterEqual(len(cerebro_mock.historial), 1)


class TestRecordatoriosArranqueLimpio(unittest.TestCase):
    """Verifica que verificar_arranque marque como completados los recordatorios y no los repita."""

    def setUp(self):
        from unittest.mock import MagicMock
        self._orig_ruta = recordatorios.RUTA_JSON
        self.tmp_json = os.path.join(tempfile.gettempdir(), f"test_rec_arr_{os.getpid()}_{time.time()}.json")
        recordatorios.RUTA_JSON = self.tmp_json

    def tearDown(self):
        recordatorios.RUTA_JSON = self._orig_ruta
        if os.path.exists(self.tmp_json):
            try:
                os.remove(self.tmp_json)
            except Exception:
                pass

    def test_recordatorio_vencido_se_marca_completado_y_no_se_repite(self):
        from unittest.mock import MagicMock, patch
        ahora = time.time()
        rec_data = [
            {
                "id": 12345,
                "texto": "tomar agua de prueba",
                "timestamp": ahora - 600,
                "hora_exacta": "10:00 a. m.",
                "fecha": "2026-11-22",
                "completado": False,
            }
        ]
        with open(self.tmp_json, "w", encoding="utf-8") as f:
            json.dump(rec_data, f)

        app_mock = MagicMock()
        app_mock.cola = MagicMock()
        app_mock.memoria = MagicMock()
        app_mock.memoria.creador = "Moisés"

        with patch("threading.Thread"):
            rec_obj = recordatorios.Recordatorios(app_mock)

        app_mock.cola.put.assert_called()

        with open(self.tmp_json, "r", encoding="utf-8") as f:
            guardados = json.load(f)
        self.assertTrue(guardados[0]["completado"])

        # Segunda verificación (reinicio simulado): no debe volver a avisar
        app_mock.cola.reset_mock()
        rec_obj.verificar_arranque()
        app_mock.cola.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
