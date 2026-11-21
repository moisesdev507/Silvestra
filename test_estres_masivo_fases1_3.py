import math
import queue
import threading
import time
import tracemalloc
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from audio_evento_modelo import EventoAcustico, ClasificacionAcustica, CategoriaSonido, NivelRelevanciaSonido
from camara_percepcion_modelo import PoliticaCapturaCamara
from camara_percepcion_motor import MotorPercepcionCamara
from cerebro import Cerebro
from multimodal_integracion_modelo import ObservacionIntegrada
from multimodal_integracion_motor import MotorIntegracionMultimodal as MotorMM
from multimodal_puente_app import SistemaMultimodalSilvestra as Sistema
from motor_ejecucion_estado import TokenCancelacion
from oido import Oido
from voz import Voz

class TestEstres(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(cola=queue.Queue(), voz=None, iniciativa=None)
        self.sistema = Sistema(self.app)
        self.sistema._activo = True
    def tearDown(self):
        self.sistema.detener()
    def paralelo(self, items, fn, workers=8, timeout=10):
        tareas, resultados, fallos = queue.Queue(), queue.Queue(), queue.Queue()
        for item in items:
            tareas.put(item)
        hilos = []
        def worker():
            while True:
                item = tareas.get()
                try:
                    if item is None:
                        return
                    resultados.put(fn(item))
                except BaseException as exc:
                    fallos.put(exc)
                finally:
                    tareas.task_done()
        for _ in range(workers):
            hilo = threading.Thread(target=worker, daemon=True)
            hilo.start(); hilos.append(hilo)
        for _ in hilos:
            tareas.put(None)
        fin = time.monotonic() + timeout
        for hilo in hilos:
            hilo.join(max(0, fin-time.monotonic()))
        self.assertFalse(any(h.is_alive() for h in hilos))
        self.assertTrue(fallos.empty())
        return list(resultados.queue)
    def test_01(self):
        def tormenta(sistema, duraciones=None):
            sistema.activar_fuente("camara", permiso=True)
            def evento(i):
                inicio=time.perf_counter(); tipo=i%5
                if tipo==0:sistema.registrar_vision(SimpleNamespace(descripcion=f"texto visual {i}",
                    observaciones_verificables=[f"hecho {i}"],timestamp=time.time(),
                    id_entrada=f"vision-{i}",nivel_confianza=.9))
                elif tipo==1:sistema.registrar_camara(SimpleNamespace(resumen_breve=f"cambio {i}",
                    puntuacion_cambio=.8,detecciones_locales=[],significativa=True,
                    datos_sanitizados={},id_observacion=f"camara-{i}"))
                elif tipo==2:sistema.registrar_interfaz(SimpleNamespace(aplicacion="ui.exe",hwnd=i+500,
                    alertas=[],elementos=[],timestamp=time.time(),id_mapa=f"ui-{i}"))
                elif tipo==3:sistema.registrar_audio(EventoAcustico(fuente="archivo",
                    clasificacion=ClasificacionAcustica(CategoriaSonido.alarma,confianza=.9,es_relevante=True),
                    relevancia=NivelRelevanciaSonido.critica,id_evento=f"audio-{i}"))
                else:
                    v=sistema._normalizar_ventana({"hwnd":i+100,"pid":i+1000,
                        "titulo":f"ChatGPT {i}","ejecutable":"ChatGPT.exe","clase":"Chrome_WidgetWin_1"})
                    sistema._registrar_ventana(v,"zorder")
                if duraciones is not None:duraciones.append(time.perf_counter()-inicio)
                return i
            return self.paralelo(range(500),evento,workers=8,timeout=12)
        duraciones=[]
        vistos=tormenta(self.sistema,duraciones)
        auxiliar=Sistema(SimpleNamespace(cola=queue.Queue(),voz=None,iniciativa=None))
        auxiliar._activo=True
        tracemalloc.start()
        try:
            tormenta(auxiliar)
            _,pico=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop(); auxiliar.detener()
        self.assertEqual(len(vistos), 500)
        p95 = sorted(duraciones)[math.ceil(.95*len(duraciones))-1]
        self.assertLess(p95, .035)
        self.assertLess(pico, 12*1024*1024)
        motor = self.sistema.integrador
        self.assertLessEqual(len(motor._observaciones), motor.politica.max_observaciones_historial)
        self.assertLessEqual(len(motor._situaciones), motor.politica.max_situaciones_historial)
        self.assertLessEqual(len(self.sistema.interprete.memoria.listar_activas()),
            self.sistema.interprete.politica.max_situaciones_activas)
    def test_02(self):
        class Reproductor:
            def __init__(self):
                self.lock=threading.Lock(); self.activos=0; self.cancelados=0; self.inicio=threading.Event()
            def reproducir(self, audio, version_check_fn, on_nivel_fn, on_inicio_fn):
                with self.lock: self.activos+=1
                self.inicio.set(); on_inicio_fn()
                try:
                    while version_check_fn(): time.sleep(.001)
                    with self.lock: self.cancelados+=1
                    return False
                finally:
                    with self.lock: self.activos-=1
            def esta_ocupado(self):
                with self.lock: return self.activos>0
        player=Reproductor()
        voz=object.__new__(Voz)
        voz.version=0; voz._activos=0; voz._estado_lock=threading.RLock()
        voz.nivel_volumen=0.0; voz.ult_primera_palabra=None; voz.proceso=None
        voz.pg=None; voz.reproductor=player; voz._parar=lambda:None
        voz._audio=lambda frase, emocion="neutral": b"audio-sintetico"
        oido=object.__new__(Oido); oido.bloqueo=threading.RLock(); oido._escuchando_activo=False
        entrada=threading.Event()
        def escuchar_falso(corto=False, app=None, generacion=None):
            entrada.set()
            while app._generacion_escucha==generacion and app.escuchando:
                time.sleep(.002)
            return None
        oido._escuchar=escuchar_falso
        app=SimpleNamespace(memoria=SimpleNamespace(nombre="Usuario"), cara=SimpleNamespace(
            poner_escuchando=lambda *_:None), oido=oido, cola=queue.Queue(), voz=voz,
            conversacion=True, escuchando=False, silencios=0, musica_activa=False,
            _generacion_escucha=0, _iniciar_reflexion=lambda:None)
        app.decir=lambda texto,*a,**k:voz.hablar(texto)
        from conversacion import alternar_conversacion, escuchar, dejar_de_escuchar
        escuchar(app)
        self.assertTrue(entrada.wait(1))
        app.decir("locución TTS inicial")
        self.assertTrue(player.inicio.wait(1))
        cerrojo=threading.RLock()
        def ciclo(_):
            with cerrojo:
                alternar_conversacion(app,"caos_off")
                alternar_conversacion(app,"caos_on")
        self.paralelo(range(50), ciclo, workers=8, timeout=10)
        limite=time.monotonic()+3
        while not oido._escuchando_activo and time.monotonic()<limite: time.sleep(.005)
        self.assertTrue(app.escuchando and oido._escuchando_activo)
        voz.detener("fin_prueba")
        limite=time.monotonic()+3
        while player.esta_ocupado() and time.monotonic()<limite: time.sleep(.005)
        self.assertFalse(player.esta_ocupado())
        self.assertGreater(player.cancelados,0)
        self.assertEqual(voz._activos,0)
        app.conversacion=False; dejar_de_escuchar(app)
        limite=time.monotonic()+2
        while oido._escuchando_activo and time.monotonic()<limite: time.sleep(.005)
        self.assertFalse(oido._escuchando_activo)
    def test_03(self):
        from qt_estabilidad_ui import drenar_cola_acotada, actualizar_estado_ui
        cola=queue.Queue(); atendidos=[]; fallos=[]; duraciones=[]
        tipos=("frase","oido","multimodal_situacion","audio_evento","fallo")
        def productor():
            for i in range(300):
                cola.put((tipos[i%len(tipos)],i)); time.sleep(.0002)
        def minimizar():
            for i in range(80):
                actualizar_estado_ui(minimizada=bool(i%2),visible=True)
                time.sleep(.0003)
            actualizar_estado_ui(minimizada=False,visible=True)
        hilos=[threading.Thread(target=productor,daemon=True),threading.Thread(target=minimizar,daemon=True)]
        for h in hilos:h.start()
        while any(h.is_alive() for h in hilos) or not cola.empty():
            t=time.perf_counter()
            try:
                drenar_cola_acotada(cola,lambda t,v:atendidos.append((t,v)),max_eventos=20,presupuesto_ms=5)
            except Exception as exc:fallos.append(exc)
            duraciones.append(time.perf_counter()-t)
        for h in hilos:h.join(1)
        actualizar_estado_ui(minimizada=False,visible=True)
        self.assertFalse(fallos); self.assertEqual(len(atendidos),300)
        self.assertEqual(len({v for _,v in atendidos}),300)
        self.assertLess(max(duraciones),.050)
    def test_04(self):
        import cerebro_enrutador
        from vision_ocr import MotorOCR
        from audio_percepcion_motor import MotorInteligenciaAuditiva
        llamadas=[]
        def fallback(*a,**k):llamadas.append("fallback");return "respaldo"
        with patch.object(cerebro_enrutador,"verificar_pro_disponible",return_value=True), \
             patch.object(cerebro_enrutador,"decidir_carril",return_value=("pro","fallo simulado")), \
             patch.object(cerebro_enrutador,"completar_pro",side_effect=[TimeoutError("timeout"),RuntimeError("429")]) as pro:
            for _ in range(2):
                self.assertEqual(cerebro_enrutador.ejecutar_con_enrutador("hola",[],
                    app=SimpleNamespace(modo_activo="normal"),fallback_fn=fallback),"respaldo")
        self.assertEqual(pro.call_count, 2); self.assertEqual(len(llamadas), 2)
        cam=MotorPercepcionCamara(fuente_frames=lambda:None,politica=PoliticaCapturaCamara(intervalo_reposo_seg=.1))
        try:
            cam.app_cola=self.app.cola; cam.iniciar()
            limite=time.monotonic()+1
            while self.app.cola.empty() and time.monotonic()<limite:time.sleep(.01)
            eventos=[]
            while not self.app.cola.empty():eventos.append(self.app.cola.get_nowait())
            self.assertTrue(any("camara_desconectada" in repr(e) for e in eventos))
        finally:cam.detener()
        audio=MotorInteligenciaAuditiva()
        with self.assertRaises(PermissionError):audio.analizar_buffer_audio([0.0]*80,16000,"microfono")
        ocr=MotorOCR(); ocr.registrar_extractor(lambda *_: (_ for _ in ()).throw(RuntimeError("ocr")))
        self.assertEqual(ocr.extraer("x.png"),( [], ["OCR local fallo"]))
        motor=MotorMM()
        self.assertIsNotNone(motor.ingerir_vision(SimpleNamespace()))
        token=TokenCancelacion(); token.cancelar("caos")
        obs=ObservacionIntegrada("vision","payload","prueba")
        with self.assertRaises(InterruptedError):motor.registrar_observacion(obs,token_cancelacion=token)
        duplicado=ObservacionIntegrada("vision","payload","duplicado")
        recibidos=self.paralelo(range(100),lambda _:motor.registrar_observacion(duplicado,publicar=False))
        self.assertEqual(sum(x is not None for x in recibidos),1)
        motor.ingerir_contexto_windows({"hwnd":8,"pid":900,"ejecutable":"healthy.exe","titulo":"Sana"})
        self.assertEqual(motor.consultar_situacion_actual()["situacion"].contexto_windows["ejecutable"],"healthy.exe")
    def test_05(self):
        def permiso(_):
            return (self.sistema.activar_fuente("camara")["ok"],
                    self.sistema.activar_fuente("microfono")["ok"])
        resultados=self.paralelo(range(50),permiso,workers=8)
        self.assertTrue(all(not cam and not mic for cam,mic in resultados))
        titulos=["contraseña.txt","password","banco","token"]
        lock=threading.Lock(); contador=[0]
        def contexto():
            with lock:
                titulo=titulos[contador[0]%len(titulos)]; contador[0]+=1
            return {"titulo":titulo}
        from PIL import ImageGrab
        with patch("gui_seguridad.escritorio_de_entrada_activo",return_value=True), \
             patch("contexto_windows.obtener_contexto_windows",side_effect=contexto), \
             patch.object(ImageGrab,"grab",side_effect=AssertionError("sensible")) as captura:
            salidas=self.paralelo(range(30),lambda _:self.sistema._captura_temporal_segura())
        captura.assert_not_called()
        self.assertTrue(all("omitida por seguridad" in x for x in salidas))
        class Orq:
            def __init__(self):self.recibidas=[]
            def recibir(self,*args,**kwargs):self.recibidas.append((args,kwargs));return {"ok":True}
        orq=Orq(); motor=MotorMM(orquestador=orq)
        for i in range(20):
            motor.ingerir_vision(SimpleNamespace(descripcion=f"sug {i}",
                observaciones_verificables=["hecho"],id_entrada=str(i),nivel_confianza=.9,
                sugerencia_accion={"accion":"eliminar_archivo","ruta":f"C:\\tmp\\{i}.txt"}))
        self.assertEqual(len(orq.recibidas),20)
        self.assertTrue(all(x[1].get("requiere_ejecucion") is False for x in orq.recibidas))
    def test_06(self):
        from calidad_respuesta import analizar_calidad_texto
        import cerebro_prompt
        app=SimpleNamespace(cola=queue.Queue(),voz=None,iniciativa=None,modo_activo="normal")
        sistema=Sistema(app); sistema._activo=True; app.sistema_multimodal=sistema
        memoria=SimpleNamespace(hechos=[],datos={"resumenes_tematicos":{}},nombre="Silvestra",
            creador="Moisés",proposito="asistente personal")
        ventanas=iter({"hwnd":i+10,"pid":7000+i,"titulo":f"ChatGPT {i}",
            "ejecutable":"ChatGPT.exe","clase":"Chrome_WidgetWin_1"} for i in range(25))
        cerebro=Cerebro(None,memoria,app=app)
        hora="Hoy es martes 3 de marzo de 2026, 12:07 a. m. (medianoche)"
        try:
            with patch("contexto_windows.obtener_contexto_windows",return_value=None), \
                 patch.object(sistema,"_enumerar_ventana_externa",side_effect=lambda:next(ventanas)) as zorder, \
                 patch.object(cerebro_prompt,"obtener_hora_local",return_value=hora):
                for _ in range(25):
                    prompt=cerebro.instrucciones("¿Qué aplicación está abierta?")
                    self.assertIn('Aplicación activa en Windows: ChatGPT.exe | Ventana: "ChatGPT',prompt)
                    self.assertIn(hora,prompt)
                    self.assertIn("Distingue hechos de hipótesis",prompt)
                    self.assertIn("evidencia observada",prompt)
                    self.assertTrue(analizar_calidad_texto("La ventana de ChatGPT está abierta.",
                        contexto_windows=[{"role":"system","content":prompt}])[0])
            self.assertEqual(zorder.call_count,25)
        finally:sistema.detener()

if __name__ == "__main__":
    unittest.main()
