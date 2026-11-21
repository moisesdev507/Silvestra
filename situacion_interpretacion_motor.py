"""Interpreta patrones multimodales sin ejecutar acciones."""
from __future__ import annotations
import threading
import time
from multimodal_integracion_modelo import SituacionIntegrada
from situacion_interpretacion_modelo import (InterpretacionSituacion,
    PoliticaInterpretacionSituaciones, EstadoSituacion, NivelIncertidumbre,
    EvidenciaSituacion)
from situacion_evaluador import (RegistroEvaluadoresSituacion,
    CalculadorIncertidumbre, EvaluadorIncidenciaInformatica,
    EvaluadorAlertaAmbiental, EvaluadorTransicionActividad,
    EvaluadorAnomaliaMultimodal, EvaluadorInformacionInsuficiente)
from situacion_memoria_temporal import GestorMemoriaSituaciones


class MotorInterpretacionSituaciones:
    def __init__(self,politica=None,evaluadores=None,memoria=None,cerebro=None,
        contexto_motor=None,iniciativa_contextual=None,app=None,app_cola=None,orquestador=None):
        self._lock=threading.RLock();self.politica=politica or PoliticaInterpretacionSituaciones()
        self.registro=RegistroEvaluadoresSituacion();self.calculador=CalculadorIncertidumbre()
        self.memoria=memoria or GestorMemoriaSituaciones(self.politica)
        self.cerebro,self.contexto_motor=cerebro,contexto_motor
        self.iniciativa,self.app,self.app_cola=iniciativa_contextual,app,app_cola
        self.orquestador=orquestador
        for e in evaluadores or (EvaluadorIncidenciaInformatica(),EvaluadorAlertaAmbiental(),
            EvaluadorTransicionActividad(),EvaluadorAnomaliaMultimodal(),EvaluadorInformacionInsuficiente()):self.registrar_evaluador(e)

    def registrar_evaluador(self,evaluador):return self.registro.registrar(evaluador)

    @staticmethod
    def _cancelar(token):
        if token is None:return False
        flag=getattr(token,"esta_cancelado",None)
        return bool(flag() if callable(flag) else flag) or bool(getattr(token,"is_set",lambda:False)())

    def interpretar(self,entrada,correlaciones=None,token_cancelacion=None,modalidades_con_fallo=None):
        if self._cancelar(token_cancelacion):raise InterruptedError("Interpretacion cancelada")
        si=entrada if isinstance(entrada,SituacionIntegrada) else None
        obs=[] if si else list(entrada or [])
        cors=list(correlaciones if correlaciones is not None else (si.correlaciones_probables if si else []))
        if si:
            for c in si.correlaciones_probables:
                cors.extend(x for x in [c] if x not in cors)
        evidencias=[];hechos=[];conclusiones=[];mods=[]
        if si:
            hechos.extend(si.hechos_confirmados)
            conclusiones.extend(si.hechos_confirmados)
            mods.extend(si.modalidades_activas)
        for o in obs:
            if self._cancelar(token_cancelacion):raise InterruptedError("Interpretacion cancelada")
            hechos.extend(o.datos_estructurados.get("observaciones",[]) if isinstance(o.datos_estructurados,dict) else [])
            epistemico=o.datos_estructurados.get("nivel_epistemico") if isinstance(o.datos_estructurados,dict) else None
            if epistemico=="confirmado":conclusiones.append(o.resumen)
            if o.modalidad=="audio":
                hechos.append("Se recibió una observación acústica; su etiqueta requiere interpretación.")
            elif epistemico!="probable": hechos.append(o.resumen)
            mods.append(o.modalidad)
            descr="Se recibió una observación acústica." if o.modalidad=="audio" else o.resumen
            evidencias.append(EvidenciaSituacion(o.id_observacion,o.modalidad,o.timestamp,descr,o.nivel_confianza,o.relevancia))
        evaluaciones=[]
        for e in self.registro.listar():
            if self._cancelar(token_cancelacion):raise InterruptedError("Interpretacion cancelada")
            try:
                r=e.evaluar(obs,cors,si)
                if r:evaluaciones.append((int(getattr(e,"prioridad",50)),r))
            except Exception:continue
        candidatas=[par for par in evaluaciones if not par[1].get("insuficiente")]
        resultado=max(candidatas,key=lambda par:par[0])[1] if candidatas else None
        if resultado is None:
            resultado=evaluaciones[0][1] if evaluaciones else {"categoria":"informacion_insuficiente","relaciones":[],"hipotesis":[],"insuficiente":True}
        relaciones=list(dict.fromkeys([c.hipotesis_correlacion for c in cors if getattr(c,"es_probable",True)]+resultado.get("relaciones",[])))
        insuf=resultado.get("insuficiente",False) or (len(set(mods))<2 and not relaciones)
        ctx=dict(si.contexto_windows) if si else (dict(obs[0].contexto_asociado) if obs else {})
        if si and not ctx.get("aplicacion"):
            ctx["aplicacion"]=ctx.get("ejecutable") or ctx.get("titulo") or ""
        conf,nivel,riesgo=self.calculador.calcular(obs,cors,insuf,mods,ctx)
        lagunas=[]
        if insuf:lagunas.extend(("Falta evidencia de otra modalidad o contexto asociado.","La relación causal no está verificada."))
        if conf is None:lagunas.append("Las fuentes no aportaron confianza numérica válida.")
        if not cors:lagunas.append("No hay relaciones multimodales respaldadas.")
        rel=max((o.relevancia for o in obs),key=lambda x:{"critica":5,"alta":4,"media":3,"baja":2,"irrelevante":1}.get(x,0),default="baja")
        resumen=(si.resumen_consolidado if si else " | ".join(dict.fromkeys(hechos[-6:])))[:self.politica.max_resumen_cerebro_chars]
        interp=InterpretacionSituacion(categoria_situacion=resultado["categoria"],inicio_ts=min((o.timestamp for o in obs),default=time.time()),
            ultima_actualizacion_ts=max((o.timestamp for o in obs),default=time.time()),relevancia=rel,
            confianza_interpretacion=conf,nivel_incertidumbre=nivel,riesgo_falso_positivo=riesgo,
            hechos_observados=list(dict.fromkeys(hechos)),relaciones_probables=relaciones,
            hipotesis=resultado.get("hipotesis",[]),conclusiones_verificadas=list(dict.fromkeys(conclusiones)),
            lagunas_informacion=lagunas,secuencia_temporal=[f"{o.timestamp:.3f} [{o.modalidad}] {o.resumen}" for o in sorted(obs,key=lambda x:x.timestamp)],
            evidencias=evidencias,modalidades_involucradas=list(dict.fromkeys(mods)),
            modalidades_con_fallo=list(modalidades_con_fallo or (si.modalidades_con_fallo if si else [])),
            contexto_asociado=ctx,resumen_interpretado=resumen,
            sugerencia_pasiva=si.sugerencia_accion if si else None)
        with self._lock:interp=self.memoria.actualizar_o_agregar(interp)
        self._publicar(interp)
        return interp

    def interpretar_lote(self,observaciones,correlaciones=None,**kwargs):
        return self.interpretar(observaciones,correlaciones,**kwargs)

    def resolver(self,id_situacion):return self.memoria.resolver(id_situacion)

    def consultar_interpretacion_actual(self,pregunta=""):
        activas=self.memoria.listar_activas()
        if not activas:return {"respuesta":"No hay suficiente información para interpretar una situación.","situaciones":[]}
        s=activas[-1]
        respuesta=(s.resumen_interpretado or s.categoria_situacion)+". Hechos: "+"; ".join(s.hechos_observados[:4])
        if s.relaciones_probables:respuesta+=". Relaciones probables: "+"; ".join(s.relaciones_probables[:2])
        if s.hipotesis:respuesta+=". Hipótesis: "+"; ".join(s.hipotesis[:2])
        if s.lagunas_informacion:respuesta+=". Falta: "+"; ".join(s.lagunas_informacion[:2])
        return {"respuesta":respuesta[:self.politica.max_resumen_cerebro_chars],"situaciones":list(activas)}

    def _publicar(self,s):
        resumen=(s.resumen_interpretado or s.categoria_situacion)[:self.politica.max_resumen_cerebro_chars]
        if self.cerebro is not None:
            try:self.cerebro.historial.append({"role":"system","content":"[SITUACION] "+resumen[:535]})
            except Exception:pass
        if self.contexto_motor is not None and s.conclusiones_verificadas:
            try:self.contexto_motor.confirmar_contexto("interpretacion_situacion",{"hechos":s.conclusiones_verificadas},origen="situacion",ttl_seg=30)
            except Exception:pass
        if self.iniciativa is not None and self.app is not None and s.relevancia in ("critica","alta"):
            try:self.iniciativa.evaluar_oportunidad(app=self.app,contexto={"tema":s.categoria_situacion,"detalle":resumen})
            except Exception:pass
        if self.app_cola is not None and s.relevancia in ("critica","alta"):
            try:self.app_cola.put_nowait(("multimodal_situacion",resumen[:550]))
            except Exception:pass
        if self.orquestador is not None and s.sugerencia_pasiva:
            try:self.orquestador.recibir(str(s.sugerencia_pasiva),origen="situacion",requiere_ejecucion=False,modo="restringido")
            except Exception:pass
