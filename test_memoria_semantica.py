"""Pruebas unitarias para memoria semántica por embeddings con Gemini y SQLite."""
import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import memoria_persistente
import memoria_semantica


class TestMemoriaSemantica(unittest.TestCase):
    """Test suite para memoria_semantica y su integración en memoria_persistente."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_memoria_jarvis.db")
        # Inicializar tablas cerrando la conexión de inmediato
        with memoria_persistente.closing(memoria_persistente._conectar(self.db_path)) as con:
            con.execute(memoria_semantica._DDL_VECTORES)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_similitud_coseno_exacta(self):
        """Verifica el cálculo matemático de similitud coseno."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        v4 = [-1.0, 0.0, 0.0]

        self.assertAlmostEqual(memoria_semantica._similitud_coseno(v1, v2), 1.0)
        self.assertAlmostEqual(memoria_semantica._similitud_coseno(v1, v3), 0.0)
        self.assertAlmostEqual(memoria_semantica._similitud_coseno(v1, v4), -1.0)
        self.assertEqual(memoria_semantica._similitud_coseno([], v1), 0.0)

    def test_empacar_y_desempacar_vector(self):
        """Verifica empaque y desempaque float32 en BLOB."""
        vec = [0.12345, -0.98765, 3.14159]
        blob = memoria_semantica._empacar_vector(vec)
        self.assertIsInstance(blob, bytes)
        recup = memoria_semantica._desempacar_vector(blob)
        self.assertEqual(len(recup), len(vec))
        for a, b in zip(vec, recup):
            self.assertAlmostEqual(a, b, places=5)

    def test_tolerancia_clave_vacia_o_timeout(self):
        """Sin clave o con timeout no genera excepciones y devuelve None/lista vacía."""
        with patch("config.CLAVE_GOOGLE", "", create=True):
            emb = memoria_semantica.obtener_embedding("hola")
            self.assertIsNone(emb)

        with patch("config.CLAVE_GOOGLE", "fake-key", create=True):
            with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
                emb_to = memoria_semantica.obtener_embedding("hola timeout")
                self.assertIsNone(emb_to)
                res_sem = memoria_semantica.buscar_semantico("consulta", ruta_db=self.db_path)
                self.assertEqual(res_sem, [])

    def test_fallback_segundo_modelo_embedding(self):
        """Si el primer modelo da 404, cae automáticamente al segundo modelo."""
        mock_vec_ok = [0.1] * 768
        mock_resp_data = {"embedding": {"values": mock_vec_ok}}
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_cm.__enter__.return_value = mock_cm

        intentos = []

        def side_effect(req, timeout=None):
            intentos.append(req.full_url)
            if "gemini-embedding-001" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO())
            return mock_cm

        with patch("config.CLAVE_GOOGLE", "fake-key", create=True):
            with patch("urllib.request.urlopen", side_effect=side_effect):
                res = memoria_semantica.obtener_embedding("prueba fallback modelo")
                self.assertIsNotNone(res)
                self.assertEqual(len(res), 768)
                self.assertTrue(len(intentos) >= 2)
                self.assertIn("text-embedding-004", intentos[1])

    def test_indexar_y_recuperacion_semantica_sin_palabras_exactas(self):
        """Recupera recuerdos por similitud semántica cuando las palabras no coinciden."""
        # Vectores sintéticos: concepto "mascota/perro" vs "computador/servidor"
        vec_perro = [0.9, 0.1, 0.0] + [0.0] * 765
        vec_canino = [0.85, 0.15, 0.0] + [0.0] * 765  # Muy cercano a perro
        vec_servidor = [0.0, 0.1, 0.9] + [0.0] * 765

        # Insertar recuerdo 1 en persistente
        r1 = memoria_persistente.guardar_recuerdo("general", "mascota_firulais", "El perro se llama Firulais", ruta_db=self.db_path)
        r2 = memoria_persistente.guardar_recuerdo("general", "servidor_prod", "El servidor de base de datos corre en puerto 5432", ruta_db=self.db_path)

        # Indexar manualmente vectores controlados
        with memoria_semantica.closing(memoria_semantica._conectar(self.db_path)) as con:
            con.execute(
                "INSERT INTO memoria_vectores(id_recuerdo, texto, vector, modelo, actualizado_en) VALUES (?, ?, ?, ?, ?)",
                (f"rec_{r1['id']}", r1["valor"], memoria_semantica._empacar_vector(vec_perro), "test", "2026-11-24"),
            )
            con.execute(
                "INSERT INTO memoria_vectores(id_recuerdo, texto, vector, modelo, actualizado_en) VALUES (?, ?, ?, ?, ?)",
                (f"rec_{r2['id']}", r2["valor"], memoria_semantica._empacar_vector(vec_servidor), "test", "2026-11-24"),
            )
            con.commit()

        # Consulta con palabras que NO están en r1: "animal canino doméstico"
        with patch.object(memoria_semantica, "obtener_embedding", return_value=vec_canino):
            sem_res = memoria_semantica.buscar_semantico("animal canino", limite=2, umbral=0.6, ruta_db=self.db_path)
            self.assertTrue(len(sem_res) > 0)
            self.assertEqual(sem_res[0][0], f"rec_{r1['id']}")
            self.assertIn("Firulais", sem_res[0][1])

            # Probar integración en buscar_recuerdos de memoria_persistente
            recuperados = memoria_persistente.buscar_recuerdos("animal canino", limite=5, ruta_db=self.db_path)
            self.assertTrue(any(r["id"] == r1["id"] for r in recuperados))

    def test_backfill_pendientes(self):
        """Indexa recuerdos que aún no tenían vector."""
        pares = [
            ("rec_1", "primer recuerdo"),
            ("rec_2", "segundo recuerdo"),
        ]
        mock_vec = [0.05] * 768
        with patch.object(memoria_semantica, "obtener_embedding", return_value=mock_vec):
            procesados = memoria_semantica.backfill_pendientes(pares, max_lote=10, ruta_db=self.db_path)
            self.assertEqual(procesados, 2)
            # Segunda llamada debe encontrar 0 pendientes
            self.assertEqual(memoria_semantica.backfill_pendientes(pares, max_lote=10, ruta_db=self.db_path), 0)


if __name__ == "__main__":
    unittest.main()
