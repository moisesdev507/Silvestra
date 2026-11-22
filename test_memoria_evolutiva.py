"""Pruebas unitarias para la suite de Memoria Evolutiva (Sueño, Progreso y Asociativa)."""
import os
import sqlite3
import tempfile
import unittest

import memoria_asociativa
import memoria_progreso
import memoria_sueno


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


if __name__ == "__main__":
    unittest.main()
