"""Regresión: copiloto de desarrollo y motor agéntico de herramientas."""
import builtins
import os
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

import agente_herramientas as ag
import dev_copiloto as dev
import memoria_persistente as mp


class TestDevCopiloto(unittest.TestCase):
    def test_descubrir_proyectos_detecta_silvestra(self):
        proyectos = dev.descubrir_proyectos()
        nombres = [p["nombre"].lower() for p in proyectos]
        self.assertIn("proyecto_silvestra", nombres)
        silvestra = [p for p in proyectos
                     if p["nombre"].lower() == "proyecto_silvestra"][0]
        self.assertTrue(os.path.isdir(silvestra["ruta"]))
        self.assertTrue(silvestra["stack"])

    def test_estado_git_real(self):
        estado = dev.estado_git()
        self.assertEqual(estado["rama"], "master")
        self.assertIn("## master", estado["status"].lower())
        self.assertTrue(estado["log"])
        self.assertTrue(estado["ruta"].lower().endswith("proyecto_silvestra"))
        por_nombre = dev.estado_git("Proyecto_Silvestra")
        self.assertEqual(por_nombre["ruta"], estado["ruta"])

    def test_buscar_codigo_nunca_lee_config(self):
        real_open = builtins.open
        abiertos = []

        def open_vigilado(ruta, *args, **kwargs):
            if str(ruta).lower().replace("/", "\\").endswith("\\config.py"):
                raise AssertionError("buscar_codigo intentó leer config.py")
            abiertos.append(str(ruta))
            return real_open(ruta, *args, **kwargs)

        with patch("builtins.open", side_effect=open_vigilado):
            resultados = dev.buscar_codigo("def descubrir_proyectos")
        self.assertTrue(resultados)
        self.assertTrue(any("dev_copiloto.py" in r["archivo"] for r in resultados))
        self.assertFalse(any("config.py" in r["archivo"] for r in resultados))
        self.assertTrue(abiertos)

    def test_entorno_dev_y_telemetria(self):
        entorno = dev.estado_entorno_dev()
        self.assertIn("python.exe", entorno["procesos"])
        self.assertIsInstance(entorno["puertos"], list)
        telemetria = dev.telemetria_pc()
        self.assertIn("texto", telemetria)
        self.assertTrue(telemetria["texto"])


class TestAgenteHerramientas(unittest.TestCase):
    def test_catalogo_y_ejecucion(self):
        for nombre in ("estado_git", "descubrir_proyectos", "buscar_codigo",
                       "estado_entorno_dev", "abrir_en_vscode", "buscar_memoria",
                       "guardar_memoria", "telemetria_pc"):
            self.assertIn(nombre, ag.CATALOGO)
        self.assertIn("master", ag.ejecutar("estado_git"))
        self.assertIn("Herramienta desconocida", ag.ejecutar("no_existe"))

    def test_contexto_y_router_rapido(self):
        self.assertEqual(ag.contexto_para_cerebro("hola, ¿cómo estás?"), "")
        contexto = ag.contexto_para_cerebro("¿cuál es el estado de git del proyecto?")
        self.assertIn("[HERRAMIENTAS LOCALES]", contexto)
        self.assertIn("estado_git", contexto)
        self.assertLessEqual(len(contexto), ag.LIMITE)
        directo = ag.responder_directo("dime el estado de git")
        self.assertIsNotNone(directo)
        self.assertIn("master", directo)
        self.assertIsNone(ag.responder_directo("hola, ¿cómo estás?"))

    def test_bucle_agente_en_dos_rondas(self):
        respuestas = iter([
            "[[TOOL:buscar_memoria|Programación]] Ahora sí.",
            "Ya tengo los datos reales.",
        ])
        resultado = ag.ejecutar_bucle(
            "[[TOOL:estado_git|]]",
            respond_fn=lambda _datos: next(respuestas),
            max_rondas=2,
        )
        self.assertEqual(resultado["rondas"], 2)
        self.assertEqual(resultado["herramientas"], ["estado_git", "buscar_memoria"])
        self.assertEqual(len(resultado["datos"]), 2)
        self.assertNotIn("[[TOOL", resultado["respuesta"])
        self.assertIn("Ya tengo los datos reales", resultado["respuesta"])

    def test_post_llm_limpia_etiquetas(self):
        habladas = []
        limpio = ag.post_llm("[[TOOL:estado_git|]] Listo.",
                             "[[TOOL:estado_git|]] Listo.",
                             lambda frase: habladas.append(frase))
        self.assertNotIn("[[TOOL", limpio)
        self.assertIn("Listo.", limpio)
        self.assertTrue(habladas)

    def test_memoria_sqlite_se_preserva_tras_el_agente(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        ruta = os.path.join(temporal.name, "memoria_jarvis.db")
        with patch.object(mp, "RUTA_DB", ruta):
            mp.guardar_recuerdo("tarea", "entrega_prog",
                                "Entrega de Programación I mañana")
            salida = ag.ejecutar("buscar_memoria", "Programación")
            self.assertIn("Programación I", salida)
            with closing(mp._conectar()) as con:
                fila = con.execute(
                    "SELECT valor FROM recuerdos WHERE clave=?", ("entrega_prog",)
                ).fetchone()
            self.assertIsNotNone(fila)
            self.assertIn("Programación I", fila["valor"])
            bucle = ag.ejecutar_bucle("[[TOOL:buscar_memoria|Programación]]",
                                      respond_fn=None, max_rondas=2)
            self.assertEqual(bucle["herramientas"], ["buscar_memoria"])
            self.assertIn("Programación I", bucle["datos"][0]["resultado"])


if __name__ == "__main__":
    unittest.main()
