"""Confirmacion, vigencia y consumo atomico de autorizaciones."""
from __future__ import annotations

import time
from typing import Any, Optional

from ejecucion_modelo import SolicitudEjecucion
import permisos_modelo as pm


class AutorizacionMixin:
    def confirmar_autorizacion(
        self,
        id_autorizacion: str,
        actor: str = "usuario",
        codigo_refuerzo: Optional[str] = None,
        ttl_seg: Optional[float] = None,
    ) -> dict[str, Any]:
        actor_norm = str(actor or "").strip().lower()
        if actor_norm != "usuario":
            self._auditar(
                "INTENTO_AUTOAPROBACION", "", str(id_autorizacion), "",
                "cerebro" if actor_norm in ("cerebro", "llm") else "sistema",
                actor_norm, "denegada",
                "Actor no humano intento autoaprobar una autorizacion.",
                {},
            )
            return {"aprobada": False, "motivo": "ACTOR_NO_AUTORIZADO"}
        with self._bloqueo:
            solicitud = self._solicitudes.get(str(id_autorizacion))
        if solicitud is None:
            self._auditar(
                "AUTORIZACION_INEXISTENTE", "", str(id_autorizacion), "",
                "usuario", "usuario", "denegada",
                "No existe la solicitud de autorizacion.", {},
            )
            return {"aprobada": False, "motivo": "AUTORIZACION_INEXISTENTE"}
        if solicitud.estado != pm.ESTADO_PENDIENTE:
            return {"aprobada": False, "motivo": "ESTADO_AUTORIZACION_INVALIDO"}
        if solicitud.expira_en < time.time():
            solicitud.estado = pm.ESTADO_CADUCADA
            self._auditar(
                "AUTORIZACION_CADUCADA", solicitud.id_solicitud,
                solicitud.id_autorizacion, solicitud.herramienta,
                solicitud.origen, "usuario", "denegada",
                "La solicitud expiro antes de confirmarla.", {},
            )
            return {"aprobada": False, "motivo": "AUTORIZACION_CADUCADA"}
        if solicitud.nivel_autorizacion == pm.NIVEL_SENSIBLE_REFORZADA:
            if not isinstance(codigo_refuerzo, str) or not codigo_refuerzo.strip():
                self._auditar(
                    "REFUERZO_AUSENTE", solicitud.id_solicitud,
                    solicitud.id_autorizacion, solicitud.herramienta,
                    solicitud.origen, "usuario", "denegada",
                    "Operacion sensible reforzada sin codigo explicito.", {},
                )
                return {"aprobada": False, "motivo": "REFUERZO_REQUERIDO"}
        try:
            expira = time.time() + float(ttl_seg) if ttl_seg is not None else solicitud.expira_en
            if expira <= time.time():
                expira = solicitud.expira_en
        except Exception:
            expira = solicitud.expira_en
        solicitud.estado = pm.ESTADO_APROBADA
        concesion = pm.ConcesionAutorizacion(
            solicitud.id_solicitud,
            solicitud.id_autorizacion,
            solicitud.huella_operacion,
            aprobada_por="usuario",
            expira_en=expira,
        )
        with self._bloqueo:
            self._concesiones[concesion.id_autorizacion] = concesion
        self._auditar(
            "AUTORIZACION_APROBADA", solicitud.id_solicitud,
            solicitud.id_autorizacion, solicitud.herramienta,
            solicitud.origen, "usuario", "aprobada",
            "Confirmacion explicita aprobada por el usuario.", {},
        )
        return {"aprobada": True, "id_autorizacion": concesion.id_autorizacion}

    def validar_antes_de_ejecutar(
        self, solicitud: SolicitudEjecucion, contrato: Any
    ) -> dict[str, Any]:
        try:
            id_autorizacion = ""
            with self._bloqueo:
                for cid, concesion in self._concesiones.items():
                    if concesion.id_solicitud == solicitud.id_solicitud:
                        id_autorizacion = cid
                        break
            if not id_autorizacion:
                codigo = "AUTORIZACION_NO_DISPONIBLE"
                self._auditar(
                    "VALIDACION_RECHAZADA", solicitud.id_solicitud, "",
                    solicitud.herramienta, solicitud.origen, "motor",
                    "denegada", codigo, solicitud.parametros,
                )
                return {"permitida": False, "codigo": codigo}
            with self._bloqueo:
                concesion = self._concesiones.get(id_autorizacion)
                if concesion is None:
                    return {"permitida": False, "codigo": "AUTORIZACION_NO_DISPONIBLE"}
                huella = pm.huella_operacion(
                    solicitud.herramienta, solicitud.parametros, solicitud.id_solicitud
                )
                if huella != concesion.huella_operacion:
                    codigo = "PARAMETROS_MODIFICADOS"
                elif concesion.revocada:
                    codigo = "AUTORIZACION_REVOCADA"
                elif concesion.expira_en < time.time():
                    codigo = "AUTORIZACION_CADUCADA"
                elif concesion.consumida:
                    codigo = "AUTORIZACION_REUTILIZADA"
                else:
                    concesion.consumida = True
                    codigo = ""
                if codigo:
                    self._auditar(
                        "VALIDACION_RECHAZADA", solicitud.id_solicitud,
                        id_autorizacion, solicitud.herramienta,
                        solicitud.origen, "motor", "denegada",
                        codigo, solicitud.parametros,
                    )
                    return {"permitida": False, "codigo": codigo}
            self._auditar(
                "VALIDACION_APROBADA", solicitud.id_solicitud,
                id_autorizacion, solicitud.herramienta,
                solicitud.origen, "motor", "aprobada",
                "Huella, vigencia y revocacion validadas.",
                solicitud.parametros,
            )
            return {"permitida": True, "id_autorizacion": id_autorizacion}
        except Exception:
            self._auditar(
                "FALLO_FAIL_CLOSED", solicitud.id_solicitud, "",
                solicitud.herramienta, solicitud.origen, "motor",
                "denegada", "ERROR_INTERNO_VALIDACION",
                solicitud.parametros,
            )
            return {"permitida": False, "codigo": "ERROR_INTERNO_VALIDACION"}
