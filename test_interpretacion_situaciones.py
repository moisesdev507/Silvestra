"""Pruebas sintéticas de interpretación razonada y memoria temporal."""
import os
import queue
import threading
import time
import unittest
from types import SimpleNamespace as NS
import numpy as np
from multimodal_integracion_modelo import (ObservacionIntegrada,
    CorrelacionMultimodal, SituacionIntegrada)
from situacion_interpretacion_modelo import (InterpretacionSituacion,
    EvidenciaSituacion, EstadoSituacion, NivelIncertidumbre,
    PoliticaInterpretacionSituaciones)
from situacion_evaluador import EvaluadorPatronSituacion
from situacion_memoria_temporal import GestorMemoriaSituaciones
from situacion_interpretacion_motor import MotorInterpretacionSituaciones


def obs(mod, texto, ts=None, tags=(), conf=None, rel="media", ctx=None, ident=None):
    return ObservacionIntegrada(mod,"evento",texto,id_observacion=ident or texto,
        timestamp=ts or time.time(),etiquetas_semanticas=tags,nivel_confianza=conf,
        relevancia=rel,contexto_asociado=ctx or {})


class TestSituaciones(unittest.TestCase):
    def setUp(self): self.motor=MotorInterpretacionSituaciones()

    def test_01_evento_visual_error(self):
        r=self.motor.interpretar([obs("interfaz","Error visible en pantalla",tags=("error",),conf=.8)])
        self.assertEqual(r.categoria_situacion,"incidencia_informatica")
        self.assertIn("Error visible en pantalla",r.hechos_observados)

    def test_02_evento_auditivo(self):
        r=self.motor.interpretar([obs("audio","Clasificador reporta alarma",tags=("alarma",),rel="alta")])
        self.assertEqual(r.categoria_situacion,"alerta_ambiental")

    def test_03_incidencia_multifuente(self):
        osb=[obs("interfaz","Error de aplicación",tags=("error",),ctx={"aplicacion":"editor"}),
             obs("contexto","Editor activo",tags=("editor",),ctx={"aplicacion":"editor"})]
        r=self.motor.interpretar(osb)
        self.assertEqual(r.categoria_situacion,"incidencia_informatica")
        self.assertFalse(r.conclusiones_verificadas)

    def test_04_alerta_sin_causalidad(self):
        a=obs("audio","Audio etiquetado alarma",tags=("alarma",))
        b=obs("vision","Notificación visual",tags=("alerta",))
        c=CorrelacionMultimodal(("audio","vision"),(a.id_observacion,b.id_observacion),"temporal",.8,
            hipotesis_correlacion="Podrían estar relacionadas; no se conoce causa.")
        r=self.motor.interpretar([a,b],[c])
        self.assertTrue(r.relaciones_probables)
        self.assertFalse(any("caus" in x.lower() for x in r.conclusiones_verificadas))

    def test_05_secuencia_temporal(self):
        t=time.time(); xs=[obs("vision","Cambio pantalla",t+2,("cambio",)),obs("interfaz","Nuevo mensaje",t+1,("mensaje",))]
        r=self.motor.interpretar(xs)
        self.assertEqual(len(r.secuencia_temporal),2)
        self.assertIn("Nuevo mensaje",r.secuencia_temporal[0])

    def test_06_informacion_insuficiente(self):
        r=self.motor.interpretar([obs("audio","Golpe aislado",tags=("golpes",))])
        self.assertEqual(r.nivel_incertidumbre,NivelIncertidumbre.insuficiente)
        self.assertTrue(r.lagunas_informacion)
        self.assertIsNone(r.confianza_interpretacion)

    def test_07_anomalia_multimodal(self):
        xs=[obs("audio","Sonido repetido A",tags=("sonido",)),obs("audio","Sonido repetido B",tags=("sonido",)),
            obs("audio","Sonido repetido C",tags=("sonido",)),obs("vision","Pantalla activa",tags=("estado",))]
        r=self.motor.interpretar(xs)
        self.assertEqual(r.categoria_situacion,"anomalia_multimodal")
        self.assertTrue(r.hipotesis)

    def test_08_confianza_y_riesgo(self):
        a=self.motor.interpretar([obs("vision","Dato A",conf=None)])
        self.assertIsNone(a.confianza_interpretacion)
        b=self.motor.interpretar([obs("vision","Dato B",conf="0.7")])
        self.assertIsNone(b.confianza_interpretacion)
        self.assertGreaterEqual(b.riesgo_falso_positivo,0)

    def test_09_campos_epistemicos_separados(self):
        x=obs("audio","Alarma clasificada",tags=("alarma",))
        y=obs("interfaz","Aviso presente",tags=("alerta",))
        c=CorrelacionMultimodal(("audio","interfaz"),(x.id_observacion,y.id_observacion),"posible",.7,
            hipotesis_correlacion="Coincidencia posible")
        r=self.motor.interpretar([x,y],[c])
        self.assertTrue(r.hechos_observados);self.assertTrue(r.relaciones_probables)
        self.assertTrue(r.hipotesis);self.assertFalse(r.conclusiones_verificadas)

    def test_10_actualiza_mismo_id(self):
        pol=PoliticaInterpretacionSituaciones(ventana_fusion_actualizacion_seg=30)
        mem=GestorMemoriaSituaciones(pol); now=time.time();ctx={"aplicacion":"editor"}
        a=InterpretacionSituacion("incidencia",now,now,contexto_asociado=ctx,
            evidencias=[EvidenciaSituacion("1","interfaz",now,"Error")],secuencia_temporal=["1 error"])
        first=mem.actualizar_o_agregar(a)
        b=InterpretacionSituacion("incidencia",now+2,now+2,contexto_asociado=ctx,
            evidencias=[EvidenciaSituacion("2","contexto",now+2,"Editor activo")],secuencia_temporal=["2 contexto"])
        second=mem.actualizar_o_agregar(b)
        self.assertEqual(first.id_situacion,second.id_situacion)
        self.assertEqual(second.estado,EstadoSituacion.actualizada)

    def test_11_no_duplica_evidencia_ni_secuencia(self):
        mem=GestorMemoriaSituaciones(); now=time.time();ctx={"hwnd":4}
        s=InterpretacionSituacion("alerta",now,now,contexto_asociado=ctx,
            evidencias=[EvidenciaSituacion("same","audio",now,"alarma")],secuencia_temporal=["t alarma"])
        mem.actualizar_o_agregar(s)
        again=InterpretacionSituacion("alerta",now+1,now+1,contexto_asociado=ctx,
            evidencias=[EvidenciaSituacion("same","audio",now,"alarma")],secuencia_temporal=["t alarma"])
        out=mem.actualizar_o_agregar(again)
        self.assertEqual(len(out.evidencias),1);self.assertEqual(len(out.secuencia_temporal),1)

    def test_12_resuelve_expira_y_limita(self):
        p=PoliticaInterpretacionSituaciones(max_situaciones_activas=2,ttl_situacion_seg=3)
        mem=GestorMemoriaSituaciones(p);now=time.time()
        xs=[InterpretacionSituacion(str(i),now+i*10,now+i*10) for i in range(3)]
        for x in xs:mem.actualizar_o_agregar(x)
        self.assertLessEqual(len(mem.listar_activas()),2)
        old=InterpretacionSituacion("vieja",now-10,now-10)
        mem.actualizar_o_agregar(old);mem.purgar(now)
        self.assertEqual(old.estado,EstadoSituacion.expirada)
        active=mem.listar_activas()
        self.assertTrue(mem.resolver(active[-1].id_situacion))

    def test_13_evaluador_extensible(self):
        class Custom(EvaluadorPatronSituacion):
            nombre="custom"
            def evaluar(self,*args):return {"categoria":"custom","relaciones":[],"hipotesis":["extensible"],"insuficiente":False}
        self.motor.registrar_evaluador(Custom())
        r=self.motor.interpretar([obs("vision","dato")])
        self.assertEqual(r.categoria_situacion,"custom")

    def test_14_puentes_cerebro_contexto_nl(self):
        cerebro=NS(historial=[]);ctx=NS(confirmar_contexto=lambda *a,**k:None)
        m=MotorInterpretacionSituaciones(cerebro=cerebro,contexto_motor=ctx)
        r=m.interpretar([obs("interfaz","Error verificado",tags=("error",),conf=.9)])
        self.assertLessEqual(len(cerebro.historial[-1]["content"]),550)
        self.assertIn("Error verificado",m.consultar_interpretacion_actual("que ocurre")["respuesta"])

    def test_15_iniciativa_pasiva_sin_ejecutores(self):
        class Init:
            llamada=False
            def evaluar_oportunidad(self,app,contexto):self.llamada=True
        init=Init();m=MotorInterpretacionSituaciones(iniciativa_contextual=init,app=object())
        m.interpretar([obs("interfaz","Error crítico",tags=("error",),rel="critica")])
        self.assertTrue(init.llamada)
        for f in ("situacion_interpretacion_modelo.py","situacion_evaluador.py","situacion_memoria_temporal.py","situacion_interpretacion_motor.py"):
            with open(f,encoding="utf-8") as h:src=h.read()
            for name in ("archivos_operaciones","procesos_operaciones","gui_interaccion"):self.assertNotIn(name,src)
        with open("situacion_interpretacion_motor.py",encoding="utf-8") as h:self.assertIn("requiere_ejecucion=False",h.read())

    def test_16_cancelacion_fallos_y_privacidad(self):
        tok=threading.Event();tok.set()
        with self.assertRaises(InterruptedError):self.motor.interpretar([obs("vision","x")],token_cancelacion=tok)
        m=MotorInterpretacionSituaciones();s=SituacionIntegrada("ventana")
        s.modalidades_con_fallo=["camara"];r=m.interpretar(s)
        self.assertIn("camara",r.modalidades_con_fallo)
        limpio=InterpretacionSituacion("x",1,1,hechos_observados=["password=abc"],sugerencia_pasiva={"bytes":b"raw","token":"secret"})
        self.assertNotIn(b"raw",repr(limpio).encode())

    def test_17_app_cola_y_memoria_solo_metadatos(self):
        cola=queue.Queue();m=MotorInterpretacionSituaciones(app_cola=cola)
        m.interpretar([obs("interfaz","Error crítico",tags=("error",),rel="critica")])
        self.assertEqual(cola.get_nowait()[0],"multimodal_situacion")
        for s in m.memoria.listar_activas():
            for e in s.evidencias:self.assertNotIsInstance(e.descripcion_hecho,np.ndarray)

    def test_18_autorizacion_externa_y_presupuesto(self):
        self.assertFalse(PoliticaInterpretacionSituaciones().autorizacion_externa)
        for f in ("situacion_interpretacion_modelo.py","situacion_evaluador.py","situacion_memoria_temporal.py","situacion_interpretacion_motor.py","test_interpretacion_situaciones.py"):
            self.assertLessEqual(os.path.getsize(f),15360)


if __name__=="__main__":unittest.main()
