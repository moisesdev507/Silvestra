"""Pruebas E2E aisladas para el cierre cognitivo de Fase 4."""
import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro
import memoria_adaptadores as adapt
import memoria_consolidacion as consol
import memoria_olvido as olvido
import memoria_razonamiento as razonar
import memoria_recuperacion as recuperar
from memoria import Memoria


class TestValidacionCognitivaEtapa8(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="e2e")
        self.store = self.mem.almacen
        self.gestor = self.mem.gestor

    def tearDown(self):
        self.mem.cerrar()

    def save(self, text, origin="explicito", confidence=.92, user="e2e"):
        return self.gestor.guardar(text, origen=origin, confianza=confidence, usuario_id=user)

    def test_01_entrada_y_decision_de_formacion(self):
        text = "Mi objetivo es aprender fotografía este año"
        r = adapt.procesar_candidato(self.mem, text, "Recuerda que " + text, "orden_explicita", explicito=True)
        self.assertTrue(r["aceptado"])
        self.assertEqual(r["recuerdo"].origen, "explicito")

    def test_02_persistencia_con_procedencia(self):
        r = self.save("Mi idioma preferido es francés")
        row = self.store.conexion.execute("SELECT usuario_id,origen,confianza FROM recuerdos WHERE id=?", (r["id"],)).fetchone()
        self.assertEqual(tuple(row), ("e2e", "explicito", .92))

    def test_03_recuperacion_relacionada_posterior(self):
        r = self.save("Mi proyecto Atlas utiliza Python")
        p = self.mem.recuperar("¿Qué utiliza Atlas?")
        self.assertIn(r["id"], [x["id"] for x in p["resultados"]])

    def test_04_conexion_en_grafo(self):
        r = self.save("Proyecto Atlas utiliza Python")
        from memoria_relaciones import extraer_desde_recuerdo
        extraer_desde_recuerdo(self.gestor.grafo, r["contenido"], "e2e", r["id"], "explicito", .92)
        p = self.mem.razonar("¿Qué utiliza Proyecto Atlas?")
        self.assertTrue(p["relaciones"]["relaciones_activas"])

    def test_05_consolida_compatibles_y_separa_valores_incompatibles(self):
        a = "Mi proyecto Atlas utiliza Python para crear asistentes personales con memoria local segura y modular que organizan tareas notas conversaciones y archivos diariamente desde mi computadora principal"
        b = a.replace("diariamente", "cotidianamente")
        c = a.replace("Python", "Rust")
        ra, rb, rc = self.save(a), self.save(b, "inferido", .55), self.save(c, "inferido", .55)
        plan = consol.analizar(self.store, "e2e")
        self.assertGreaterEqual(consol.similitud(a, c), .90)
        self.assertTrue(any({x[0], x[1]} == {ra["id"], rc["id"]} for x in plan["contradicciones"]))
        result = consol.consolidar(self.store, "e2e")
        self.assertTrue(result["consolidados"])
        self.assertEqual(self.store.contar_recuerdos(usuario_id="e2e"), 2)
        self.assertTrue(self.store.listar_linaje(result["consolidados"][0]["id"], "e2e"))

    def test_06_correccion_actualiza_historial_y_linaje(self):
        old = self.save("Mi color favorito es azul")
        new = self.gestor.reemplazar(old["id"], "Mi color favorito es verde", "e2e")
        self.assertEqual(new["reemplaza_a_id"], old["id"])
        self.assertTrue(self.store.listar_historial(old["id"], "e2e"))
        self.assertEqual(self.store.listar_linaje(new["id"], "e2e")[0]["origen_id"], old["id"])

    def test_07_contradiccion_y_estado_obsoleto(self):
        old = self.save("Vivo en David")
        self.gestor.reemplazar(old["id"], "Vivo en Santiago", "e2e")
        self.save("No vivo en Santiago", "inferido", .5)
        p = self.mem.razonar("¿Dónde vivo, Santiago?")
        self.assertTrue(p["contradicciones"])
        self.assertNotIn(old["id"], [x["id"] for x in p["evidencia"]])

    def test_08_recuperacion_y_razonamiento_integrados(self):
        r = self.save("Mi proyecto Atlas utiliza Python")
        p = self.gestor.razonar("¿Qué tecnología utiliza Atlas?", usuario_id="e2e")
        self.assertIn(r["id"], [x["id"] for x in p["evidencia"]])
        self.assertTrue(p["recuperacion"]["resultados"])

    def test_09_hechos_inferencias_e_hipotesis_separados(self):
        self.save("Mi idioma preferido es francés")
        self.save("Mi idioma preferido quizá sea italiano", "inferido", .55)
        p = self.mem.razonar("¿Qué idioma prefiero, francés o italiano?")
        self.assertTrue(p["conocida"] and p["inferencias"] and p["hipotesis"])
        self.assertTrue(all(x["confianza"] <= .65 for x in p["hipotesis"]))
        self.assertTrue(all(x["no_confirmada"] for x in p["hipotesis"]))
        self.assertEqual(len(p["alternativas"]), 2)
        self.assertTrue(all(x["recuerdo_ids"] for x in p["alternativas"]))

    def test_10_explicabilidad_ids_origen_fecha_confianza(self):
        r = self.save("Mi objetivo es estudiar astronomía")
        p = self.mem.razonar("¿Cuál es mi objetivo de estudio?")
        t = next(x for x in p["trazabilidad"] if x["id"] == r["id"])
        self.assertEqual(t["origen"], "explicito")
        self.assertTrue(t["fecha"])
        self.assertEqual(t["confianza"], .92)
        self.assertIn(r["id"], p["conclusiones"][0]["recuerdo_ids"])

    def test_11_abstencion_sin_respaldo(self):
        p = self.mem.razonar("¿Qué ocurrió con mi nave en Marte?")
        self.assertFalse(p["conclusiones"])
        self.assertTrue(p["desconocida"] and p["incertidumbre"])

    def test_12_contexto_vivo_separado_y_sensible_enmascarado(self):
        self.save("Mi editor histórico era Visual Studio Code")
        engine = {"detectado": {"ventana": {"ejecutable": "msedge.exe", "titulo": "password.txt"}}, "probable": {}}
        mm = {"ventana": {"ejecutable": "msedge.exe", "titulo": "password.txt"}, "audio": "aviso reciente"}
        p = self.mem.razonar("¿Qué aplicación tengo ahora?", contexto_engine=engine, multimodal=mm)
        self.assertEqual(p["contexto_actual"]["multimodal"]["ventana"], "msedge.exe")
        self.assertEqual(p["contexto_actual"]["multimodal"]["titulo"], "omitido por privacidad")
        self.assertIn("msedge.exe", p["contexto_actual"]["context_engine"]["ventana"])

    def test_13_no_promueve_inferencia_y_guest_no_filtra_memoria(self):
        self.save("Mi herramienta preferida es SQLite", "inferido", .55)
        before = self.store.conexion.total_changes
        self.mem.razonar("¿Qué herramienta prefiero?")
        self.assertEqual(self.store.conexion.total_changes, before)
        self.save("Mi lenguaje preferido es COBOL")
        bridge = SimpleNamespace(consultar_entorno_actual=lambda _q: {"ventana": {"ejecutable": "Code.exe", "titulo": "app.py"}})
        bot = cerebro.Cerebro(None, self.mem, SimpleNamespace(sistema_multimodal=bridge))
        engine = {"detectado": {"ventana": {"ejecutable": "Code.exe"}}, "probable": {}}
        out = []
        with patch("contexto_motor.obtener_motor_contexto", return_value=SimpleNamespace(obtener_contexto=lambda: engine)) as ctx, \
             patch("memoria_recuperacion.recuperar", wraps=recuperar.recuperar) as busca:
            worker = threading.Thread(target=lambda: out.append(bot.instrucciones("¿Qué ventana tengo abierta ahora?")))
            worker.start(); worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertIn("ESTADO ACTUAL EN VIVO DE WINDOWS", out[0])
        self.assertEqual(busca.call_count, 1)
        ctx.assert_called_once()
        bot.turno_invitado = True
        with patch("contexto_motor.obtener_motor_contexto", return_value=SimpleNamespace(obtener_contexto=lambda: engine)), \
             patch.object(self.mem, "razonar", wraps=self.mem.razonar) as call:
            guest = bot.instrucciones("¿Qué lenguaje prefiero en este momento?")
        self.assertNotIn("COBOL", guest)
        call.assert_not_called()

    def test_14_purga_total_aislada_y_privacidad(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Memoria(ruta_db=":memory:", ruta_json=os.path.join(tmp, "memoria.json"), usuario_id="perfil_a")
            try:
                old = m.gestor.guardar("Mi proyecto Atlas utiliza Python", usuario_id="perfil_a")
                new = m.gestor.reemplazar(old["id"], "Mi proyecto Atlas utiliza Rust", usuario_id="perfil_a")
                linked = m.gestor.guardar("El proyecto Boreal utiliza SQLite", usuario_id="perfil_a")
                m.gestor.actualizar(linked["id"], "perfil_a", confianza=.8)
                g = m.gestor.grafo
                x, y = g.crear_nodo("Boreal", "proyecto"), g.crear_nodo("SQLite", "tecnologia")
                edge = g.crear_relacion(x["id"], "utiliza", y["id"], "perfil_a", recuerdo_id=linked["id"])
                m.gestor.guardar("Perfil B conserva este dato", usuario_id="perfil_b")
                m.guardar()
                self.assertTrue(m.almacen.listar_historial(old["id"], "perfil_a"))
                self.assertTrue(m.almacen.eliminar_recuerdo(linked["id"], fisico=True, usuario_id="perfil_a"))
                rel = m.almacen.conexion.execute("SELECT estado,recuerdo_id FROM relaciones WHERE id=?", (edge["id"],)).fetchone()
                self.assertEqual(tuple(rel), ("obsoleto", None))
                self.assertFalse(m.almacen.listar_historial(linked["id"], "perfil_a"))
                self.assertFalse(m.almacen.buscar_texto("Boreal SQLite", usuario_id="perfil_a"))
                m.borrar()
                self.assertEqual(m.almacen.contar_recuerdos(solo_activos=False, usuario_id="perfil_a"), 0)
                self.assertEqual(m.almacen.contar_recuerdos(usuario_id="perfil_b"), 1)
                self.assertFalse(m.almacen.listar_historial(old["id"], "perfil_a"))
                self.assertFalse(os.path.exists(m.ruta_json))
                self.assertEqual(m.almacen.buscar_texto("Atlas", usuario_id="perfil_a"), [])
            finally:
                m.cerrar()

    def test_15_rollback_cancelacion_y_subsistemas_previos(self):
        r = self.save("Mi proyecto Atlas utiliza Python")
        event = threading.Event(); event.set()
        self.assertTrue(self.mem.razonar("Atlas", token_cancelacion=event)["cancelado"])
        with self.assertRaises(RuntimeError):
            with self.store.transaccion():
                self.store.eliminar_recuerdo(r["id"], fisico=True, usuario_id="e2e")
                raise RuntimeError("rollback")
        self.assertEqual(self.store.contar_recuerdos(usuario_id="e2e"), 1)
        self.assertTrue(self.mem.recuperar("Atlas")["resultados"])
        import ast
        for file in ("memoria_razonamiento.py", "memoria_razonamiento_grafo.py"):
            with open(file, encoding="utf-8") as source:
                tree = ast.parse(source.read())
            names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
            self.assertNotIn("acciones", names)
            self.assertNotIn("ejecucion_modelo", names)


if __name__ == "__main__":
    unittest.main()
