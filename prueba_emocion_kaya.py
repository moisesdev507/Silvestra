"""Motor emocional persistente, bromas internas y personalidad compartida."""
import asyncio
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import MagicMock, patch

import estado
import estado_emocional_kaya as ee
import live_herramientas
import live_herramientas_extra
import live_motor
import live_orquestador
import memoria
import memoria_contexto


class TestEmocionKaya(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_db = os.path.join(self.tmp.name, "datos", "silvestra_memoria.db")
        self.ahora = 1_000_000.0
        self.parches = [
            patch.object(ee, "RUTA_DB", self.ruta_db),
            patch.object(ee, "_ahora", side_effect=lambda: self.ahora),
            patch.object(estado, "RUTA", os.path.join(self.tmp.name, "estado.json")),
        ]
        for parche in self.parches:
            parche.start()
        self.instancia_original = memoria._memoria_instancia
        self.mem = memoria.Memoria(
            ruta_db=os.path.join(self.tmp.name, "memoria.db"),
            ruta_json=os.path.join(self.tmp.name, "memoria.json"),
            usuario_id="prueba_emocion",
        )
        memoria_contexto.resetear_sesion()

    def tearDown(self):
        self.mem.cerrar()
        memoria._memoria_instancia = self.instancia_original
        for parche in reversed(self.parches):
            parche.stop()
        self.tmp.cleanup()

    def test_persistencia_sqlite_y_directriz_breve(self):
        resultado = ee.registrar_evento_emocional("charla_fluida", "ana")
        self.assertAlmostEqual(resultado["energia"], 0.83)
        self.assertAlmostEqual(resultado["complicidad"], 0.60)
        self.assertAlmostEqual(resultado["fastidio"], 0.0)
        with closing(sqlite3.connect(self.ruta_db)) as con:
            fila = con.execute(
                "SELECT energia, curiosidad, complicidad, fastidio, "
                "ultima_interaccion_ts, interrupciones_seguidas "
                "FROM kaya_estado_emocional WHERE usuario_id=?", ("ana",)
            ).fetchone()
        self.assertIsNotNone(fila)
        self.assertAlmostEqual(fila[0], 0.83)
        self.assertAlmostEqual(fila[3], 0.0)
        self.assertEqual(ee.obtener_estado("ana")["interrupciones_seguidas"], 0)
        directriz = ee.resumen_estado_emocional("ana")
        self.assertTrue(directriz.startswith("Ánimo:"))
        self.assertLessEqual(len(directriz), 160)

    def test_abandono_solo_tras_dos_horas(self):
        ee.registrar_evento_emocional("charla_fluida", "ana")
        base = ee.obtener_estado("ana")
        self.ahora += 3 * 3600
        tras = ee.registrar_evento_emocional("despertar_tras_abandono", "ana")
        self.assertGreater(tras["curiosidad"], base["curiosidad"])
        self.assertGreater(tras["fastidio"], base["fastidio"])
        self.assertIn("curiosa", ee.resumen_estado_emocional("ana"))
        curiosidad = tras["curiosidad"]
        self.ahora += 60
        reciente = ee.registrar_evento_emocional("despertar_tras_abandono", "ana")
        self.assertAlmostEqual(reciente["curiosidad"], curiosidad)

    def test_interrupciones_charla_y_reposo(self):
        for _ in range(2):
            ee.registrar_evento_emocional("interrupcion_barge_in", "ana")
        estado_dos = ee.obtener_estado("ana")
        self.assertEqual(estado_dos["interrupciones_seguidas"], 2)
        self.assertAlmostEqual(estado_dos["fastidio"], 0.10)

        for _ in range(12):
            ee.registrar_evento_emocional("interrupcion_barge_in", "ana")
        estado_picada = ee.obtener_estado("ana")
        self.assertEqual(estado_picada["interrupciones_seguidas"], 14)
        self.assertLessEqual(estado_picada["fastidio"], 0.75)
        self.assertLess(estado_picada["energia"], 0.75)
        self.assertIn("picada", ee.resumen_estado_emocional("ana"))

        ee.registrar_evento_emocional("charla_fluida", "ana")
        tras_charla = ee.obtener_estado("ana")
        self.assertEqual(tras_charla["interrupciones_seguidas"], 0)
        self.assertLess(tras_charla["fastidio"], estado_picada["fastidio"])

        ee.registrar_evento_emocional("reposo_prolongado", "ana")
        tras_reposo = ee.obtener_estado("ana")
        self.assertGreater(tras_reposo["energia"], tras_charla["energia"])
        self.assertGreaterEqual(tras_reposo["fastidio"], 0.10)

    def test_herramienta_guardar_broma_interna(self):
        nombres = [f.name for f in
                   live_herramientas.declarar_declaraciones_herramientas()[0].function_declarations]
        self.assertIn("guardar_broma_interna", nombres)

        respuesta = live_herramientas_extra.guardar_broma_interna(
            "Nos decimos tortuga veloz cuando algo va lento", "pruebas")
        self.assertIn("guardé", respuesta.lower())
        self.assertTrue(any("[BROMA_INTERNA]" in h for h in self.mem.hechos))

        respuesta2 = asyncio.run(live_herramientas.despachar_herramienta_asincrona(
            "guardar_broma_interna",
            {"broma": "El café es combustible de programador", "contexto": "madrugadas"},
        ))
        self.assertIn("guardé", respuesta2.lower())
        self.assertGreaterEqual(
            sum("[BROMA_INTERNA]" in h for h in self.mem.hechos), 2)

    def test_inyeccion_en_memoria_contexto(self):
        self.assertTrue(self.mem.recordar(
            "A Ana le gusta la comida italiana", origen="explicito", fuente="orden_explicita"))
        live_herramientas_extra.guardar_broma_interna(
            "Nos decimos tortuga veloz cuando algo va lento", "pruebas")
        ee.registrar_evento_emocional("charla_fluida", self.mem.usuario_id)
        memoria_contexto.resetear_sesion()

        bloque = memoria_contexto.resumen_para_prompt(self.mem)
        for esperado in ("Ánimo:", "Broma:", "Hecho:", "tortuga veloz"):
            self.assertIn(esperado, bloque)
        self.assertNotIn("[BROMA_INTERNA]", bloque)
        self.assertLessEqual(len(bloque), 450)

        segundo = memoria_contexto.resumen_para_prompt(self.mem)
        self.assertNotIn("Hecho:", segundo)
        self.assertIn("Broma:", segundo)
        self.assertLessEqual(len(segundo), 450)

    def test_despertar_live_registra_evento_real(self):
        with patch.object(ee, "registrar_si_disponible") as registrar:
            app = MagicMock()
            coordinador = live_orquestador.CoordinadorLiveSilvestra(app)
            coordinador.modo_live_habilitado = True
            with patch.object(live_motor.SesionKayaLive, "iniciar", return_value=True):
                self.assertTrue(coordinador.intentar_activar_live("hola"))
            registrar.assert_any_call("despertar_tras_abandono")


if __name__ == "__main__":
    unittest.main()
