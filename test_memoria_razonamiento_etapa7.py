"""Validación del razonamiento cognitivo con SQLite aislada en memoria."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro
import memoria_razonamiento as razonamiento
import memoria_razonamiento_grafo as razon_grafo
from memoria import Memoria


class TestRazonamientoEtapa7(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="razon_test")
        self.gestor = self.mem.gestor
        self.grafo = self.gestor.grafo

    def tearDown(self):
        self.mem.cerrar()

    def guardar(self, texto, tipo="semantica", origen="explicito", confianza=.92):
        return self.gestor.guardar(texto, tipo_memoria=tipo, origen=origen,
                                   confianza=confianza, usuario_id="razon_test")

    def test_01_recupera_recuerdo_relevante(self):
        r = self.guardar("Mi proyecto Atlas utiliza Python")
        p = self.mem.razonar("¿Qué tecnología utiliza mi proyecto Atlas?")
        self.assertIn(r["id"], [x["id"] for x in p["evidencia"]])
        self.assertTrue(p["conclusiones"])

    def test_02_conecta_recuerdos_relacionados(self):
        r = self.guardar("Proyecto Atlas utiliza Python")
        a, b = self.grafo.crear_nodo("Proyecto Atlas", "proyecto"), self.grafo.crear_nodo("Python", "tecnologia")
        edge = self.grafo.crear_relacion(a["id"], "utiliza", b["id"], "razon_test", recuerdo_id=r["id"], confianza=.9)
        p = self.mem.razonar("¿Qué utiliza Proyecto Atlas?")
        self.assertIn(edge["id"], [x["id"] for x in p["relaciones"]["relaciones_activas"]])

    def test_03_combina_los_cuatro_tipos(self):
        self.guardar("Ayer terminé el proyecto Atlas", "episodica")
        self.guardar("Mi proyecto favorito es Atlas", "semantica")
        self.guardar("Procedimiento para desplegar Atlas: primero compilar", "procedimental")
        self.gestor.agregar_trabajo("tarea_atlas", "Hoy revisar Atlas", "razon_test")
        p = self.mem.razonar("¿Qué sabes de Atlas?")
        self.assertTrue({"episodica", "semantica", "procedimental", "trabajo"} <=
                        {x["tipo_memoria"] for x in p["evidencia"]})

    def test_04_expone_contradicciones(self):
        self.guardar("Vivo en David", origen="explicito")
        self.guardar("No vivo en David", origen="inferido", confianza=.55)
        p = self.mem.razonar("¿Dónde vivo, David?")
        self.assertTrue(p["contradicciones"])
        self.assertTrue(any("contradictorias" in x for x in p["incertidumbre"]))

    def test_05_separa_hechos_inferencias_e_hipotesis(self):
        self.guardar("Mi proyecto Atlas utiliza Python", origen="explicito")
        self.guardar("Quizá usaré SQLite en Atlas", origen="inferido", confianza=.5)
        p = self.mem.razonar("¿Qué tecnología uso en Atlas?")
        self.assertTrue(p["conocida"])
        self.assertTrue(p["inferencias"])
        self.assertTrue(all(x.get("no_confirmada") for x in p["inferencias"]))
        self.assertEqual(p["hipotesis"], [])

    def test_06_se_abstiene_sin_datos(self):
        p = self.mem.razonar("¿Qué ocurrió en Marte ayer?")
        self.assertFalse(p["conclusiones"])
        self.assertTrue(p["desconocida"])
        self.assertTrue(p["incertidumbre"])

    def test_07_temporalidad_historial_y_obsoleto(self):
        old = self.guardar("Mi idioma preferido es francés")
        new = self.gestor.reemplazar(old["id"], "Mi idioma preferido es italiano", "razon_test")
        p = self.mem.razonar("¿Qué idioma prefiero?")
        ids = [x["id"] for x in p["evidencia"]]
        self.assertIn(new["id"], ids)
        self.assertNotIn(old["id"], ids)
        self.assertEqual(next(x for x in p["trazabilidad"] if x["id"] == new["id"])["reemplaza_a_id"], old["id"])

    def test_08_grafo_directo_e_indirecto(self):
        a = self.grafo.crear_nodo("Proyecto Orion", "proyecto")
        b = self.grafo.crear_nodo("Python", "tecnologia")
        c = self.grafo.crear_nodo("SQLite", "tecnologia")
        e1 = self.grafo.crear_relacion(a["id"], "utiliza", b["id"], "razon_test", confianza=.9)
        e2 = self.grafo.crear_relacion(b["id"], "depende_de", c["id"], "razon_test", confianza=.8)
        p = self.mem.razonar("Proyecto Orion Python SQLite")
        ids = [r["id"] for r in p["relaciones"]["relaciones_activas"]]
        path_ids = [i for x in p["relaciones"]["conexiones"] for i in x["relacion_ids"]]
        self.assertTrue({e1["id"], e2["id"]} <= set(ids + path_ids))
        self.assertTrue(razon_grafo.analizar(self.grafo, "Orion", [], "razon_test")["conexiones"])

    def test_09_trazabilidad_de_conclusion(self):
        r = self.guardar("Mi objetivo es estudiar astronomía")
        p = self.mem.razonar("¿Cuál es mi objetivo de estudio?")
        c = p["conclusiones"][0]
        self.assertIn(r["id"], c["recuerdo_ids"])
        ref = next(x for x in p["trazabilidad"] if x["id"] == r["id"])
        self.assertEqual((ref["origen"], ref["tipo_memoria"]), ("explicito", "semantica"))
        self.assertTrue(ref["fecha"])
        self.assertIsNotNone(ref["confianza"])

    def test_10_integracion_con_cerebro(self):
        self.guardar("Mi proyecto Atlas utiliza Python")
        bot = cerebro.Cerebro(None, self.mem)
        ctx = {"detectado": {"ventana": {"ejecutable": "Code.exe"}}, "probable": {}}
        with patch("contexto_motor.obtener_motor_contexto", return_value=SimpleNamespace(obtener_contexto=lambda: ctx)):
            prompt = bot.instrucciones("¿Qué tecnología utiliza mi proyecto Atlas?")
        self.assertIn("RAZONAMIENTO DE MEMORIA", prompt)
        self.assertIn("Python", prompt)

    def test_11_context_engine_separa_actual_de_historico(self):
        ctx = {"detectado": {"ventana": {"ejecutable": "Code.exe", "titulo": "password.txt"}},
               "probable": {"actividad": {"valor": "programando"}}}
        p = self.mem.razonar("¿Qué estoy haciendo ahora?", contexto_engine=ctx)
        self.assertEqual(p["contexto_actual"]["fuente"], "en_vivo")
        self.assertEqual(p["contexto_actual"]["context_engine"]["ventana"], "Code.exe")
        self.assertEqual(p["contexto_actual"]["context_engine"]["titulo"], "omitido por privacidad")
        self.assertEqual(p["evidencia"], [])

    def test_12_contexto_multimodal_sin_fusionar_memoria(self):
        live = {"ventana": {"ejecutable": "msedge.exe", "titulo": "Docs"},
                "audio": "sonido de notificación", "situacion": "cambio de interfaz"}
        p = self.mem.razonar("¿Qué pasa en la pantalla?", multimodal=live)
        mm = p["contexto_actual"]["multimodal"]
        self.assertEqual(mm["ventana"], "msedge.exe")
        self.assertEqual(mm["audio"], "sonido de notificación")
        self.assertFalse(p["evidencia"])

    def test_13_persistencia_no_se_modifica(self):
        r = self.guardar("Proyecto Atlas utiliza Python")
        a, b = self.grafo.crear_nodo("Atlas", "proyecto"), self.grafo.crear_nodo("Python", "tecnologia")
        self.grafo.crear_relacion(a["id"], "utiliza", b["id"], "razon_test", recuerdo_id=r["id"])
        before = self.mem.almacen.conexion.total_changes
        self.mem.razonar("¿Qué utiliza Atlas?")
        self.assertEqual(self.mem.almacen.conexion.total_changes, before)

    def test_14_cancelacion_y_fallo_parcial(self):
        self.guardar("Mi proyecto Atlas utiliza Python")
        token = threading.Event(); token.set()
        self.assertTrue(self.mem.razonar("Atlas", token_cancelacion=token)["cancelado"])
        with patch("memoria_razonamiento_grafo.analizar", side_effect=RuntimeError("fallo")):
            p = self.mem.razonar("¿Qué utiliza Atlas?")
        self.assertTrue(p["evidencia"])
        self.assertTrue(any(x.startswith("grafo:") for x in p["errores"]))

    def test_15_regresion_y_comparacion_de_alternativas(self):
        self.guardar("Mi lenguaje preferido es Python")
        p = self.mem.razonar("¿Python o SQLite para mi proyecto?")
        self.assertGreaterEqual(len(p["alternativas"]), 2)
        self.assertTrue(self.mem.recuperar("Python")["resultados"])


if __name__ == "__main__":
    unittest.main()
