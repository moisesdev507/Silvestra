"""Cobertura sintética de integración multimodal sin dispositivos ni red."""
import os
import queue
import threading
import time
import unittest
from types import SimpleNamespace as NS
import numpy as np
from multimodal_integracion_modelo import (ObservacionIntegrada,
    PoliticaIntegracionMultimodal, sanitizar_valor)
from multimodal_correlacionador import CorrelacionadorMultimodal
from multimodal_integracion_motor import MotorIntegracionMultimodal
from audio_evento_modelo import EventoAcustico, ClasificacionAcustica, CategoriaSonido
from camara_percepcion_modelo import ObservacionCamara
from ui_visual_modelo import MapaInterfazVisual, AlertaInterfazUI, CambioInterfazVisual
from vision_modelo import ResultadoComprensionVisual


class TestIntegracionMultimodal(unittest.TestCase):
    def setUp(self): self.motor = MotorIntegracionMultimodal()

    def test_01_normaliza_vision_camara_interfaz(self):
        vision=ResultadoComprensionVisual("v1","private.png",descripcion="Ventana visible",nivel_confianza=.8)
        cam=ObservacionCamara(time.time(),"camara",.4,resumen_breve="Movimiento detectado")
        alerta=AlertaInterfazUI(tipo="error",texto="Error visible")
        mapa=MapaInterfazVisual(aplicacion="editor",alertas=[alerta])
        self.assertEqual(self.motor.ingerir_vision(vision).modalidades_activas,["vision"])
        self.motor.ingerir_camara(cam); self.motor.ingerir_interfaz(mapa)
        self.assertEqual({o.modalidad for o in self.motor._observaciones},{"vision","camara","interfaz"})

    def test_02_normaliza_audio_y_filtra_eco_ruido(self):
        e=EventoAcustico(clasificacion=ClasificacionAcustica(CategoriaSonido.alarma,"",.9,False,True,"test"),relevancia="critica")
        self.assertIsNotNone(self.motor.ingerir_audio(e))
        e.clasificacion.categoria=CategoriaSonido.eco_silvestra
        self.assertIsNone(self.motor.ingerir_audio(e))
        e.clasificacion.categoria=CategoriaSonido.ruido_ambiental
        self.assertIsNone(self.motor.ingerir_audio(e))

    def test_03_contexto_windows(self):
        self.motor.ingerir_contexto_windows({"ejecutable":"editor.exe","hwnd":8,"timestamp":time.time()})
        self.assertEqual(self.motor._contexto_windows["ejecutable"],"editor.exe")

    def test_04_alarma_y_alerta_correlacionan(self):
        self.motor.ingerir_audio(EventoAcustico(clasificacion=ClasificacionAcustica(CategoriaSonido.alarma,"",.8,False,True,"local"),relevancia="critica"),)
        self.motor.ingerir_alerta_interfaz(AlertaInterfazUI(texto="Notificación visible"))
        self.assertTrue(self.motor.consultar_situacion_actual()["correlaciones_probables"])

    def test_05_error_y_actividad_misma_app(self):
        self.motor.ingerir_contexto_windows({"ejecutable":"editor.exe","hwnd":21})
        self.motor.ingerir_interfaz(MapaInterfazVisual(aplicacion="editor.exe",hwnd=21,
            alertas=[AlertaInterfazUI(tipo="error",texto="Error visible")]))
        self.assertTrue(self.motor._situaciones[-1].correlaciones_probables)

    def test_06_cambio_y_audio_con_contexto_compartido(self):
        ctx={"aplicacion":"browser","hwnd":5}
        a=ObservacionIntegrada("camara","cambio","Cambio visual",etiquetas_semanticas=("alerta",),contexto_asociado=ctx)
        b=ObservacionIntegrada("audio","alarma","Alarma",etiquetas_semanticas=("alerta",),contexto_asociado=ctx)
        self.assertTrue(CorrelacionadorMultimodal().correlacionar([a,b]))

    def test_07_no_correlaciona_solo_por_tiempo(self):
        now=time.time()
        a=ObservacionIntegrada("audio","sonido","Sonido ambiental",timestamp=now,etiquetas_semanticas=("ladrido",))
        b=ObservacionIntegrada("contexto","aplicacion","Editor abierto",timestamp=now+1,etiquetas_semanticas=("editor",),contexto_asociado={"aplicacion":"editor"})
        self.assertEqual(CorrelacionadorMultimodal().correlacionar([a,b]),[])

    def test_08_confianza_none_hechos_separados(self):
        o=ObservacionIntegrada("audio","evento","Posible alarma",etiquetas_semanticas=("alarma",),nivel_confianza="0.8",datos_estructurados={"nivel_epistemico":"probable"})
        self.assertIsNone(o.nivel_confianza)
        self.motor.registrar_observacion(o,publicar=False)
        self.assertEqual(self.motor.consultar_situacion_actual()["hechos_confirmados"],[])

    def test_09_deduplicacion(self):
        o=ObservacionIntegrada("vision","imagen","Alerta visible",huella_dedup="misma")
        self.assertIsNotNone(self.motor.registrar_observacion(o,False))
        self.assertIsNone(self.motor.registrar_observacion(ObservacionIntegrada("vision","imagen","Alerta visible",huella_dedup="misma"),False))

    def test_10_eventos_fuera_de_orden(self):
        now=time.time()
        a=ObservacionIntegrada("audio","alarma","Alarma",timestamp=now+2,etiquetas_semanticas=("alerta",))
        b=ObservacionIntegrada("interfaz","popup","Aviso",timestamp=now,etiquetas_semanticas=("alerta",))
        self.motor.registrar_observacion(a,False); situ=self.motor.registrar_observacion(b,False)
        self.assertTrue(situ.correlaciones_probables)
        self.assertEqual([o.timestamp for o in self.motor._observaciones],[now,now+2])

    def test_11_ttl_observaciones(self):
        m=MotorIntegracionMultimodal(PoliticaIntegracionMultimodal(ttl_observacion_seg=1))
        m.registrar_observacion(ObservacionIntegrada("vision","dato","Viejo",timestamp=time.time()-4),False)
        self.assertEqual(m.consultar_situacion_actual()["hechos_confirmados"],[])

    def test_12_fallos_parciales(self):
        self.motor.registrar_fallo_modalidad("camara","offline")
        self.motor.ingerir_contexto_windows({"ejecutable":"editor.exe"})
        self.assertIn("camara",self.motor.consultar_situacion_actual()["situacion"].modalidades_con_fallo)
        self.motor.recuperar_modalidad("camara")

    def test_13_cancelacion_y_aislamiento(self):
        tok=threading.Event(); tok.set()
        with self.assertRaises(InterruptedError): self.motor.registrar_observacion(ObservacionIntegrada("vision","x","x"),token_cancelacion=tok)
        with self.assertRaises(TypeError): self.motor.registrar_observacion(object())

    def test_14_higiene_de_datos(self):
        datos=sanitizar_valor({"pcm":np.zeros(5),"bytes_wav":b"WAVE","ruta_captura":"C:\\temp\\a.png","api_key":"token=secreto","ok":"visible"})
        self.assertNotIn("pcm",datos); self.assertNotIn("bytes_wav",datos)
        self.assertNotIn("ruta_captura",datos); self.assertIn("***",datos["api_key"])
        self.assertEqual(datos["ok"],"visible")

    def test_15_integraciones_y_consulta(self):
        class Init:
            llamado=False
            def evaluar_oportunidad(self,app,contexto): self.llamado=True
        init=Init(); cerebro=NS(historial=[]); contexto=NS(confirmar_contexto=lambda *a,**k:None)
        cola=queue.Queue(); app=object()
        m=MotorIntegracionMultimodal(cerebro=cerebro,contexto_motor=contexto,
            iniciativa_contextual=init,app=app,app_cola=cola)
        m.ingerir_vision(ResultadoComprensionVisual("id","",descripcion="Imagen observada",observaciones_verificables=["texto visible"]))
        self.assertTrue(cerebro.historial and init.llamado and not cola.empty())
        self.assertLessEqual(len(cerebro.historial[0]["content"]),562)
        self.assertIn("Imagen observada",m.consultar_situacion_actual("que ocurre")["respuesta"])

    def test_16_no_ejecutores_y_aviso_ui_seguro(self):
        for f in ("multimodal_integracion_modelo.py","multimodal_correlacionador.py","multimodal_integracion_motor.py"):
            with open(f,encoding="utf-8") as archivo: src=archivo.read()
            for name in ("archivos_operaciones","procesos_operaciones","gui_interaccion"):
                self.assertNotIn(name,src)
        with open("multimodal_integracion_motor.py",encoding="utf-8") as f: self.assertIn("requiere_ejecucion=False",f.read())
        with open("eventos.py",encoding="utf-8") as f: self.assertIn("puede_actualizar_ui()",f.read())

    def test_17_limites_de_memoria(self):
        pol=PoliticaIntegracionMultimodal(max_observaciones_historial=2)
        m=MotorIntegracionMultimodal(pol)
        for i in range(5): m.registrar_observacion(ObservacionIntegrada("vision","e",str(i),huella_dedup=str(i)),False)
        self.assertLessEqual(len(m._observaciones),2)
        self.assertFalse(any(isinstance(v,np.ndarray) for o in m._observaciones for v in o.datos_estructurados.values()))

    def test_18_privacidad_externa_y_propuesta_pasiva(self):
        self.assertFalse(PoliticaIntegracionMultimodal().autorizacion_externa)
        class Orch:
            kwargs=None
            def recibir(self,*a,**k): self.kwargs=k
        orch=Orch(); m=MotorIntegracionMultimodal(orquestador=orch)
        s=m._consolidar(); s.sugerencia_accion={"propuesta":"revisar"}; m._publicar(s)
        self.assertFalse(orch.kwargs["requiere_ejecucion"])


if __name__ == "__main__": unittest.main()
