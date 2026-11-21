"""Pruebas del grafo de conocimiento usando exclusivamente SQLite en memoria."""
import sqlite3
import time
import unittest

import cerebro_prompt
import memoria_esquema
import memoria_relaciones
import memoria_recuperacion
from memoria import Memoria
from memoria_gestor import GestorMemoria


class TestRelacionesEtapa5(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="grafo_test")
        self.g = self.mem.gestor.grafo

    def tearDown(self):
        self.mem.cerrar()

    def nodo(self, nombre, tipo="concepto", usuario="grafo_test"):
        return self.g.crear_nodo(nombre, tipo, usuario)

    def test_01_nodos_normalizados(self):
        a = self.nodo("Café Atlas", "proyecto")
        b = self.nodo("cafe atlas", "concepto")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["usuario_id"], "grafo_test")

    def test_02_crear_y_consultar_relacion(self):
        a, b = self.nodo("Proyecto Atlas", "proyecto"), self.nodo("Python", "tecnologia")
        r = self.g.crear_relacion(a["id"], "utiliza", b["id"], "grafo_test",
            origen="explicita", confianza=.94)
        fila = self.g.listar_relaciones(a["id"], "grafo_test")
        self.assertEqual(fila[0]["id"], r["id"])
        self.assertEqual(fila[0]["nombre_destino"], "Python")

    def test_03_dirigidas_y_simetricas(self):
        a, b = self.nodo("A"), self.nodo("B")
        d = self.g.crear_relacion(a["id"], "depende_de", b["id"], "grafo_test", True)
        self.assertEqual(self.g.recorrer(b["id"], "grafo_test"), [])
        u = self.g.crear_relacion(b["id"], "esta_relacionado_con", a["id"], "grafo_test", False)
        self.assertLessEqual(u["origen_id"], u["destino_id"])
        self.assertTrue(self.g.recorrer(a["id"], "grafo_test"))
        self.assertEqual(d["dirigida"], 1)

    def test_04_bfs_ciclos_profundidad_y_limite(self):
        ns = [self.nodo("Nodo " + str(i)) for i in range(6)]
        for a, b in zip(ns, ns[1:]):
            self.g.crear_relacion(a["id"], "esta_relacionado_con", b["id"], "grafo_test", False)
        self.g.crear_relacion(ns[-1]["id"], "esta_relacionado_con", ns[0]["id"], "grafo_test", False)
        dos = self.g.recorrer(ns[0]["id"], "grafo_test", max_profundidad=2, max_resultados=20)
        tres = self.g.recorrer(ns[0]["id"], "grafo_test", max_profundidad=5, max_resultados=3)
        self.assertTrue(all(x["profundidad"] <= 2 for x in dos))
        self.assertLessEqual(len(tres), 3)
        self.assertEqual(len({x["nodo"]["id"] for x in tres}), len(tres))

    def test_05_deduplicacion_aristas(self):
        a, b = self.nodo("Proyecto Delta", "proyecto"), self.nodo("SQLite", "tecnologia")
        r1 = self.g.crear_relacion(a["id"], "utiliza", b["id"], "grafo_test", False)
        r2 = self.g.crear_relacion(b["id"], "utiliza", a["id"], "grafo_test", False)
        self.assertEqual(r1["id"], r2["id"])
        self.assertEqual(len(self.g.listar_relaciones(a["id"], "grafo_test")), 1)

    def test_06_contradicciones_conservan_fuentes(self):
        a, b = self.nodo("Evento Alfa", "acontecimiento"), self.nodo("Evento Beta", "acontecimiento")
        memoria_relaciones.registrar(self.g, "Evento Alfa", "ocurrio_antes_de", "Evento Beta",
            "grafo_test", explicit=True, confianza=.96)
        result = memoria_relaciones.registrar(self.g, "Evento Beta", "ocurrio_despues_de", "Evento Alfa",
            "grafo_test", explicit=False, confianza=.52)
        todas = self.g.listar_relaciones(a["id"], "grafo_test", estado=None)
        self.assertEqual(len(todas), 2)
        self.assertTrue(all(r["estado"] == "contradicho" for r in todas))
        self.assertEqual({r["origen"] for r in todas}, {"explicita", "inferida"})
        self.assertTrue(result["contradicciones"])

    def test_07_extraccion_conservadora_y_procedencia(self):
        rec = self.mem.gestor.guardar("Proyecto Atlas utiliza Python", usuario_id="grafo_test",
            origen="explicito", confianza=.92)
        found = memoria_relaciones.extraer_desde_recuerdo(self.g, rec["contenido"], "grafo_test",
            rec["id"], "explicito", .92)
        self.assertEqual(len(found), 1)
        rel = found[0]["relacion"]
        self.assertEqual((rel["origen"], rel["recuerdo_id"], rel["confianza"]), ("explicita", rec["id"], .92))
        none = memoria_relaciones.extraer_desde_recuerdo(self.g, "Quizá Atlas conozca Python", "grafo_test")
        self.assertEqual(none, [])

    def test_08_actualizacion_eliminacion_y_huerfanos(self):
        rec = self.mem.gestor.guardar("Proyecto Orion utiliza Python", usuario_id="grafo_test")
        a, b = self.nodo("Proyecto Orion", "proyecto"), self.nodo("Python", "tecnologia")
        r = self.g.crear_relacion(a["id"], "utiliza", b["id"], "grafo_test", recuerdo_id=rec["id"])
        upd = self.g.actualizar_relacion(r["id"], "grafo_test", confianza=.8)
        self.assertEqual(upd["confianza"], .8)
        self.mem.gestor.eliminar(rec["id"], usuario_id="grafo_test")
        self.assertEqual(self.g.listar_relaciones(a["id"], "grafo_test"), [])
        self.assertEqual(self.g.listar_relaciones(a["id"], "grafo_test", estado=None)[0]["estado"], "obsoleto")
        self.assertTrue(self.g.eliminar_relacion(r["id"], "grafo_test"))

    def test_09_aislamiento_perfiles(self):
        a, b = self.nodo("Proyecto privado", "proyecto", "grafo_test"), self.nodo("Python", "tecnologia", "grafo_test")
        self.g.crear_relacion(a["id"], "utiliza", b["id"], "grafo_test")
        otro = GestorMemoria(self.mem.almacen, "otro_perfil").grafo
        self.assertIsNone(otro.obtener_nodo(a["id"], "otro_perfil"))
        self.assertEqual(otro.listar_relaciones(usuario_id="otro_perfil"), [])
        with self.assertRaises(KeyError):
            otro.crear_relacion(a["id"], "utiliza", b["id"], "otro_perfil")

    def test_10_integracion_formacion_recuperacion_prompt(self):
        self.assertTrue(self.mem.recordar("Proyecto Atlas utiliza Python",
            texto_usuario="Recuerda que Proyecto Atlas utiliza Python"))
        pkg = self.mem.recuperar("¿Qué usa Proyecto Atlas?", limite=3)
        self.assertTrue(pkg["resultados"])
        self.assertTrue(pkg["relaciones"])
        self.assertTrue(self.mem.consultar_relacional("Proyecto Atlas Python")["relaciones"])
        prompt = cerebro_prompt.construir_prompt(self.mem, "Proyecto Atlas Python",
            contexto_adicional="[ESTADO ACTUAL EN VIVO DE WINDOWS] Editor abierto")
        self.assertIn("Relaciones de alta confianza", prompt)
        self.assertLess(prompt.index("RECUERDOS HISTÓRICOS"), prompt.rindex("[ESTADO ACTUAL EN VIVO DE WINDOWS]"))

    def test_11_rendimiento_y_limites(self):
        nodos = [self.nodo("Rendimiento " + str(i)) for i in range(40)]
        for a, b in zip(nodos, nodos[1:]):
            self.g.crear_relacion(a["id"], "esta_relacionado_con", b["id"], "grafo_test", False)
        t = time.perf_counter()
        salida = self.g.recorrer(nodos[0]["id"], "grafo_test", max_profundidad=5, max_resultados=12)
        ms = (time.perf_counter()-t)*1000
        self.assertLessEqual(len(salida), 12)
        self.assertTrue(all(x["profundidad"] <= 5 for x in salida))
        self.assertLess(ms, 1000)

    def test_12_migracion_esquema_previo(self):
        c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE entidades(id INTEGER PRIMARY KEY,nombre TEXT NOT NULL,nombre_norm TEXT NOT NULL,tipo TEXT,creado_en TEXT NOT NULL)")
        c.execute("CREATE TABLE relaciones(id INTEGER PRIMARY KEY,origen_id INTEGER NOT NULL REFERENCES entidades(id),tipo_relacion TEXT NOT NULL,destino_id INTEGER NOT NULL REFERENCES entidades(id),peso REAL NOT NULL DEFAULT 1,origen_dato TEXT,creado_en TEXT NOT NULL)")
        c.execute("INSERT INTO entidades VALUES(1,'Café','café','concepto','2020')")
        c.execute("INSERT INTO entidades VALUES(2,'Cafe','cafe','concepto','2021')")
        c.execute("INSERT INTO entidades VALUES(3,'Python','tecnologia','tecnologia','2022')")
        c.execute("INSERT INTO relaciones VALUES(1,2,'utiliza',3,.8,'legacy','2022')"); c.commit()
        memoria_esquema.inicializar(c, ":memory:")
        memoria_esquema.inicializar(c, ":memory:")
        self.assertIn("usuario_id", {x[1] for x in c.execute("pragma table_info(relaciones)")})
        self.assertEqual(c.execute("select count(*) from entidades").fetchone()[0], 2)
        edge = c.execute("select usuario_id,origen_id,destino_id,origen,confianza from relaciones").fetchone()
        self.assertEqual((edge[0], edge[1], edge[2], edge[3]), ("local", 1, 3, "inferida"))
        self.assertAlmostEqual(edge[4], .8)
        self.assertEqual(c.execute("select count(*) from relaciones").fetchone()[0], 1)
        c.close()


if __name__ == "__main__":
    unittest.main()
