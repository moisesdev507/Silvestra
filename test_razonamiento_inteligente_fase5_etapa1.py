"""Validación aislada del razonamiento inteligente y su integración en Cerebro."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro
import memoria_recuperacion
from memoria import Memoria
from razonamiento_motor import razonar, formatear


class TestRazonamientoFase5Etapa1(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="razonamiento_test")

    def tearDown(self):
        self.mem.cerrar()

    def save(self, text, origin="explicito", confidence=.92):
        return self.mem.gestor.guardar(text, origen=origin, confianza=confidence,
                                       usuario_id="razonamiento_test")

    def test_01_clasificacion_y_objetivo(self):
        r = razonar("Por favor, explica este dato")
        self.assertEqual(r.problema.complejidad, "simple")
        self.assertIn("explica este dato", r.problema.objetivo)

    def test_02_complejo_restricciones_y_descomposicion(self):
        r = razonar("Compara la causa del error; luego revisa sin modificar los datos")
        self.assertEqual(r.problema.complejidad, "comparativo")
        self.assertTrue(r.subproblemas)
        self.assertTrue(r.problema.restricciones)

    def test_03_evaluacion_competitiva_trazable(self):
        row = self.save("El proyecto Atlas usa SQLite")
        bruto = {"evidencia": [{"id": row["id"], "contenido": row["contenido"],
            "origen": "explicito", "confianza": .92}],
            "alternativas": [{"opcion": "SQLite", "recuerdo_ids": [row["id"]], "confianza": .92},
                             {"opcion": "MongoDB", "recuerdo_ids": [999], "confianza": .4}]}
        r = razonar("Compara SQLite o MongoDB", resultado_memoria=bruto)
        self.assertEqual(len(r.alternativas), 2)
        self.assertIn(str(row["id"]), r.alternativas[0].evidencia_favor)
        self.assertIsNotNone(r.confianza_global)

    def test_04_contradicciones_impiden_conclusion(self):
        row = self.save("Vivo en David")
        bruto = {"evidencia": [{"id": row["id"], "contenido": row["contenido"], "origen": "explicito", "confianza": .95}],
                 "contradicciones": [{"ids": [row["id"], 44]}],
                 "conclusiones": [{"texto": "Vive en David", "recuerdo_ids": [row["id"]], "confianza": .95}]}
        r = razonar("¿Dónde vivo?", resultado_memoria=bruto)
        self.assertFalse(r.conclusiones)
        self.assertTrue(r.contradicciones)

    def test_05_separa_hechos_inferencias_contexto_y_grafo(self):
        bruto = {"contexto_actual": {"context_engine": {"ventana": "Code.exe", "titulo": "app.py"},
            "multimodal": {"audio": "alarma detectada"}},
            "evidencia": [{"id": 1, "contenido": "Prefiere Python", "origen": "explicito", "confianza": .9},
                          {"id": 2, "contenido": "Quizá estudie Rust", "origen": "inferido", "confianza": .5}],
            "relaciones": {"relaciones_activas": [{"id": 7, "tipo_relacion": "utiliza", "confianza": .7}]},
            "hipotesis": [{"descripcion": "Puede preferir Rust", "recuerdo_ids": [2], "confianza": .9}]}
        r = razonar("¿Qué sabes?", resultado_memoria=bruto)
        self.assertTrue(r.hechos and r.contexto_vivo and r.inferencias and r.hipotesis)
        self.assertLessEqual(r.hipotesis[0].confianza, .65)
        s = formatear(r)
        self.assertLess(s.index("ESTADO ACTUAL"), s.index("Hechos/recuerdos"))
        privado = razonar("¿Qué ventana?", multimodal={"ventana": {"ejecutable": "msedge.exe", "titulo": "password.txt"}})
        self.assertNotIn("password.txt", formatear(privado))

    def test_06_sin_respaldo_confianza_desconocida(self):
        r = razonar("¿Qué pasó ayer?", resultado_memoria={"evidencia": []})
        self.assertIsNone(r.confianza_global)
        self.assertTrue(r.informacion_faltante)
        self.assertFalse(r.conclusiones)

    def test_07_solo_lectura(self):
        self.save("Mi editor preferido es Vim")
        before = self.mem.almacen.conexion.total_changes
        r = self.mem.razonar("¿Qué editor prefiero?")
        intel = razonar("¿Qué editor prefiero?", resultado_memoria=r)
        self.assertTrue(intel.hechos)
        self.assertEqual(self.mem.almacen.conexion.total_changes, before)

    def test_08_cancelacion_cooperativa(self):
        token = threading.Event()
        token.set()
        r = razonar("Analiza esto", resultado_memoria={}, token_cancelacion=token)
        self.assertTrue(r.cancelado)
        self.assertEqual(formatear(r), "")

    def test_09_fallo_parcial_sin_inventar(self):
        fuente = SimpleNamespace(razonar=lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
        r = razonar("Resuelve este asunto", memoria=fuente)
        self.assertTrue(r.errores)
        self.assertFalse(r.hechos or r.conclusiones)
        self.assertTrue(r.informacion_faltante)

    def test_10_cerebro_usa_paquete_unico_y_prioriza_vivo(self):
        historico = self.save("El usuario programa en Visual Studio Code con aprendizaje.py")
        puente = SimpleNamespace(consultar_entorno_actual=lambda _: {"ventana": {"ejecutable": "Antigravity IDE.exe",
            "titulo": "memoria_filtro.py"}, "audio": ""})
        bot = cerebro.Cerebro(None, self.mem, SimpleNamespace(sistema_multimodal=puente))
        engine = {"detectado": {"ventana": {"ejecutable": "Antigravity IDE.exe", "titulo": "memoria_filtro.py"}}, "probable": {}}
        fila = {**historico, "tipo_memoria": "episodica", "estado": "activo", "metadatos": {}}
        paquete = {"resultados": [fila], "contradicciones": [], "relaciones": []}
        with patch("contexto_motor.obtener_motor_contexto", return_value=SimpleNamespace(obtener_contexto=lambda: engine)), \
             patch("memoria_recuperacion.recuperar", return_value=paquete) as recuperar:
            prompt = bot.instrucciones("¿Qué aplicación y archivo tengo abiertos ahora mismo?")
        self.assertIn("[ESTADO ACTUAL EN VIVO DE WINDOWS]", prompt)
        self.assertIn("Antigravity IDE.exe", prompt)
        self.assertIn("memoria_filtro.py", prompt)
        self.assertIn("Visual Studio Code", prompt)
        self.assertEqual(recuperar.call_count, 1)


if __name__ == "__main__":
    unittest.main()
