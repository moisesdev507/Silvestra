"""Observación sanitizada del modelo."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import verificacion_modelo as vm

MAX_TEXTO = 600


def _limpio(valor, max_len=MAX_TEXTO):
    texto = str(valor or "")
    texto = re.sub(r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTADO]", texto)
    texto = re.sub(r"\b(?:sk|coh|gsk|nvapi|grs)[_-][A-Za-z0-9_\-]{6,}", "[CLAVE REDACTADA]", texto)
    return texto[:max_len]


@dataclass
class Observacion:
    exito: bool
    salida: str = ""
    error: str = ""
    verificado: bool = False
    duracion_ms: int = 0
    herramienta: str = ""
    datos: dict = field(default_factory=dict)

    def a_dict(self):
        return {
            "exito": bool(self.exito),
            "salida": _limpio(self.salida),
            "error": _limpio(self.error),
            "verificado": bool(self.verificado),
            "duracion_ms": int(self.duracion_ms),
            "herramienta": _limpio(self.herramienta, 80),
            "datos": vm.sanitizar_datos(self.datos),
        }

    def formatear(self):
        """Texto para el LLM."""
        lineas = [
            f"HERRAMIENTA: {_limpio(self.herramienta, 80) or 'ninguna'}",
            f"ÉXITO: {'sí' if self.exito else 'no'}",
            f"VERIFICADO: {'sí' if self.verificado else 'no'}",
            f"DURACIÓN_MS: {int(self.duracion_ms)}",
        ]
        if self.salida:
            lineas.append(f"SALIDA: {_limpio(self.salida)}")
        if self.error:
            lineas.append(f"ERROR: {_limpio(self.error)}")
        return "\n".join(lineas)


def verificar(verificador, herramienta, observacion, esperado=None):
    """Valida el resultado."""
    if verificador is None:
        return observacion.exito
    try:
        if callable(verificador):
            resultado = verificador(herramienta, observacion, esperado)
        else:
            from ejecucion_modelo import (
                ESTADO_COMPLETADA, ESTADO_FALLIDA,
                ResultadoEjecucion, SolicitudEjecucion,
            )

            solicitud = SolicitudEjecucion(
                origen="cerebro", herramienta=herramienta,
                parametros=vm.sanitizar_datos(observacion.datos),
            )
            ejecucion = ResultadoEjecucion(
                id_solicitud=solicitud.id_solicitud,
                herramienta=herramienta,
                estado=ESTADO_COMPLETADA if observacion.exito else ESTADO_FALLIDA,
                exito=bool(observacion.exito),
                datos=_limpio(observacion.salida),
                error={"codigo": "AGENTE", "mensaje": _limpio(observacion.error)}
                if observacion.error else None,
                duracion_ms=observacion.duracion_ms,
            )
            resultado = verificador.verificar_resultado(solicitud, ejecucion, esperado)
    except Exception:
        return False
    if isinstance(resultado, bool):
        return resultado
    if isinstance(resultado, dict):
        estado = str(resultado.get("estado", resultado.get("estado_final", ""))).lower()
        return bool(resultado.get("verificado")) or estado in ("verificado", "recuperado")
    estado = str(getattr(resultado, "estado_final", "") or "").lower()
    return bool(getattr(resultado, "verificado", False)) or estado in ("verificado", "recuperado")


def desde_resultado(herramienta, resultado, inicio=None, verificador=None, esperado=None):
    """Normaliza resultados."""
    if isinstance(resultado, Observacion):
        return resultado
    duracion_ms = 0
    if inicio is not None:
        try:
            duracion_ms = int(max(0.0, time.time() - float(inicio)) * 1000)
        except (TypeError, ValueError):
            duracion_ms = 0
    exito, salida, error, datos = False, "", "", {}
    verificado = False
    if isinstance(resultado, dict):
        exito = bool(resultado.get("exito", resultado.get("ok", False)))
        salida = str(resultado.get("salida", resultado.get("mensaje", "")) or "")
        error = str(resultado.get("error", "") or "")
        datos = resultado.get("datos", {}) if isinstance(resultado.get("datos"), dict) else {}
        verificado = bool(resultado.get("verificado", exito))
    elif isinstance(resultado, (tuple, list)) and len(resultado) >= 2:
        exito = bool(resultado[0])
        salida = str(resultado[1] or "")
        error = "" if exito else salida
        verificado = exito
    else:
        salida = str(resultado or "")
        exito = bool(salida)
        error = "" if exito else "resultado_vacio"
        verificado = exito
    observacion = Observacion(
        exito=exito, salida=salida, error=error, verificado=verificado,
        duracion_ms=duracion_ms, herramienta=str(herramienta or ""), datos=datos,
    )
    if verificador is not None:
        observacion.verificado = verificar(verificador, herramienta, observacion, esperado)
        if not observacion.verificado and observacion.exito:
            observacion.error = (observacion.error + " | verificacion_fallida").strip(" |")
    return observacion
