"""Motor auditivo desacoplado con permisos, sandbox y puentes pasivos."""
from __future__ import annotations
import os
import threading
import time
import wave
import numpy as np
from audio_evento_modelo import *
from audio_clasificador import ClasificadorAcusticoEspectral, DetectorEcoSilvestra
from audio_contexto_temporal import ContextoAcusticoTemporal
from percepcion_adaptadores import ProcesadorModalidad, AdaptadorAudio
from percepcion_modelo import EventoPerceptivo, ReferenciaContenido


class MotorInteligenciaAuditiva:
    def __init__(self, politica=None, clasificador=None, sandbox=None, voz=None,
                 contexto_motor=None, iniciativa_contextual=None, cerebro=None,
                 app_cola=None, orquestador=None, motor_percepcion=None, app=None,
                 timeout_seg=8.0):
        self._lock = threading.RLock()
        self._ocupado = threading.Lock()
        self.politica = politica or PoliticaPercepcionAuditiva()
        self.clasificador = clasificador or ClasificadorAcusticoEspectral()
        self.eco = DetectorEcoSilvestra(voz)
        self.sandbox = sandbox
        self.contexto_motor, self.iniciativa = contexto_motor, iniciativa_contextual
        self.cerebro, self.app_cola = cerebro, app_cola
        self.orquestador, self.motor_percepcion = orquestador, motor_percepcion
        self.app = app
        self.temporal = ContextoAcusticoTemporal(self.politica.max_eventos_historial,
            self.politica.ttl_historial_seg)
        self.timeout_seg = max(.1, float(timeout_seg))
        self.activo, self.pausado = True, False

    def activar(self): self.activo = True; self.pausado = False
    def desactivar(self): self.activo = False
    def pausar(self): self.pausado = True
    def reanudar(self): self.pausado = False

    def analizar_buffer_audio(self, muestras, sample_rate, fuente="buffer", token_cancelacion=None, contexto_win=None):
        if not self.politica.habilitada or not self.activo or self.pausado:
            raise RuntimeError("Percepcion auditiva inactiva")
        if fuente in ("microfono", "captura_vivo", "live") and not self.politica.permiso_microfono:
            raise PermissionError("Permiso de microfono requerido")
        if not self._ocupado.acquire(False): raise RuntimeError("Analisis auditivo ya activo")
        arr = None
        try:
            inicio = time.monotonic()
            arr = np.asarray(muestras, dtype=np.float32).reshape(-1)
            if not len(arr) or sample_rate <= 0: raise ValueError("Audio vacio o sample_rate invalido")
            if len(arr)/sample_rate > self.politica.duracion_max_seg: raise ValueError("Duracion excedida")
            cancelado = False
            if token_cancelacion is not None:
                marca = getattr(token_cancelacion, "esta_cancelado", None)
                cancelado = bool(marca() if callable(marca) else marca)
                if hasattr(token_cancelacion, "is_set"):
                    cancelado = cancelado or token_cancelacion.is_set()
            if cancelado: raise InterruptedError("Analisis cancelado")
            rms = float(np.sqrt(np.mean(arr*arr)))
            clas = self.clasificador.clasificar(arr, sample_rate)
            if time.monotonic()-inicio > self.timeout_seg: raise TimeoutError("Timeout de audio")
            if self.eco.hablando() and self.politica.ignorar_eco_propio:
                clas = ClasificacionAcustica(CategoriaSonido.eco_silvestra, "locucion_activa", .98, False, False, "estado_voz")
            nivel = {"alarma":NivelRelevanciaSonido.critica,"sirena":NivelRelevanciaSonido.critica,
                "timbre":NivelRelevanciaSonido.alta,"golpes":NivelRelevanciaSonido.alta,
                "aplausos":NivelRelevanciaSonido.media,"ladridos":NivelRelevanciaSonido.media,
                "voz_humana":NivelRelevanciaSonido.media}.get(clas.categoria.value, NivelRelevanciaSonido.irrelevante)
            evento = EventoAcustico(fuente=fuente,duracion_seg=len(arr)/sample_rate,
                energia_rms=rms,ratio_voz_vad=1.0 if clas.es_voz else 0.0,
                clasificacion=clas,relevancia=nivel,
                observaciones_verificables=[f"RMS={rms:.4f}", f"categoria={clas.categoria.value}"],
                interpretaciones_inciertas=["Clasificacion heuristica espectral; requiere confirmacion"])
            contexto = contexto_win
            if contexto is None:
                try:
                    from contexto_windows import obtener_contexto_windows
                    contexto = obtener_contexto_windows()
                except Exception: contexto = {}
            evento = self.temporal.agregar(evento, contexto)
            if evento.clasificacion.es_relevante and (evento.clasificacion.confianza or 0) >= self.politica.umbral_confianza_relevante:
                self._publicar(evento)
            return evento
        finally:
            if arr is not None: del arr
            self._ocupado.release()

    def analizar_archivo_audio(self, ruta, pregunta=None, contexto_win=None, token_cancelacion=None):
        if self.sandbox is None: raise PermissionError("Se requiere sandbox autorizado para leer audio")
        ruta = self.sandbox.validar_existente(ruta)
        if not os.path.isfile(ruta) or os.path.getsize(ruta) > self.politica.max_bytes_audio: raise ValueError("Archivo de audio no permitido")
        raw = pcm = None
        try:
            with wave.open(ruta,"rb") as f:
                if f.getnchannels()!=1 or f.getsampwidth() not in (1,2,4): raise ValueError("WAV mono PCM requerido")
                sr,n,width=f.getframerate(),f.getnframes(),f.getsampwidth()
                if n/max(1,sr)>self.politica.duracion_max_seg: raise ValueError("Duracion excedida")
                raw=f.readframes(n)
            dtype={1:np.uint8,2:np.int16,4:np.int32}[width]
            pcm=np.frombuffer(raw,dtype=dtype).astype(np.float32)
            pcm=(pcm-128)/128 if width==1 else pcm/(2**(8*width-1))
            ev=self.analizar_buffer_audio(pcm,sr,"archivo",token_cancelacion,contexto_win)
            ev.transcripcion_breve=""
            self.temporal._analisis[ev.id_evento]=self.temporal.eventos[-1]
            return {"evento":ev.a_dict(),"respuesta":self.temporal.consultar_contexto_auditivo(pregunta or "",ev.id_evento)["respuesta"]}
        finally:
            raw = None
            if pcm is not None: del pcm

    def _publicar(self, ev):
        resumen=(f"Audio detectado: {ev.clasificacion.categoria.value}; RMS {ev.energia_rms:.3f}; confianza {ev.clasificacion.confianza}")[:500]
        if self.contexto_motor:
            try: self.contexto_motor.confirmar_contexto("percepcion_auditiva",ev.a_dict(),origen="audio",ttl_seg=30)
            except Exception: pass
        if self.iniciativa:
            try: self.iniciativa.evaluar_oportunidad(app=self.app,contexto={"tema":"audio","detalle":resumen})
            except Exception: pass
        if self.cerebro:
            try: self.cerebro.historial.append({"role":"system","content":"[AUDIO] "+resumen})
            except Exception: pass
        if self.app_cola is not None:
            try: self.app_cola.put_nowait(("audio_evento",{"evento":ev.a_dict(),"resumen":resumen}))
            except Exception: pass
        if self.orquestador and ev.sugerencia_accion:
            try: self.orquestador.recibir(str(ev.sugerencia_accion),origen="audio",requiere_ejecucion=False,modo="restringido")
            except Exception: pass


class ProcesadorAudicionMultimodal(ProcesadorModalidad):
    def __init__(self,motor): self.motor=motor
    def procesar(self,evento,token_cancelacion=None):
        ruta=getattr(getattr(evento,"referencia_contenido",None),"ruta",None)
        if not ruta: return {"error":"sin_ruta_audio"}
        return self.motor.analizar_archivo_audio(ruta,token_cancelacion=token_cancelacion)


def registrar_procesador_audio(registro,motor):
    procesador=ProcesadorAudicionMultimodal(motor)
    registro.registrar("audio",procesador)
    return procesador
