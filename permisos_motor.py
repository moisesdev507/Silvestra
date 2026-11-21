"""Motor centralizado de politicas y evaluacion de autorizacion."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from ejecucion_modelo import SolicitudEjecucion
import permisos_modelo as pm
from permisos_autorizaciones import AutorizacionMixin
from permisos_auditoria import AuditoriaMixin


RIESGO_ORDEN = {"bajo": 1, "medio": 2, "alto": 3, "critico": 4}
ACTORES_NO_HUMANOS = {"cerebro", "llm", "planificador", "automatico"}


class MotorPermisos(AutorizacionMixin, AuditoriaMixin):
    def __init__(self) -> None:
        self._bloqueo = threading.RLock()
        self._politicas: dict[str, pm.PoliticaOperacion] = {}
        self._categorias: dict[str, pm.PoliticaOperacion] = {}
        self._solicitudes: dict[str, pm.SolicitudAutorizacion] = {}
        self._concesiones: dict[str, pm.ConcesionAutorizacion] = {}
        self._auditoria: list[pm.EventoAuditoria] = []

    def registrar_politica(
        self, politica: pm.PoliticaOperacion, actor: str = "sistema_inicio"
    ) -> tuple[bool, str]:
        actor_norm = str(actor or "").strip().lower()
        if actor_norm in ACTORES_NO_HUMANOS:
            self._auditar(
                "INTENTO_MODIFICACION_POLITICA", "", "", "",
                actor_norm, actor_norm, "denegada",
                "Actor no humano intento registrar o modificar una politica.",
                {},
            )
            return False, "Solo el sistema inicio o un usuario puede registrar politicas."
        if not isinstance(politica, pm.PoliticaOperacion):
            self._auditar(
                "POLITICA_INVALIDA", "", "", "", "sistema",
                actor_norm, "denegada", "Objeto de politica invalido.", {},
            )
            return False, "Politica invalida."
        try:
            valida, motivo = politica.valida_integridad()
            if not valida:
                self._auditar(
                    "POLITICA_INVALIDA", "", "", politica.herramienta,
                    "sistema", actor_norm, "denegada", motivo, {},
                )
                return False, motivo
            with self._bloqueo:
                if "*" not in politica.herramienta:
                    self._politicas[politica.herramienta] = politica
                else:
                    clave = politica.herramienta.strip("*").strip(".")
                    self._categorias[clave] = politica
            self._auditar(
                "POLITICA_REGISTRADA", "", "", politica.herramienta,
                "sistema", actor_norm, "aprobada",
                "Politica registrada.", {},
            )
            return True, "Politica registrada."
        except Exception:
            self._auditar(
                "FALLO_REGISTRO_POLITICA", "", "",
                getattr(politica, "herramienta", ""), "sistema",
                actor_norm, "denegada",
                "Error interno al registrar politica.", {},
            )
            return False, "Error interno al registrar politica."

    def _obtener_politica(
        self, solicitud: SolicitudEjecucion, contrato: Any
    ) -> Optional[pm.PoliticaOperacion]:
        nombre = solicitud.herramienta
        with self._bloqueo:
            directa = self._politicas.get(nombre)
            if directa is not None:
                return directa
            categoria = str(getattr(contrato, "categoria", "") or "").strip().lower()
            encontrada = self._categorias.get(categoria)
            if encontrada is not None:
                return encontrada
            for patron, politica in self._categorias.items():
                if patron and (nombre.startswith(patron) or categoria.startswith(patron)):
                    return politica
        return None

    def evaluar_solicitud(
        self, solicitud: SolicitudEjecucion, contrato: Any
    ) -> dict[str, Any]:
        try:
            with self._bloqueo:
                for concesion in self._concesiones.values():
                    if concesion.id_solicitud == solicitud.id_solicitud:
                        estado = self._estado_concesion(concesion, solicitud)
                        if estado:
                            return estado
                        return {
                            "decision": "permitida",
                            "id_autorizacion": concesion.id_autorizacion,
                        }

            politica = self._obtener_politica(solicitud, contrato)
            if politica is None:
                return self._rechazar(
                    "SIN_POLITICA",
                    "Denegacion fail-closed: no existe politica.",
                    solicitud,
                )
            if not politica.habilitada:
                return self._rechazar(
                    "POLITICA_DESHABILITADA",
                    "Denegacion fail-closed: politica deshabilitada.",
                    solicitud,
                )

            riesgo = str(getattr(contrato, "nivel_riesgo", "critico")).lower()
            permitido = RIESGO_ORDEN.get(politica.riesgo_maximo_permitido, 0)
            if RIESGO_ORDEN.get(riesgo, 4) > permitido:
                return self._rechazar(
                    "RIESGO_SUPERADO",
                    "Riesgo del contrato supera el permitido.",
                    solicitud,
                )

            nivel = politica.nivel_autorizacion
            if nivel == pm.NIVEL_PROHIBIDA:
                return self._rechazar(
                    "OPERACION_PROHIBIDA",
                    "Operacion bloqueada por politica prohibida.",
                    solicitud,
                )
            if nivel == pm.NIVEL_SOLO_LECTURA:
                huella = pm.huella_operacion(
                    solicitud.herramienta, solicitud.parametros, solicitud.id_solicitud
                )
                autorizacion = pm.SolicitudAutorizacion(
                    solicitud.id_solicitud, solicitud.herramienta, solicitud.origen,
                    nivel, huella,
                    expira_en=time.time() + politica.ttl_seg_por_defecto,
                )
                with self._bloqueo:
                    self._solicitudes[autorizacion.id_autorizacion] = autorizacion
                    self._concesiones[autorizacion.id_autorizacion] = pm.ConcesionAutorizacion(
                        solicitud.id_solicitud, autorizacion.id_autorizacion, huella,
                        expira_en=autorizacion.expira_en,
                    )
                self._auditar(
                    "SOLO_LECTURA_APROBADA", solicitud.id_solicitud,
                    autorizacion.id_autorizacion, solicitud.herramienta,
                    solicitud.origen, "motor", "aprobada",
                    "Operacion permitida por politica explicita.",
                    solicitud.parametros,
                )
                return {"decision": "permitida", "id_autorizacion": autorizacion.id_autorizacion}

            if nivel in (pm.NIVEL_REQUIERE_CONFIRMACION, pm.NIVEL_SENSIBLE_REFORZADA):
                huella = pm.huella_operacion(
                    solicitud.herramienta, solicitud.parametros, solicitud.id_solicitud
                )
                autorizacion = pm.SolicitudAutorizacion(
                    solicitud.id_solicitud, solicitud.herramienta, solicitud.origen,
                    nivel, huella,
                    expira_en=time.time() + politica.ttl_seg_por_defecto,
                )
                with self._bloqueo:
                    self._solicitudes[autorizacion.id_autorizacion] = autorizacion
                self._auditar(
                    "CONFIRMACION_PENDIENTE", solicitud.id_solicitud,
                    autorizacion.id_autorizacion, solicitud.herramienta,
                    solicitud.origen, "motor", "pendiente",
                    "Se requiere confirmacion explicita del usuario.",
                    solicitud.parametros,
                )
                return {
                    "decision": "pendiente_autorizacion",
                    "id_autorizacion": autorizacion.id_autorizacion,
                    "nivel_autorizacion": nivel,
                }
            return self._rechazar(
                "NIVEL_AUTORIZACION_INVALIDO",
                "Nivel de autorizacion invalido.",
                solicitud,
            )
        except Exception:
            return self._rechazar(
                "ERROR_INTERNO_PERMISOS",
                "Error interno evaluado con fail-closed.",
                solicitud,
            )

    def _estado_concesion(
        self, concesion: pm.ConcesionAutorizacion, solicitud: SolicitudEjecucion
    ) -> Optional[dict[str, Any]]:
        ahora = time.time()
        if concesion.revocada:
            codigo = "AUTORIZACION_REVOCADA"
        elif concesion.expira_en < ahora:
            codigo = "AUTORIZACION_CADUCADA"
        elif concesion.consumida:
            codigo = "AUTORIZACION_REUTILIZADA"
        else:
            huella = pm.huella_operacion(
                solicitud.herramienta, solicitud.parametros, solicitud.id_solicitud
            )
            if huella != concesion.huella_operacion:
                codigo = "PARAMETROS_MODIFICADOS"
            else:
                return None
        self._auditar(
            "VALIDACION_RECHAZADA", solicitud.id_solicitud,
            concesion.id_autorizacion, solicitud.herramienta,
            solicitud.origen, "motor", "denegada", codigo,
            solicitud.parametros,
        )
        return {"decision": "rechazada", "motivo": codigo}

    def _rechazar(
        self, codigo: str, motivo: str, solicitud: SolicitudEjecucion
    ) -> dict[str, Any]:
        self._auditar(
            "FALLO_FAIL_CLOSED" if codigo.startswith("ERROR")
            else ("SIN_POLITICA" if codigo == "SIN_POLITICA" else "EVALUACION_DENEGADA"),
            solicitud.id_solicitud, "", solicitud.herramienta,
            solicitud.origen, "motor", "denegada", motivo,
            solicitud.parametros,
        )
        return {"decision": "rechazada", "motivo": codigo}

    def validar_para_ejecucion(
        self, solicitud: SolicitudEjecucion, contrato: Any
    ) -> dict[str, Any]:
        decision = self.evaluar_solicitud(solicitud, contrato)
        if decision["decision"] == "pendiente_autorizacion":
            return {"estado": "pendiente", **decision}
        if decision["decision"] != "permitida":
            return {"estado": "rechazada", **decision}
        validacion = self.validar_antes_de_ejecutar(solicitud, contrato)
        if validacion.get("permitida"):
            return {"estado": "permitida", **validacion}
        return {"estado": "rechazada", **validacion}
