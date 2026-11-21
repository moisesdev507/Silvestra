"""Pruebas aisladas de consolidación, actualización y olvido controlado."""
import threading
import unittest

import cerebro_prompt
import memoria_consolidacion as consolidacion
import memoria_olvido as olvido
import memoria_politicas as politicas
from memoria import Memoria


class TestConsolidacionEtapa6(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="etapa6")
        self.store = self.mem.almacen

    def tearDown(self):
        self.mem.cerrar()

    def guardar(self, texto, usuario="etapa6", **kw):
        return self.mem.gestor.guardar(texto, usuario_id=usuario, **kw)

    def duplicado_legacy(self, base):
        c = self.store.conexion
        c.execute("INSERT INTO recuerdos(usuario_id,tipo_memoria,contenido,contenido_norm,categoria,origen,confianza,estado,creado_en,actualizado_en,metadatos_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (base["usuario_id"], base["tipo_memoria"], base["contenido"], base["contenido_norm"],
             base["categoria"], base["origen"], base["confianza"], "activo", base["creado_en"],
             base["actualizado_en"], "{}"))
        self.store.conexion.commit()
        return c.execute("SELECT * FROM recuerdos ORDER BY id DESC LIMIT 1").fetchone()["id"]

    def test_01_consolida_compatibles_por_usuario(self):
        a = self.guardar("Mi proyecto personal Atlas usa Python para desarrollar herramientas útiles", origen="explicito")
        b = self.guardar("Mi proyecto Atlas usa Python para desarrollar herramientas útiles", origen="inferido")
        resultado = consolidacion.consolidar(self.store, "etapa6")
        self.assertTrue(resultado["consolidados"])
        self.assertEqual(self.store.contar_recuerdos(usuario_id="etapa6"), 1)
        consolidado = resultado["consolidados"][0]["id"]
        self.assertNotIn(consolidado, (a["id"], b["id"]))
        self.assertEqual({x["origen_id"] for x in self.store.listar_linaje(consolidado, "etapa6")}, {a["id"], b["id"]})

    def test_02_detecta_duplicados_exactos(self):
        uno = self.guardar("Prefiero café por la mañana", origen="inferido")
        dup = self.duplicado_legacy(uno)
        plan = consolidacion.analizar(self.store, "etapa6")
        self.assertEqual({x["id"] for x in plan["grupos"][0]}, {uno["id"], dup})

    def test_03_contradicciones_a_revision(self):
        self.guardar("Vivo en David", origen="inferido")
        self.guardar("No vivo en David", origen="inferido")
        plan = consolidacion.analizar(self.store, "etapa6")
        self.assertTrue(plan["contradicciones"])
        self.assertFalse(plan["grupos"])
        self.assertEqual(self.store.contar_recuerdos(usuario_id="etapa6"), 2)

    def test_04_actualiza_con_historial_y_reemplaza(self):
        old = self.guardar("Mi idioma preferido es francés", origen="explicito")
        new = self.mem.gestor.reemplazar(old["id"], "Mi idioma preferido es italiano", usuario_id="etapa6")
        self.assertEqual(new["reemplaza_a_id"], old["id"])
        self.assertEqual(self.store.listar_historial(old["id"], "etapa6")[0]["accion"], "reemplazo")
        self.assertEqual(self.store.listar_recuerdos(10, usuario_id="etapa6")[0]["id"], new["id"])

    def test_05_snapshots_y_linaje_conservan_fuentes(self):
        old = self.guardar("Mi meta es aprender fotografía", origen="explicito")
        new = self.mem.gestor.reemplazar(old["id"], "Mi meta es aprender pintura", usuario_id="etapa6")
        self.assertTrue(self.store.listar_historial(old["id"], "etapa6"))
        self.assertEqual(self.store.listar_linaje(new["id"], "etapa6")[0]["origen_id"], old["id"])

    def test_06_edad_no_borra_memoria_y_detecta_episodio(self):
        viejo = {"tipo_memoria": "semantica", "origen": "inferido", "confianza": .4,
            "creado_en": "2020-01-01T00:00:00+00:00", "metadatos": {}}
        self.assertEqual(politicas.evaluar_retencion(viejo)["decision"], "revisar")
        viejo["tipo_memoria"] = "episodica"
        self.assertEqual(politicas.evaluar_retencion(viejo)["decision"], "obsoleto")

    def test_07_olvido_explicito_sincroniza_fts_y_grafo(self):
        r = self.guardar("Mi proyecto Atlas utiliza Python", origen="inferido")
        g = self.mem.gestor.grafo
        a, b = g.crear_nodo("Atlas", "proyecto"), g.crear_nodo("Python", "tecnologia")
        g.crear_relacion(a["id"], "utiliza", b["id"], "etapa6", recuerdo_id=r["id"])
        self.assertEqual(olvido.olvidar(self.store, "proyecto Atlas", "etapa6", True), 1)
        self.assertEqual(self.store.buscar_texto("proyecto Atlas", usuario_id="etapa6"), [])
        edge = self.store.conexion.execute("SELECT estado,recuerdo_id FROM relaciones WHERE usuario_id='etapa6'").fetchone()
        self.assertEqual((edge["estado"], edge["recuerdo_id"]), ("obsoleto", None))

    def test_08_protege_recuerdos_importantes(self):
        rec = {"tipo_memoria": "semantica", "origen": "explicito", "confianza": .2,
            "creado_en": "2020-01-01T00:00:00+00:00", "metadatos": {}}
        self.assertEqual(politicas.evaluar_retencion(rec)["decision"], "conservar")

    def test_09_sin_relaciones_huerfanas_y_purga_privada(self):
        r = self.guardar("Prefiero jazz", origen="explicito")
        self.store.actualizar_recuerdo(r["id"], nuevo_contenido="Prefiero blues", usuario_id="etapa6")
        self.assertTrue(self.store.listar_historial(r["id"], "etapa6"))
        olvido.olvidar(self.store, "Prefiero blues", "etapa6", True)
        self.assertFalse(self.store.listar_historial(r["id"], "etapa6"))
        self.assertEqual(self.store.conexion.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_10_aislamiento_estricto_de_perfiles(self):
        ana = self.guardar("Mi proyecto Atlas usa Python", usuario="ana", origen="inferido")
        bob = self.guardar("Mi proyecto Atlas usa Python", usuario="bob", origen="inferido")
        consolidacion.consolidar(self.store, "ana")
        self.assertEqual(self.store.contar_recuerdos(usuario_id="bob"), 1)
        self.assertEqual(self.store.buscar_texto("Atlas", usuario_id="bob")[0]["id"], bob["id"])

    def test_11_cancelacion_revierte_grupo_atomico(self):
        rec = self.guardar("Mi proyecto Atlas usa Python", origen="inferido")
        self.duplicado_legacy(rec)
        class CancelarEnCommit:
            llamadas = 0
            def is_set(self):
                self.llamadas += 1
                return self.llamadas >= 3
        resultado = consolidacion.consolidar(self.store, "etapa6", CancelarEnCommit())
        self.assertTrue(resultado["cancelado"])
        self.assertEqual(self.store.contar_recuerdos(usuario_id="etapa6"), 2)

    def test_12_integracion_formacion_recuperacion_prompt_y_rollback(self):
        rec = self.guardar("Mi objetivo es estudiar astronomía", origen="explicito")
        prompt, total = cerebro_prompt.recuerdos_relevantes(self.mem, "astronomía")
        self.assertGreater(total, 0)
        self.assertIn("astronomía", prompt)
        with self.assertRaises(RuntimeError):
            with self.store.transaccion():
                self.mem.gestor.reemplazar(rec["id"], "Mi objetivo es estudiar geología", usuario_id="etapa6")
                raise RuntimeError("rollback solicitado")
        fila = self.store.conexion.execute("SELECT contenido,estado FROM recuerdos WHERE id=?", (rec["id"],)).fetchone()
        self.assertEqual((fila["contenido"], fila["estado"]), (rec["contenido"], "activo"))


if __name__ == "__main__":
    unittest.main()
