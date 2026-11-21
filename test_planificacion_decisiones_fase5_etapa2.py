"""Pruebas aisladas del planificador, permisos y persistencia multiusuario."""
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import planificador_modelo as pm
import planificacion_adaptativa as adapt
from cerebro import Cerebro
from ejecucion_modelo import ContratoHerramienta
from ejecucion_registro import RegistroHerramientas, SistemaEjecucion
from memoria import Memoria
from permisos_modelo import PoliticaOperacion, NIVEL_REQUIERE_CONFIRMACION
from permisos_motor import MotorPermisos
from planificacion_motor import PlanificacionMotor, es_solicitud_explicita
from planificacion_modelos import DecisionPlan


def respuesta_plan():
    return json.dumps({"titulo": "Proyecto incremental", "requisitos": ["entrega verificable"],
        "restricciones": ["sin ejecuciones automáticas"], "preguntas_pendientes": [],
        "fases": [{"id_fase": "f1", "orden": 1, "nombre": "Preparación", "tareas": [
            {"id_tarea": "t1", "titulo": "Definir alcance", "descripcion": "Acordar resultado",
             "importancia": 5, "urgencia": 4, "complejidad": "baja", "dependencias": []},
            {"id_tarea": "t2", "titulo": "Validar entrega", "descripcion": "Revisar evidencia",
             "importancia": 4, "urgencia": 3, "complejidad": "media", "dependencias": ["t1"]}]}]})


class CerebroFalso:
    def __init__(self):
        self.calls = 0

    def _pedir(self, mensajes, tarea="fondo"):
        self.calls += 1
        return respuesta_plan()


