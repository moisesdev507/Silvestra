"""Correlaciones temporales conservadoras y extensibles."""
from __future__ import annotations
import math
from multimodal_integracion_modelo import (CorrelacionMultimodal,
    ObservacionIntegrada, PoliticaIntegracionMultimodal)


class CorrelacionadorMultimodal:
    def __init__(self, politica=None, afinidad_semantica=None):
        self.politica = politica or PoliticaIntegracionMultimodal()
        self.afinidad_semantica = afinidad_semantica

    @staticmethod
    def _contexto(a, b):
        ca, cb = a.contexto_asociado, b.contexto_asociado
        claves = ("aplicacion", "hwnd")
        return any(ca.get(k) and cb.get(k) and
                   str(ca[k]).casefold() == str(cb[k]).casefold() for k in claves)

    def _semantica(self, a, b):
        if self.afinidad_semantica:
            try:
                return min(1.0, max(0.0, float(self.afinidad_semantica(a, b))))
            except Exception:
                return 0.0
        ta, tb = set(a.etiquetas_semanticas), set(b.etiquetas_semanticas)
        if not ta or not tb:
            return 0.0
        comun = ta & tb
        union = ta | tb
        return len(comun) / len(union) if comun else 0.0

    @staticmethod
    def _relevancia(obs):
        return {"critica": 1.0, "alta": .8, "media": .55,
                "baja": .3, "irrelevante": 0.0}.get(obs.relevancia, .2)

    def correlacionar(self, observaciones):
        vigentes = sorted(observaciones, key=lambda o: o.timestamp)
        salida = []
        for i, a in enumerate(vigentes):
            for b in vigentes[i + 1:]:
                delta = b.timestamp - a.timestamp
                if delta > self.politica.ventana_correlacion_seg:
                    break
                if a.modalidad == b.modalidad:
                    continue
                sem = self._semantica(a, b)
                ctx = self._contexto(a, b)
                if sem <= 0 and not ctx:
                    continue
                temporal = 1.0 - delta / max(.001, self.politica.ventana_correlacion_seg)
                rel = (self._relevancia(a) + self._relevancia(b)) / 2
                puntuacion = .35 * temporal + .35 * sem + .2 * float(ctx) + .1 * rel
                if puntuacion < self.politica.umbral_correlacion:
                    continue
                hechos = [f"{o.modalidad}: {o.resumen}" for o in (a, b)]
                hipotesis = ("Las observaciones podrían estar relacionadas por " +
                    ("contexto compartido" if ctx else "afinidad semántica") +
                    " y proximidad temporal; relación no confirmada.")
                confs = [o.nivel_confianza for o in (a, b)]
                confianza = min(confs) if all(c is not None for c in confs) else None
                salida.append(CorrelacionMultimodal(
                    modalidades=(a.modalidad, b.modalidad),
                    ids_observaciones=(a.id_observacion, b.id_observacion),
                    tipo_relacion="temporal_contextual" if ctx else "temporal_semantica",
                    puntuacion_afinidad=min(1.0, puntuacion),
                    confianza_relacion=confianza, hechos_confirmados=hechos,
                    hipotesis_correlacion=hipotesis, es_probable=True))
        return salida
