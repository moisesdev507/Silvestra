"""Pruebas deterministas para inteligencia auditiva; sin microfono real."""
import os
import tempfile
import unittest
import wave
import numpy as np
from audio_evento_modelo import (CategoriaSonido, PoliticaPercepcionAuditiva,
    ClasificacionAcustica, EventoAcustico)
from audio_clasificador import (ClasificadorAcusticoEspectral,
    ClasificadorAudioRemoto, DetectorEcoSilvestra)
from audio_contexto_temporal import ContextoAcusticoTemporal
from audio_percepcion_motor import MotorInteligenciaAuditiva, registrar_procesador_audio
from percepcion_adaptadores import RegistroAdaptadoresPercepcion
from archivos_seguridad import ConfiguracionSandboxArchivos


SR = 16000

def tono(freq, dur=.5, amp=.35):
    t=np.arange(int(SR*dur))/SR
    return (amp*np.sin(2*np.pi*freq*t)).astype(np.float32)

def wavfile(path, pcm, sr=SR):
    data=np.clip(pcm*32767,-32768,32767).astype(np.int16)
    with wave.open(path,"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes(data.tobytes())


class TestInteligenciaAuditiva(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cl=ClasificadorAcusticoEspectral()
        self.motor=MotorInteligenciaAuditiva(clasificador=self.cl)

    def test_01_sonidos_ambientales(self):
        t=np.arange(SR//2)/SR
        casos=((tono(2800),"alarma"),
            (.4*np.sin(2*np.pi*440*t)+.3*np.sin(2*np.pi*660*t),"timbre"),
            (np.tile(np.r_[np.ones(100)*.5,np.zeros(700)],10),"golpes"),
            (.3*np.sin(2*np.pi*(300+1200*t)*t),"sirena"),
            (np.random.default_rng(2).normal(0,.05,len(t)),"ruido_ambiental"))
        for signal, expected in casos:
            self.assertEqual(self.cl.clasificar(signal,SR,0).categoria.value,expected)
    def test_02_diferencia_voz_no_voz(self):
        v=self.cl.clasificar(tono(440),SR,1.0); n=self.cl.clasificar(tono(1000),SR,0)
        self.assertTrue(v.es_voz); self.assertFalse(n.es_voz)
    def test_03_confianza_valida_o_none(self):
        self.assertTrue(0<=self.cl.clasificar(tono(500),SR).confianza<=1)
        remote=ClasificadorAudioRemoto(type("P",(),{"clasificar":lambda *a,**k:{"categoria":"alarma","confianza":"x"}})(),True)
        self.assertIsNone(remote.clasificar([],SR).confianza)
    def test_04_ruido_sin_alerta(self):
        e=self.motor.analizar_buffer_audio(np.zeros(SR,dtype=np.float32),SR)
        self.assertFalse(e.clasificacion.es_relevante)
    def test_05_repeticiones_temporales(self):
        ctx=ContextoAcusticoTemporal()
        for _ in range(3):
            e=EventoAcustico(clasificacion=ClasificacionAcustica(CategoriaSonido.golpes,"",.8,False,True,"test"))
            ctx.agregar(e)
        self.assertEqual(ctx.eventos[-1]["categoria"],"golpes")
    def test_06_supresion_eco(self):
        m=MotorInteligenciaAuditiva(clasificador=self.cl,voz=type("V",(),{"ocupada":lambda s:True})())
        self.assertEqual(m.analizar_buffer_audio(tono(500),SR).clasificacion.categoria,CategoriaSonido.eco_silvestra)
    def test_07_respuesta_natural(self):
        m=self.motor.analizar_buffer_audio(tono(800),SR)
        r=self.motor.temporal.consultar_contexto_auditivo("que paso")
        self.assertIn("Se detectó",r["respuesta"])
    def test_08_contexto_windows(self):
        e=self.motor.analizar_buffer_audio(tono(500),SR,contexto_win={"app":"Editor"})
        self.assertEqual(e.contexto_windows_asociado["app"],"Editor")
    def test_09_permisos_privacidad(self):
        p=PoliticaPercepcionAuditiva()
        self.assertFalse(p.permiso_microfono or p.permitir_grabacion_continua or p.permitir_envio_externo)
        with self.assertRaises(PermissionError): self.motor.analizar_buffer_audio(tono(200),SR,"microfono")
        with self.assertRaises(PermissionError): ClasificadorAudioRemoto(lambda:None).clasificar([],SR)
    def test_10_sin_ejecutores(self):
        for f in ("audio_evento_modelo.py","audio_clasificador.py","audio_contexto_temporal.py","audio_percepcion_motor.py"):
            with open(f,encoding="utf8") as archivo: src=archivo.read()
            for blocked in ("archivos_operaciones","procesos_operaciones","gui_interaccion"):
                self.assertNotIn(blocked,src)
        with open("audio_percepcion_motor.py",encoding="utf8") as archivo: self.assertIn("requiere_ejecucion=False",archivo.read())
    def test_11_ciclo_y_archivo_corrupto(self):
        self.motor.pausar()
        with self.assertRaises(RuntimeError): self.motor.analizar_buffer_audio(tono(200),SR)
        self.motor.reanudar()
        p=os.path.join(self.tmp.name,"bad.wav")
        with open(p,"wb") as archivo: archivo.write(b"bad")
        m=MotorInteligenciaAuditiva(clasificador=self.cl,sandbox=ConfiguracionSandboxArchivos([self.tmp.name]))
        with self.assertRaises(Exception): m.analizar_archivo_audio(p)
    def test_12_concurrencia_cancelacion(self):
        import threading
        self.assertTrue(self.motor._lock.acquire(False)); self.motor._lock.release()
        tok=threading.Event(); tok.set()
        with self.assertRaises(InterruptedError): self.motor.analizar_buffer_audio(tono(200),SR,token_cancelacion=tok)
    def test_13_historial_solo_metadatos(self):
        e=self.motor.analizar_buffer_audio(tono(300),SR)
        item=self.motor.temporal.eventos[-1]
        self.assertNotIn("pcm",repr(item).lower()); self.assertNotIn("wav",repr(item).lower())
        self.assertFalse(any(isinstance(v,np.ndarray) for v in item.values()))
    def test_14_integracion_registro(self):
        reg=RegistroAdaptadoresPercepcion(); p=registrar_procesador_audio(reg,self.motor)
        self.assertIs(reg.obtener("audio"),p)
    def test_15_consulta_no_verbal(self):
        self.motor.analizar_buffer_audio(tono(900),SR)
        self.assertIn("voz humana",self.motor.temporal.consultar_contexto_auditivo("voz")["respuesta"])
    def test_16_categoria_enumerada(self):
        self.assertEqual(len(CategoriaSonido),11)
    def test_17_tamanos_bajo_limite(self):
        for f in ("audio_evento_modelo.py","audio_clasificador.py","audio_contexto_temporal.py","audio_percepcion_motor.py"):
            self.assertLessEqual(os.path.getsize(f),15360)
    def test_18_detector_vad_fallback(self):
        self.assertIsInstance(self.cl.clasificar(tono(250),SR),ClasificacionAcustica)


if __name__=="__main__": unittest.main()
