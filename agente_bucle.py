"""Bucle agéntico: observar, decidir, permisos, actuar, verificar, realimentar."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import agente_herramientas as ah
import agente_observacion as ao
import agente_permisos as ap
import agente_traza as at

MAX_PASOS_DEFAULT = 3
MAX_PASOS = 5


@dataclass
class ResultadoBucle:
    exito: bool
    respuesta: str
    pasos: int
    motivo: str
    cancelado: bool = False
    traza: list = field(default_factory=list)


class BucleAgente:
    """Ciclo acotado y cancelable con recuperación informada ante fallos."""

    def __init__(self, catalogo=None, compuerta=None, verificador=None,
                 max_pasos=MAX_PASOS_DEFAULT, ejecutar=None, traza=None):
        self.catalogo = catalogo if catalogo is not None else ah.catalogo()
        self.compuerta = compuerta if compuerta is not None else ap.CompuertaPermisos()
        self.verificador = verificador
        try:
            self.max_pasos = min(MAX_PASOS, max(1, int(max_pasos)))
        except (TypeError, ValueError):
            self.max_pasos = MAX_PASOS_DEFAULT
        self.ejecutar_fn = ejecutar if callable(ejecutar) else None
        self._traza = traza

    def _cancelado(self, cancelacion, traza):
        externo = bool(cancelacion is not None and
                       getattr(cancelacion, "is_set", lambda: False)())
        return externo or traza.cancelada

    def _herramienta(self, nombre):
        if hasattr(self.catalogo, "obtener"):
            return self.catalogo.obtener(nombre)
        for herramienta in self.catalogo:
            if getattr(herramienta, "nombre", "") == nombre:
                return herramienta
        return None

    def _decidir(self, objetivo, observaciones, paso):
        if observaciones and not observaciones[-1].exito:
            ultima = observaciones[-1]
            return {
                "herramienta": ultima.herramienta,
                "argumentos": {"texto": f"Corrige esto: {ultima.error}"},
                "intencion": "corregir_error",
            }
        relevantes = ah.consultar(objetivo, limite=1, catalogo=self.catalogo)
        if not relevantes:
            return {"final": True, "respuesta": "No tengo una herramienta para eso."}
        herramienta = relevantes[0]
        argumentos = {"texto": objetivo} if herramienta.parametros else {}
        return {
            "herramienta": herramienta.nombre,
            "argumentos": argumentos,
            "intencion": objetivo,
        }

    def _actuar(self, nombre, argumentos, paso):
        if self.ejecutar_fn is not None:
            return self.ejecutar_fn(nombre, argumentos, paso)
        import acciones

        texto = argumentos.get("texto", argumentos.get("arg"))
        return acciones.ejecutar(nombre, texto)

    def _fin(self, exito, respuesta, pasos, motivo, cancelado, traza):
        return ResultadoBucle(
            exito=bool(exito), respuesta=str(respuesta or ""), pasos=int(pasos),
            motivo=str(motivo), cancelado=bool(cancelado), traza=traza.a_lista(),
        )

    def ejecutar(self, objetivo, decidir=None, cancelacion=None):
        traza = self._traza if self._traza is not None else at.Traza()
        observaciones = []
        for paso in range(1, self.max_pasos + 1):
            if self._cancelado(cancelacion, traza):
                return self._fin(False, "Cancelado por el usuario.", paso - 1,
                                 "cancelado", True, traza)
            try:
                decision = (decidir(objetivo, observaciones, self.catalogo, paso)
                            if callable(decidir)
                            else self._decidir(objetivo, observaciones, paso))
            except Exception as error:
                decision = {"error": str(error)}
            if not isinstance(decision, dict):
                decision = {"final": True, "respuesta": str(decision)}

            if decision.get("error") and not decision.get("herramienta"):
                observaciones.append(ao.Observacion(
                    False, error=str(decision["error"]), herramienta="decision"))
                traza.registrar(paso, intencion="decidir", error=str(decision["error"]))
                continue

            if decision.get("final"):
                return self._fin(True, decision.get("respuesta", "Listo."), paso,
                                 "objetivo_resuelto", False, traza)

            nombre = str(decision.get("herramienta") or "").strip().lower()
            herramienta = self._herramienta(nombre)
            if herramienta is None:
                observaciones.append(ao.Observacion(
                    False, error="herramienta_desconocida", herramienta=nombre))
                traza.registrar(paso, herramienta=nombre, error="herramienta_desconocida")
                continue

            argumentos = decision.get("argumentos") or {}
            if not isinstance(argumentos, dict):
                argumentos = {"texto": argumentos}
            permiso = self.compuerta.evaluar(herramienta, parametros=argumentos)
            if not permiso.permitido:
                traza.registrar(paso, intencion=decision.get("intencion", ""),
                                herramienta=nombre, argumentos=argumentos,
                                error=permiso.motivo)
                return self._fin(False, f"Permiso denegado: {permiso.motivo}", paso,
                                 permiso.motivo, False, traza)

            if self._cancelado(cancelacion, traza):
                return self._fin(False, "Cancelado por el usuario.", paso,
                                 "cancelado", True, traza)

            inicio = time.time()
            try:
                resultado = self._actuar(nombre, argumentos, paso)
            except Exception as error:
                resultado = (False, f"Error al ejecutar: {error}")
            observacion = ao.desde_resultado(
                nombre, resultado, inicio=inicio, verificador=self.verificador)
            observaciones.append(observacion)
            traza.registrar(
                paso,
                intencion=decision.get("intencion", ""),
                herramienta=nombre,
                argumentos=argumentos,
                resultado=observacion.salida or observacion.error,
                verificado=observacion.verificado,
                duracion_ms=observacion.duracion_ms,
                error=observacion.error if not observacion.exito else "",
            )
            if self._cancelado(cancelacion, traza):
                return self._fin(False, "Cancelado por el usuario.", paso,
                                 "cancelado", True, traza)
            if observacion.exito and observacion.verificado:
                return self._fin(True, observacion.salida or "Listo.", paso,
                                 "verificado", False, traza)

        return self._fin(False, "Se alcanzó el límite de pasos.", self.max_pasos,
                         "max_pasos", False, traza)
