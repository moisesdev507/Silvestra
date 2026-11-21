"""Escenarios globales de cierre Fase 5 sobre almacenamiento aislado."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import planificador_modelo as pm
from cerebro import Cerebro
from ejecucion_modelo import ContratoHerramienta
from ejecucion_registro import RegistroHerramientas, SistemaEjecucion
from integracion_cognitiva_fase5 import IntegracionCognitivaFase5
from memoria_almacen import AlmacenMemoriaCognitiva
from memoria_gestor import GestorMemoria
from permisos_modelo import PoliticaOperacion, NIVEL_REQUIERE_CONFIRMACION
from permisos_motor import MotorPermisos
from razonamiento_motor import razonar, formatear
from verificacion_modelo import CriterioVerificacion, EvidenciaVerificacion, InformeVerificacion
from verificacion_motor import MotorVerificacionRecuperacion


class IntegracionGlobalFase5(unittest.TestCase):
    def setUp(self):
        self.store=AlmacenMemoriaCognitiva(":memory:","u1")
        self.mem=SimpleNamespace(almacen=self.store,usuario_id="u1")
        self.core=IntegracionCognitivaFase5(self.mem)

    def tearDown(self):
        self.core.cerrar(); self.store.cerrar()

    def background(self, fn):
        box=[]
        t=threading.Thread(target=lambda:box.append(fn()),daemon=True); t.start(); t.join(2)
        self.assertFalse(t.is_alive(),"worker se bloqueó")
        return box[0]

    def test_A_resolucion_memoria_grafo_y_consulta_simple(self):
        gestor=GestorMemoria(self.store,"u1")
        gestor.guardar("El servicio de pagos usa OAuth con reintentos ante fallos de red.",
            tipo_memoria="semantica",origen="explicito",confianza=.95)
        paquete=gestor.razonar("¿Qué opciones hay para mejorar pagos y evitar errores de red?",usuario_id="u1")
        r=razonar("compara alternativas de pagos",resultado_memoria=paquete)
        self.assertTrue(paquete.get("evidencia"))
        self.assertIn("relaciones",paquete)
        self.assertTrue(r.hechos)
        calls=[]
        self.mem.razonar=lambda *a,**k:calls.append(a) or {}
        with patch("cerebro.construir_prompt",return_value="prompt"):
            Cerebro(None,self.mem,app=SimpleNamespace(integracion_cognitiva=self.core)).instrucciones("hola")
        self.assertEqual(calls,[])

    def test_B_plan_y_aprobacion_separada(self):
        leccion=self.core.experiencias.registrar({"resultado_esperado":"conexión estable",
            "resultado_observado":"falló conexión por timeout repetido","factores":["wifi"],
            "origen_ids":["t-1"],"verificada":True,"exito":False,"categoria":"wifi"})["aprendizaje"]
        out=self.core.planificacion.crear_plan("Planifica reparar conexión wifi; requisitos: respaldo; restricción: sin reiniciar")
        plan=out["plan"]
        self.assertTrue(plan.fases and plan.todas_las_tareas())
        out=self.core.planificacion.crear_plan("Planifica reparar wifi",contexto={"aprendizajes_experienciales":[leccion]})
        plan=out["plan"]
        self.assertIn("Lecciones históricas orientativas",out["analisis"].decision.justificacion)
        with self.assertRaises(PermissionError):
            self.core.planificacion.preparar_ejecucion(plan.id_plan,plan.todas_las_tareas()[0].id_tarea,"tool")
        self.assertTrue(self.core.planificacion.aprobar_recomendacion(plan.id_plan,"usuario"))
        sol=self.core.planificacion.preparar_ejecucion(plan.id_plan,plan.todas_las_tareas()[0].id_tarea,"tool")
        self.assertEqual(sol.id_plan,plan.id_plan)
        _,analysis=self.core.planificacion.obtener(plan.id_plan)
        self.assertEqual(analysis.decision.autorizacion_ejecucion,"no_solicitada")

    def test_C_verificacion_dedup_fuentes_y_patron(self):
        for i in range(1,4):
            plan,tarea=f"p{i}",f"t{i}"
            self.core.adaptador.recibir_tarea(plan,tarea,"fallida",False)
            inf=InformeVerificacion(f"req{i}","wifi",solicitud_original={"id_plan":plan,"id_tarea":tarea,"herramienta":"wifi"},
                resultado_esperado={"estado":"conectado"},estado_final="fallido",
                errores_detectados=["timeout"],evidencia=EvidenciaVerificacion("comprobador",True,False,datos={"codigo":"TIMEOUT"}))
            self.core.verificador._emitir(inf)
        self.core.adaptador.esperar()
        with self.store._lock:
            rows=self.store.conexion.execute("SELECT origen_clave,verificada FROM experiencias_fase5 WHERE usuario_id='u1' AND origen_clave LIKE 'plan:%'").fetchall()
        self.assertEqual(len(rows),3)
        self.assertTrue(all(x["verificada"] for x in rows))
        aprendido=self.core.experiencias.recuperar("wifi timeout",5)
        self.assertTrue(any(x["tipo"]=="patron" and x["estado"]=="validado" for x in aprendido))
        self.core.adaptador.recibir_tarea("p1","t1","fallida",False); self.core.adaptador.esperar()
        with self.store._lock:
            count=self.store.conexion.execute("SELECT COUNT(*) FROM experiencias_fase5 WHERE usuario_id='u1' AND origen_clave='plan:p1|tarea:t1'").fetchone()[0]
        self.assertEqual(count,1)

    def test_D_replanificacion_preserva_completadas(self):
        plan=self.core.planificacion.crear_plan("Planifica migrar un servicio por etapas")["plan"]
        first=plan.todas_las_tareas()[0]
        ok,_,_=self.core.planificacion.actualizar_estado(plan.id_plan,first.id_tarea,"completada")
        self.assertTrue(ok)
        fase=pm.Fase("f1",1,"Etapa",tareas=[pm.Tarea(first.id_tarea,"Ya terminada alterada",fase_id="f1"),
            pm.Tarea("next","Siguiente paso",fase_id="f1",dependencias=[first.id_tarea])])
        new=pm.PlanObjetivo("nuevo","nuevo","nuevo",fases=[fase])
        result=self.core.planificacion.replanificar_contexto(plan.id_plan,new,{"detectado":{"ventana":{"ejecutable":"Code.exe"}},"probable":{},"confirmado":{}})
        self.assertTrue(result["actualizado"])
        recovered=self.core.planificacion.obtener(plan.id_plan)[0]
        self.assertEqual(recovered.mapa_tareas()[first.id_tarea].estado,"completada")
        self.assertIn("next",recovered.mapa_tareas())

    def test_E_contexto_vivo_privacidad_y_aislamiento(self):
        self.core.experiencias.registrar({"resultado_observado":"La app abrió ventana sensible de banco.",
            "origen_ids":["private-1"],"verificada":True,"exito":True,"categoria":"ventana"})
        other=IntegracionCognitivaFase5(SimpleNamespace(almacen=self.store,usuario_id="u2"))
        self.assertEqual(other.experiencias.recuperar("ventana banco",5),[])
        r=razonar("¿Qué está abierto ahora?",resultado_memoria={"evidencia":[]},
            contexto_engine={"detectado":{"ventana":{"ejecutable":"bank.exe","titulo":"password.txt"}}},
            multimodal={"ventana":{"ejecutable":"bank.exe","titulo":"password.txt","titulo_omitido":True}})
        txt=formatear(r,1600)
        self.assertIn("[ESTADO ACTUAL EN VIVO DE WINDOWS]",txt)
        self.assertIn("bank.exe",txt)
        self.assertNotIn("password.txt",txt)
        other.cerrar()

    def test_G_migracion_aditiva_de_experiencias_etapa3(self):
        from experiencia_almacen import AlmacenExperiencias
        legacy=AlmacenMemoriaCognitiva(":memory:","u1")
        AlmacenExperiencias(legacy)
        with legacy.transaccion() as con:
            con.execute("DROP TABLE experiencias_fase5")
            con.execute("CREATE TABLE experiencias_fase5(usuario_id TEXT,id_experiencia TEXT,clave_patron TEXT,exito INTEGER,verificada INTEGER,documento_json TEXT,creado_en REAL,PRIMARY KEY(usuario_id,id_experiencia))")
            con.execute("INSERT INTO experiencias_fase5 VALUES(?,?,?,?,?,?,?)",("u1","old","pat",0,1,'{"origen_ids":["req","plan-x","task-y"]}',1.0))
        AlmacenExperiencias(legacy)
        with legacy._lock:
            row=legacy.conexion.execute("SELECT origen_clave FROM experiencias_fase5 WHERE id_experiencia='old'").fetchone()
            idx=legacy.conexion.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_exp_usuario_origen'").fetchone()
        self.assertEqual(row[0],"plan:plan-x|tarea:task-y")
        self.assertIsNotNone(idx)
        legacy.cerrar()

    def test_F_ejecucion_controlada_verificacion_y_cierre(self):
        self.core.cerrar()
        permisos=MotorPermisos(); registry=RegistroHerramientas(); calls=[]
        registry.registrar(ContratoHerramienta("demo","test","safe test handler",
            handler=lambda p:calls.append(p) or {"ok":True},nivel_riesgo="bajo"))
        system=SistemaEjecucion(registry,motor_permisos=permisos)
        verifier=MotorVerificacionRecuperacion()
        core=IntegracionCognitivaFase5(self.mem,sistema_ejecucion=system,verificador=verifier,motor_permisos=permisos)
        plan=core.planificacion.crear_plan("Planifica ejecutar demo con verificación")["plan"]
        task=plan.todas_las_tareas()[0]
        with self.assertRaises(PermissionError): core.planificacion.preparar_ejecucion(plan.id_plan,task.id_tarea,"demo")
        core.planificacion.aprobar_recomendacion(plan.id_plan,"usuario")
        denied=core.planificacion.preparar_ejecucion(plan.id_plan,task.id_tarea,"demo")
        a=self.background(lambda:core.ejecutar_solicitud(denied,{"ok":True}))
        self.assertEqual(a["resultado"].error["codigo"],"SIN_POLITICA")
        self.assertEqual(calls,[])
        permitted=core.planificacion.preparar_ejecucion(plan.id_plan,task.id_tarea,"demo")
        permisos.registrar_politica(PoliticaOperacion("demo",NIVEL_REQUIERE_CONFIRMACION,
            riesgo_maximo_permitido="bajo"),actor="sistema_inicio")
        contrato=registry.obtener("demo")
        pending=permisos.evaluar_solicitud(permitted,contrato)
        self.assertEqual(pending["decision"],"pendiente_autorizacion")
        self.assertTrue(permisos.confirmar_autorizacion(pending["id_autorizacion"],actor="usuario")["aprobada"])
        verifier.registrar_estrategia(CriterioVerificacion("demo"),lambda s,r,e:
            EvidenciaVerificacion("test",True,bool(r.exito),datos={"ok":bool(r.exito)}))
        done=threading.Thread(target=lambda:core.ejecutar_solicitud(permitted,{"ok":True}),daemon=True)
        done.start(); done.join(2); self.assertFalse(done.is_alive())
        core.adaptador.esperar()
        self.assertEqual(len(calls),1)
        self.assertTrue(core.experiencias.recuperar("demo",5))
        event=threading.Event(); event.set()
        before=len(calls)
        self.assertTrue(self.background(lambda:core.ejecutar_solicitud(permitted,{"ok":True},event))["cancelado"])
        self.assertEqual(len(calls),before)
        core.cerrar(); core.cerrar(); self.assertFalse(core.adaptador._hilo.is_alive())


if __name__ == "__main__": unittest.main()