class TestPlanificacionFase5Etapa2(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="plan_a")
        self.motor = PlanificacionMotor(self.mem.almacen, "plan_a")
        self.brain = CerebroFalso()

    def tearDown(self):
        self.mem.cerrar()

    def crear(self, objetivo="Planifica entrega modular", razonamiento=None, alternativas=None):
        return self.motor.crear_plan(objetivo, razonamiento, cerebro=self.brain,
                                    alternativas=alternativas)

    def test_01_crea_plan_desde_objetivo(self):
        r = self.crear()
        self.assertTrue(r["plan"].id_plan)
        self.assertEqual(r["analisis"].objetivo.principal, "Planifica entrega modular")

    def test_02_descompone_objetivo_y_criterios(self):
        r = self.crear()
        self.assertEqual(len(r["plan"].todas_las_tareas()), 2)
        self.assertEqual(len(r["analisis"].criterios_exito), 2)

    def test_03_dependencias_y_ciclos(self):
        p = self.crear()["plan"]
        self.assertTrue(pm.validar_dependencias(p)[0])
        a, b = p.mapa_tareas()["t1"], p.mapa_tareas()["t2"]
        a.dependencias = ["t2"]
        self.assertFalse(pm.validar_dependencias(p)[0])
        a.dependencias = []

    def test_04_prioriza_tarea_accionable(self):
        p = self.crear()["plan"]
        accionables = pm.obtener_tareas_accionables(p)
        self.assertEqual([t.id_tarea for t in accionables], ["t1"])
        p.mapa_tareas()["t1"].estado = pm.ESTADO_COMPLETADA
        self.assertEqual([t.id_tarea for t in pm.obtener_tareas_accionables(p)], ["t2"])

    def test_05_compara_alternativas(self):
        alts = [{"id": "segura", "titulo": "Por hitos", "beneficio": .85, "riesgo": .1,
                 "costo": 2, "ventajas": ["reversible"], "desventajas": ["toma etapas"]},
                {"id": "rapida", "titulo": "Entrega única", "beneficio": .7, "riesgo": .8, "costo": 1}]
        a = self.crear(alternativas=alts)["analisis"]
        self.assertEqual(a.decision.alternativa_id, "segura")
        self.assertTrue(a.alternativas[0].ventajas and a.alternativas[0].desventajas)

    def test_06_evalua_riesgos_y_prevencion(self):
        a = self.crear("Planifica publicar y enviar el informe con credenciales") ["analisis"]
        self.assertGreaterEqual(len(a.riesgos), 2)
        self.assertTrue(all(r.medida_preventiva for r in a.riesgos))

    def test_07_informacion_insuficiente_queda_explicita(self):
        r = self.crear("Planifica un sistema", razonamiento={"informacion_faltante": ["Falta el plazo."]})
        self.assertTrue(r["analisis"].objetivo.informacion_faltante)
        self.assertEqual(r["analisis"].decision.aprobacion_usuario, "pendiente")

    def test_08_fallo_bloquea_dependientes(self):
        p = self.crear()["plan"]
        impactadas = adapt.actualizar_estado(p, "t1", pm.ESTADO_FALLIDA, "proveedor no disponible")
        self.assertEqual(p.mapa_tareas()["t1"].estado, pm.ESTADO_FALLIDA)
        self.assertIn("t2", impactadas)
        self.assertEqual(p.mapa_tareas()["t2"].estado, pm.ESTADO_BLOQUEADA)

    def test_09_replanifica_contexto_preservando_completadas(self):
        creado = self.crear()
        p = creado["plan"]
        p.mapa_tareas()["t1"].estado = pm.ESTADO_COMPLETADA
        self.motor.planificador.guardar()
        nueva = pm.PlanObjetivo("nuevo", "nuevo", "nuevo", fases=[pm.Fase("f1", 1, "Prep", tareas=[
            pm.Tarea("t1", "No reemplazar", fase_id="f1"),
            pm.Tarea("t2", "Ajustar siguiente", fase_id="f1", urgencia=5),
            pm.Tarea("t3", "Tarea nueva", fase_id="f1", dependencias=["t1"])])])
        cambio = self.motor.replanificar_contexto(p.id_plan, nueva,
            {"detectado": {"ventana": {"ejecutable": "Code.exe"}}, "probable": {}, "confirmado": {}})
        self.assertTrue(cambio["actualizado"])
        p = self.motor.obtener(p.id_plan)[0]
        self.assertEqual(p.mapa_tareas()["t1"].estado, pm.ESTADO_COMPLETADA)
        self.assertEqual(p.mapa_tareas()["t2"].urgencia, 5)
        self.assertIn("t3", p.mapa_tareas())

    def test_10_progreso_criterios_y_retraso(self):
        r = self.crear()
        c = r["analisis"].criterios_exito[0]
        self.assertFalse(adapt.verificar_criterio(c, c.evidencia_requerida))
        self.assertTrue(adapt.verificar_criterio(c, c.evidencia_requerida, True))
        self.assertEqual(adapt.progreso(r["plan"])["porcentaje"], 0.0)
        self.assertTrue(adapt.detectar_retraso(r["plan"], 1, 2))

    def test_11_prepara_solicitud_para_sistema_ejecucion(self):
        r = self.crear()
        sol = self.motor.preparar_ejecucion(r["plan"].id_plan, "t1", "operacion_demo", {"x": 1})
        self.assertEqual((sol.origen, sol.id_plan, sol.id_tarea), ("planificador", r["plan"].id_plan, "t1"))

    def test_12_permisos_requieren_confirmacion_de_usuario(self):
        with self.assertRaises(ValueError):
            DecisionPlan("x", "", autorizacion_ejecucion="autorizada")
        r = self.crear()
        sol = self.motor.preparar_ejecucion(r["plan"].id_plan, "t1", "operacion_demo")
        permisos = MotorPermisos()
        permisos.registrar_politica(PoliticaOperacion("operacion_demo", NIVEL_REQUIERE_CONFIRMACION,
            riesgo_maximo_permitido="alto"), actor="sistema_inicio")
        llamadas = []
        registro = RegistroHerramientas()
        registro.registrar(ContratoHerramienta("operacion_demo", "demo", "prueba",
            handler=lambda p: llamadas.append(p), nivel_riesgo="medio", requiere_confirmacion=True))
        sistema = SistemaEjecucion(registro, motor_permisos=permisos)
        pendiente = sistema.procesar(sol)
        self.assertEqual(pendiente.estado, "pendiente_autorizacion")
        self.assertFalse(llamadas)
        auth = pendiente.metadatos["id_autorizacion"]
        self.assertFalse(self.motor.aprobar_recomendacion(sol.id_plan, actor="planificador"))
        self.assertTrue(self.motor.aprobar_recomendacion(sol.id_plan, actor="usuario"))
        self.assertEqual(self.motor.planificador._analisis[sol.id_plan]["decision"]["autorizacion_ejecucion"], "no_solicitada")
        self.assertFalse(permisos.confirmar_autorizacion(auth, actor="planificador")["aprobada"])
        self.assertEqual(self.motor.planificador._analisis[sol.id_plan]["decision"]["autorizacion_ejecucion"], "no_solicitada")
        self.assertTrue(permisos.confirmar_autorizacion(auth, actor="usuario")["aprobada"])
        final = sistema.procesar(sol)
        self.assertEqual(final.estado, "completada")
        self.assertTrue(llamadas)

    def test_13_persistencia_sqlite_aislada_por_usuario(self):
        a = self.crear()
        motor_b = PlanificacionMotor(self.mem.almacen, "plan_b")
        p_b = motor_b.crear_plan("Planifica otra cosa", cerebro=self.brain)["plan"]
        recargado = PlanificacionMotor(self.mem.almacen, "plan_a")
        self.assertIsNotNone(recargado.obtener(a["plan"].id_plan)[0])
        self.assertIsNone(recargado.obtener(p_b.id_plan)[0])
        self.assertEqual(len(recargado.repo.listar("plan_a")), 1)
        self.assertEqual(len(recargado.repo.listar("plan_b")), 1)

    def test_14_cerebro_solo_planifica_solicitud_explicita(self):
        self.assertTrue(es_solicitud_explicita("Planifica una entrega segura"))
        self.assertFalse(es_solicitud_explicita("¿Qué es la planificación?"))
        bot = Cerebro(None, self.mem)
        bot._pedir = lambda mensajes, tarea="fondo": respuesta_plan()
        ctx = {"detectado": {}, "probable": {"actividad": {"valor": "estudio"}}, "confirmado": {}}
        with patch("contexto_motor.obtener_motor_contexto", return_value=SimpleNamespace(obtener_contexto=lambda: ctx)):
            prompt = bot.instrucciones("Planifica una entrega segura por etapas")
        self.assertIn("[PLAN RECOMENDADO", prompt)
        self.assertIn("ESTADO ACTUAL EN VIVO", prompt) if "ESTADO ACTUAL EN VIVO" in prompt else None


if __name__ == "__main__":
    unittest.main()
