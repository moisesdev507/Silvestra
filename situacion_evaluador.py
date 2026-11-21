"""Evaluadores extensibles y estimación conservadora de incertidumbre."""
from __future__ import annotations
from situacion_interpretacion_modelo import (InterpretacionSituacion,
    NivelIncertidumbre, confianza_valida)


class EvaluadorPatronSituacion:
    nombre = "base"
    prioridad = 50
    def evaluar(self, observaciones, correlaciones, situacion_integrada=None):
        raise NotImplementedError


class RegistroEvaluadoresSituacion:
    def __init__(self): self._evaluadores=[]
    def registrar(self,evaluador):
        if not callable(getattr(evaluador,"evaluar",None)): raise TypeError("Evaluador invalido")
        self._evaluadores.append(evaluador); return evaluador
    def listar(self): return tuple(self._evaluadores)


class EvaluadorPatronBase(EvaluadorPatronSituacion):
    categoria="informacion_insuficiente"
    etiquetas=()
    def evaluar(self, observaciones, correlaciones, situacion_integrada=None):
        mods={o.modalidad for o in observaciones}
        if situacion_integrada: mods.update(situacion_integrada.modalidades_activas)
        textos=" ".join((o.tipo_evento+" "+o.resumen).lower() for o in observaciones)
        if situacion_integrada: textos += " " + situacion_integrada.resumen_consolidado.lower()
        sem={t for o in observaciones for t in o.etiquetas_semanticas}
        relaciones=[c.hipotesis_correlacion for c in correlaciones]
        if self.etiquetas and not any(t in textos or t in sem for t in self.etiquetas): return None
        if self.categoria=="informacion_insuficiente" and (len(mods)>1 or relaciones): return None
        return {"categoria":self.categoria,"relaciones":relaciones,
            "hipotesis":([f"Podría tratarse de {self.categoria}; requiere más evidencia."] if self.categoria!="informacion_insuficiente" else []),
            "insuficiente":self.categoria=="informacion_insuficiente"}


class EvaluadorIncidenciaInformatica(EvaluadorPatronBase):
    nombre="incidencia_informatica"; categoria="incidencia_informatica"
    prioridad=70
    etiquetas=("error","fallo","incidencia")
class EvaluadorAlertaAmbiental(EvaluadorPatronBase):
    nombre="alerta_ambiental"; categoria="alerta_ambiental"
    prioridad=60
    etiquetas=("alarma","sirena","timbre","alerta")
class EvaluadorTransicionActividad(EvaluadorPatronBase):
    nombre="transicion_actividad"; categoria="transicion_actividad"
    prioridad=50
    etiquetas=("cambio","transicion","mensaje","actividad")
class EvaluadorAnomaliaMultimodal(EvaluadorPatronBase):
    nombre="anomalia_multimodal"; categoria="anomalia_multimodal"
    prioridad=80
    def evaluar(self, observaciones, correlaciones, situacion_integrada=None):
        modalidades={o.modalidad for o in observaciones}
        if situacion_integrada: modalidades.update(situacion_integrada.modalidades_activas)
        repetidos=max((sum(o.tipo_evento==x.tipo_evento for x in observaciones) for o in observaciones),default=0)
        rafaga=repetidos>=3 or (len(observaciones)>=5 and len(modalidades)>=3)
        if not rafaga or len(modalidades)<2: return None
        return {"categoria":self.categoria,"relaciones":[c.hipotesis_correlacion for c in correlaciones],
                "hipotesis":["La combinación o frecuencia merece revisión; no confirma una anomalía."],"insuficiente":False}
class EvaluadorInformacionInsuficiente(EvaluadorPatronBase):
    nombre="informacion_insuficiente"; categoria="informacion_insuficiente"
    prioridad=0


class CalculadorIncertidumbre:
    def calcular(self,observaciones,correlaciones,insuficiente=False,modalidades=None,contexto=None):
        confs=[confianza_valida(o.nivel_confianza) for o in observaciones]
        confs=[x for x in confs if x is not None]
        confianza=(sum(confs)/len(confs)) if confs else None
        mods=len(set(modalidades or ()) | {o.modalidad for o in observaciones})
        importancia=max(({"critica":1,"alta":.8,"media":.55,"baja":.3,"irrelevante":0}.get(o.relevancia,.2) for o in observaciones),default=0)
        tiempos=[o.timestamp for o in observaciones]
        coherencia=max(0.0,1.0-(max(tiempos)-min(tiempos))/30.0) if len(tiempos)>1 else 0.0
        hay_contexto=bool(contexto) or any(bool(o.contexto_asociado) for o in observaciones)
        riesgo=min(1.0,max(0.0,.72-importancia*.12-min(1,mods/3)*.2-coherencia*.12-float(hay_contexto)*.1+float(not confs)*.08))
        if insuficiente or (not observaciones and mods<2): nivel=NivelIncertidumbre.insuficiente
        elif confianza is None: nivel=NivelIncertidumbre.alta
        elif riesgo<.15 and mods>=2: nivel=NivelIncertidumbre.baja
        elif riesgo<.4: nivel=NivelIncertidumbre.media
        else: nivel=NivelIncertidumbre.alta
        return confianza,nivel,riesgo
