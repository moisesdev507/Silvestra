"""Regresión del aprendizaje experiencial sin acceder a datos reales."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from memoria_almacen import AlmacenMemoriaCognitiva
from experiencia_analizador import analizar
from experiencia_motor import MotorExperiencias
from experiencia_integracion import AdaptadorExperiencias
from experiencia_modelos import Aprendizaje
from razonamiento_motor import razonar, formatear
from planificacion_motor import PlanificacionMotor
from ejecucion_registro import SistemaEjecucion
from ejecucion_modelo import SolicitudEjecucion, ResultadoEjecucion, ContratoHerramienta
from verificacion_motor import MotorVerificacionRecuperacion
from verificacion_modelo import InformeVerificacion, EvidenciaVerificacion


class ExperienciasFase5(unittest.TestCase):
    def setUp(self):
        self.almacen = AlmacenMemoriaCognitiva(":memory:", "ana")
        self.motor = MotorExperiencias(self.almacen, "ana")

    def tearDown(self):
        self.almacen.cerrar()

    def exp(self, n, ok=False, cat="wifi", facts=("conexion",)):
        return self.motor.registrar({"resultado_esperado":"conexión estable", "resultado_observado":
            "conexión estable confirmada" if ok else "falló conexión por timeout de red", "factores":facts,
            "origen_ids":["tarea-"+str(n)], "verificada":True, "exito":ok, "categoria":cat,
            "condiciones":["red local"]})

    def test_01_analiza_resultado_exitoso_y_fallido(self):
        a=analizar({"resultado_esperado":"x","resultado_observado":"resultado confirmado", "verificada":True,"exito":True})
        b=analizar({"resultado_esperado":"x","resultado_observado":"resultado fallido", "verificada":True,"exito":False})
        self.assertTrue(a["util"]); self.assertTrue(b["util"])
        self.assertNotEqual(a["exito"],b["exito"])

    def test_02_identifica_errores_recurrentes(self):
        for i in range(3): r=self.exp(i)
        self.assertEqual(r["evidencias"],3)
        self.assertEqual(r["aprendizaje"]["tipo"],"patron")

    def test_03_extrae_aprendizaje_con_procedencia(self):
        a=self.exp(1,True)["aprendizaje"]
        self.assertIn("tarea-1",a["origen_ids"])
        self.assertTrue(a["resultado_observado"]); self.assertTrue(a["interpretacion"])

    def test_04_patron_solo_con_tres_fuentes(self):
        self.assertEqual(self.exp(1)["aprendizaje"]["estado"],"preliminar")
        self.assertEqual(self.exp(2)["aprendizaje"]["estado"],"preliminar")
        self.assertEqual(self.exp(3)["aprendizaje"]["estado"],"validado")

    def test_05_observacion_separada_de_interpretacion(self):
        a=self.exp(1)["aprendizaje"]
        self.assertIn("timeout",a["resultado_observado"])
        self.assertIn("Estrategia preventiva",a["interpretacion"])
        self.assertNotEqual(a["resultado_observado"],a["interpretacion"])

    def test_06_recupera_por_relevancia_y_vigencia(self):
        self.exp(1); self.exp(2); self.exp(3)
        self.assertEqual(len(self.motor.recuperar("wifi timeout",3)),1)
        self.assertEqual(self.motor.recuperar("receta de cocina",3),[])

    def test_07_razonamiento_muestra_leccion_historica(self):
        self.exp(1); self.exp(2); a=self.exp(3)["aprendizaje"]
        r=razonar("consulta wifi",resultado_memoria={"evidencia":[]},aprendizajes_experienciales=[a])
        self.assertEqual(len(r.aprendizajes_experienciales),1)
        self.assertIn("HISTÓRICOS, NO HECHOS ACTUALES",formatear(r))

    def test_08_planificador_usa_lecciones_orientativas(self):
        self.exp(1); self.exp(2); a=self.exp(3)["aprendizaje"]
        plan=PlanificacionMotor(self.almacen,"ana")
        out=plan.crear_plan("Planifica revisar conexión wifi",contexto={"aprendizajes_experienciales":[a]})
        self.assertIn("Lecciones históricas orientativas",out["analisis"].decision.justificacion)
        self.assertEqual(out["analisis"].decision.aprobacion_usuario,"pendiente")
        self.assertEqual(out["analisis"].decision.autorizacion_ejecucion,"no_solicitada")

    def test_09_compara_eficacia_y_degrada(self):
        a=self.exp(1)["aprendizaje"]
        self.assertTrue(self.motor.evaluar_eficacia(a["id_aprendizaje"],.2,.9))
        self.assertFalse(self.motor.evaluar_eficacia(a["id_aprendizaje"],.9,.2))

    def test_10_confianza_se_actualiza_con_evidencia(self):
        primera=self.exp(1)["aprendizaje"]["confianza"]
        self.exp(2); final=self.exp(3)["aprendizaje"]["confianza"]
        self.assertGreater(final,primera)
        self.assertEqual(final,(1+3)/(2+3))

    def test_11_contradiccion_cambia_estado(self):
        self.exp(1,True); self.exp(2,True); self.exp(3,False); final=self.exp(4,False)["aprendizaje"]
        self.assertEqual(final["estado"],"contradicho")

    def test_12_experiencia_unica_no_generaliza(self):
        a=self.exp(1,True)["aprendizaje"]
        self.assertEqual(a["estado"],"preliminar")
        self.assertNotEqual(a["tipo"],"patron")

    def test_13_persistencia_aislada_por_usuario(self):
        self.exp(1,True)
        otro=MotorExperiencias(self.almacen,"luis")
        self.assertEqual(otro.recuperar("wifi",4),[])
        self.assertEqual(len(self.motor.recuperar("wifi",4)),1)

    def test_14_privacidad_cancelacion_y_listener_verificacion(self):
        secreto=self.motor.registrar({"resultado_observado":"mi token es sk-12345678901234567890","verificada":True})
        self.assertFalse(secreto["registrada"])
        cancel=threading.Event(); cancel.set()
        self.assertTrue(self.motor.registrar({"resultado_observado":"resultado suficientemente largo"},cancel)["cancelado"])
        ver=MotorVerificacionRecuperacion(); adapt=AdaptadorExperiencias(self.motor)
        self.assertTrue(adapt.conectar_verificacion(ver))
        inf=InformeVerificacion("req-1","wifi",resultado_esperado="conexión estable",estado_final="verificado",
            evidencia=EvidenciaVerificacion("test",True,True))
        ver._emitir(inf); adapt.esperar()
        self.assertTrue(self.motor.recuperar("verificacion",5))
        pmotor=PlanificacionMotor(self.almacen,"ana")
        self.assertTrue(adapt.conectar_planificacion(pmotor))
        plan=pmotor.crear_plan("organiza revisar conexion wifi")["plan"]
        tarea=plan.fases[0].tareas[0]
        pmotor.actualizar_estado(plan.id_plan,tarea.id_tarea,"fallida","prueba controlada")
        sistema=SistemaEjecucion()
        self.assertTrue(adapt.conectar_ejecucion(sistema))
        sol=SolicitudEjecucion("planificador","wifi")
        res=ResultadoEjecucion(sol.id_solicitud,"wifi","completada",True,datos={"ok":True})
        sistema.post_ejecucion(sol,ContratoHerramienta("wifi","prueba","prueba"),res)
        adapt.esperar()
        with self.almacen._lock:
            n=self.almacen.conexion.execute("SELECT COUNT(*) FROM experiencias_fase5 WHERE usuario_id='ana'").fetchone()[0]
        self.assertGreaterEqual(n,3)
        adapt.cerrar()
        import ast, pathlib
        for name in ("experiencia_motor.py","experiencia_almacen.py","experiencia_analizador.py"):
            tree=ast.parse(pathlib.Path(name).read_text(encoding="utf-8"))
            imports={a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
            imports|={n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
            self.assertFalse({"permisos_motor","acciones"}&imports)

    def test_15_cerebro_inyecta_aprendizaje_sin_tocar_contexto_vivo(self):
        self.exp(1); self.exp(2); self.exp(3)
        from cerebro import Cerebro
        mem=SimpleNamespace(usuario_id="ana",almacen=self.almacen,
            razonar=lambda *a,**kw:{"recuperacion":{},"evidencia":[]})
        captured={}
        with patch("contexto_motor.obtener_motor_contexto",return_value=SimpleNamespace(
                obtener_contexto=lambda:{"detectado":{},"probable":{},"confirmado":{}})), \
             patch("cerebro.construir_prompt",side_effect=lambda *a,**kw: captured.update(kw) or "prompt"):
            brain=Cerebro(None,mem)
            brain.instrucciones("¿Cómo resolver el fallo de conexión wifi?")
        self.assertIn("[APRENDIZAJES DE EXPERIENCIAS",captured["contexto_adicional"])


if __name__ == "__main__":
    unittest.main()
