"""Memoria temporal acotada de situaciones activas."""
from __future__ import annotations
import threading
import time
from situacion_interpretacion_modelo import (InterpretacionSituacion,
    EstadoSituacion, EvidenciaSituacion, PoliticaInterpretacionSituaciones,
    sanitizar_dato)


class GestorMemoriaSituaciones:
    def __init__(self,politica=None):
        self.politica=politica or PoliticaInterpretacionSituaciones()
        self._lock=threading.RLock(); self._situaciones=[]

    def purgar(self,ahora=None):
        ahora=time.time() if ahora is None else float(ahora)
        with self._lock:
            for s in self._situaciones:
                if s.estado in (EstadoSituacion.iniciada,EstadoSituacion.actualizada) and ahora-s.ultima_actualizacion_ts>self.politica.ttl_situacion_seg:
                    s.estado=EstadoSituacion.expirada; s.cierre_ts=ahora
            self._situaciones=[s for s in self._situaciones if s.estado in (EstadoSituacion.iniciada,EstadoSituacion.actualizada)]

    def _coincide(self,a,b):
        if a.categoria_situacion!=b.categoria_situacion:return False
        if abs(b.ultima_actualizacion_ts-a.ultima_actualizacion_ts)>self.politica.ventana_fusion_actualizacion_seg:return False
        ids={e.id_observacion for e in a.evidencias}
        if ids & {e.id_observacion for e in b.evidencias}:return True
        ca,cb=a.contexto_asociado,b.contexto_asociado
        return any(ca.get(k) and cb.get(k) and str(ca[k]).casefold()==str(cb[k]).casefold()
                   for k in ("aplicacion","hwnd"))

    def actualizar_o_agregar(self,situacion):
        self.purgar()
        with self._lock:
            existente=next((s for s in reversed(self._situaciones) if self._coincide(s,situacion)),None)
            if existente:
                existentes={e.id_observacion for e in existente.evidencias}
                nuevas=[e for e in situacion.evidencias if e.id_observacion not in existentes]
                existente.evidencias.extend(nuevas)
                existente.secuencia_temporal.extend(x for x in situacion.secuencia_temporal if x not in existente.secuencia_temporal)
                existente.hechos_observados.extend(x for x in situacion.hechos_observados if x not in existente.hechos_observados)
                existente.relaciones_probables.extend(x for x in situacion.relaciones_probables if x not in existente.relaciones_probables)
                existente.hipotesis.extend(x for x in situacion.hipotesis if x not in existente.hipotesis)
                existente.conclusiones_verificadas.extend(x for x in situacion.conclusiones_verificadas if x not in existente.conclusiones_verificadas)
                existente.modalidades_involucradas=list(dict.fromkeys(existente.modalidades_involucradas+situacion.modalidades_involucradas))
                existente.modalidades_con_fallo=list(dict.fromkeys(existente.modalidades_con_fallo+situacion.modalidades_con_fallo))
                existente.contexto_asociado.update(situacion.contexto_asociado)
                existente.ultima_actualizacion_ts=max(existente.ultima_actualizacion_ts,situacion.ultima_actualizacion_ts)
                orden={"irrelevante":0,"baja":1,"media":2,"alta":3,"critica":4}
                if orden.get(situacion.relevancia,0)>orden.get(existente.relevancia,0):existente.relevancia=situacion.relevancia
                existente.estado=EstadoSituacion.actualizada
                existente.resumen_interpretado=situacion.resumen_interpretado or existente.resumen_interpretado
                resultado=existente
            else:
                resultado=situacion
                self._situaciones.append(resultado)
            while len(self._situaciones)>self.politica.max_situaciones_activas:
                vieja=self._situaciones.pop(0);vieja.estado=EstadoSituacion.expirada
                vieja.cierre_ts=situacion.ultima_actualizacion_ts
            return resultado

    def resolver(self,id_situacion,cierre_ts=None):
        with self._lock:
            for s in self._situaciones:
                if s.id_situacion==id_situacion:
                    s.estado=EstadoSituacion.resuelta;s.cierre_ts=cierre_ts or time.time();return True
        return False

    def listar_activas(self):
        self.purgar()
        with self._lock:return tuple(self._situaciones)
