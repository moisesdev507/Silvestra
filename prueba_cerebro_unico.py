"""Pruebas de la Fase 1 del Cerebro Único (Live + Celeste)."""
import contextlib
import os
import sqlite3
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro_grafo
import cerebro_rag
import cerebro_unico
import estado
import herramientas_cerebro
import live_prompt
import memoria_persistente
import memoria_semantica
import memoria_unificada
import respuesta_flujo


def _tablas(ruta):
    with contextlib.closing(sqlite3.connect(ruta)) as con:
        return {fila[0] for fila in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}


class TestCerebroUnico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.rutas = {
            "grafo": os.path.join(self.tmp.name, "grafo.db"),
            "rag": os.path.join(self.tmp.name, "rag.db"),
            "vectores": os.path.join(self.tmp.name, "vectores.db"),
            "kaya": os.path.join(self.tmp.name, "kaya.db"),
            "estado": os.path.join(self.tmp.name, "estado.json"),
            "correcciones": os.path.join(self.tmp.name, "correcciones.json"),
        }
        self.parches = [
            patch.object(cerebro_grafo, "RUTA_DB", self.rutas["grafo"]),
            patch.object(cerebro_rag, "RUTA_DB", self.rutas["rag"]),
            patch.object(memoria_persistente, "RUTA_DB", self.rutas["vectores"]),
            patch.object(memoria_semantica, "RUTA_DB", self.rutas["kaya"]),
            patch.object(estado, "RUTA", self.rutas["estado"]),
        ]
        for parche in self.parches:
            parche.start()
        estado.guardar({})

    def tearDown(self):
        for parche in reversed(self.parches):
            parche.stop()
        self.tmp.cleanup()

    def test_a_arranque_crea_todas_las_tablas(self):
        with patch.object(memoria_unificada, "sincronizar_arranque", return_value={}):
            resultado = cerebro_unico.inicializar_cerebro()
        self.assertTrue(resultado["grafo"])
        self.assertTrue(resultado["rag"])
        self.assertTrue(resultado["vectores"])
        self.assertTrue(resultado["embeddings"])
        for tabla in ("grafo_nodos", "grafo_relaciones"):
            self.assertIn(tabla, _tablas(self.rutas["grafo"]))
        for tabla in ("rag_fragmentos", "rag_rutas"):
            self.assertIn(tabla, _tablas(self.rutas["rag"]))
        self.assertIn("memoria_vectores", _tablas(self.rutas["vectores"]))
        self.assertIn("kaya_embeddings", _tablas(self.rutas["kaya"]))

    def test_b_pipeline_turno_guarda_grafo_memoria_y_correccion(self):
        import correcciones
        import memoria_contexto

        memoria_contexto.instalar_espejo(None)
        memoria_contexto._TURNOS.clear()
        with patch.object(correcciones, "ARCHIVO_CORRECCIONES", self.rutas["correcciones"]):
            cerebro_unico.procesar_turno_cognitivo(
                "kaya", "Dije que te equivocaste con el café.")
            capturas = []

            def aprender(texto, canal="texto"):
                capturas.append((texto, canal))
                hilo = threading.Thread(target=lambda: None, daemon=True)
                hilo.start()
                return hilo

            with patch.object(memoria_unificada, "aprender_del_turno_async",
                              side_effect=aprender):
                resultado = cerebro_unico.procesar_turno_cognitivo(
                    "usuario", "No, eso no es así, mejor di hola. Me gusta el café.",
                    origen="live")
        self.assertTrue(resultado["correccion"])
        self.assertEqual(capturas[0][1], "voz")
        for hilo in resultado["hilos"].values():
            hilo.join(5)
        with open(self.rutas["correcciones"], "r", encoding="utf-8") as archivo:
            self.assertIn("mejor di hola", archivo.read())
        with contextlib.closing(sqlite3.connect(self.rutas["grafo"])) as con:
            filas = con.execute(
                "SELECT sujeto, relacion, objeto FROM grafo_relaciones").fetchall()
        self.assertTrue(any("café" in str(fila[2]) for fila in filas))
        with contextlib.closing(sqlite3.connect(self.rutas["kaya"])) as con:
            total = con.execute("SELECT COUNT(*) FROM kaya_embeddings").fetchone()[0]
        self.assertGreater(total, 0)

    def test_c_live_y_celeste_comparten_el_mismo_bloque(self):
        with patch.object(cerebro_unico, "compilar_contexto_unico",
                          return_value="BLOQUE COGNITIVO UNICO") as compilar:
            live = live_prompt.contexto_memoria()
            celeste = cerebro_unico.compilar_contexto_unico("hola")
        self.assertEqual(live, celeste)
        self.assertEqual(compilar.call_count, 2)
        cerebro = SimpleNamespace(historial=[], _podar_historial=lambda: None)
        with patch.object(cerebro_unico, "procesar_par_cognitivo") as procesar:
            respuesta_flujo._reg_turno(cerebro, "Hola", "Hola, ¿qué tal?")
        procesar.assert_called_once()
        with open("cerebro_prompt.py", "r", encoding="utf-8") as archivo:
            fuente = archivo.read()
        self.assertIn("compilar_contexto_unico", fuente)

    def test_d_herramientas_nuevas_se_ejecutan(self):
        rag = "[RAG]\n- El proyecto Aurora usa SQLite."
        relaciones = [{"sujeto": "Moisés", "relacion": "trabaja_en",
                       "objeto": "Aurora", "confianza": 1.0}]
        with patch.object(cerebro_rag, "indexar_ruta", return_value=(True, "ok")) as indexar, \
             patch.object(cerebro_rag, "consultar_rag", return_value=rag), \
             patch.object(cerebro_grafo, "consultar_relaciones", return_value=relaciones):
            texto = herramientas_cerebro.consultar_conocimiento_local(
                "Aurora", ruta="workspace_lyris")
        indexar.assert_called_once_with("workspace_lyris")
        self.assertIn("Aurora usa SQLite", texto)
        self.assertIn("trabaja_en: Aurora", texto)

        largo = "Contenido real de la página. " * 12
        with patch.object(herramientas_cerebro.resumen_web, "descargar_pagina",
                          return_value=("<html></html>", None)), \
             patch.object(herramientas_cerebro.resumen_web, "extraer_texto_html",
                          return_value=largo), \
             patch.object(herramientas_cerebro.resumen, "procesar_resumen_texto",
                          return_value="RESUMIDO") as procesar:
            resumen = herramientas_cerebro.resumir_enlace_o_video(
                "https://ejemplo.com/noticia")
        self.assertEqual(resumen, "RESUMIDO")
        procesar.assert_called_once()

        nombres = [d.name for d in herramientas_cerebro.declaraciones()]
        self.assertEqual(nombres, ["consultar_conocimiento_local", "resumir_enlace_o_video"])
        with patch.object(herramientas_cerebro, "consultar_conocimiento_local",
                          return_value="LOCAL") as consultar:
            self.assertEqual(herramientas_cerebro.despachar(
                "consultar_conocimiento_local", {"consulta": "Aurora"}), "LOCAL")
        consultar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
