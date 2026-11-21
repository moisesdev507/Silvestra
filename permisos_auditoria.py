"""Auditoria, revocacion y consulta thread-safe de permisos."""
from __future__ import annotations

from typing import Any, Optional

import permisos_modelo as pm


class AuditoriaMixin:
    def _auditar(
        self,
        tipo_evento: str,
        id_solicitud: str,
        id_autorizacion: str,
        herramienta: str,
        origen: str,
        actor: str,
        decision: str,
        motivo: str,
        parametros: dict[str, Any],
    ) -> pm.EventoAuditoria:
        evento = pm.EventoAuditoria(
            tipo_evento=tipo_evento,
            id_solicitud=id_solicitud,
            id_autorizacion=id_autorizacion,
            herramienta=herramienta,
            origen=origen,
            actor=actor,
            decision=decision,
            motivo=motivo,
            parametros_sanitizados=pm.sanitizar_parametros(parametros),
        )
        with self._bloqueo:
            self._auditoria.append(evento)
        return evento

    def revocar_autorizacion(
        self,
        id_autorizacion: Optional[str] = None,
        id_solicitud: Optional[str] = None,
        herramienta: Optional[str] = None,
        actor: str = "usuario",
    ) -> int:
        actor_norm = str(actor or "").strip().lower()
        if actor_norm != "usuario":
            self._auditar(
                "INTENTO_REVOCACION_NO_HUMANA", id_solicitud or "",
                id_autorizacion or "", herramienta or "", "sistema",
                actor_norm, "denegada",
                "Solo el usuario puede revocar autorizaciones.", {},
            )
            return 0
        cantidad = 0
        with self._bloqueo:
            for cid, concesion in self._concesiones.items():
                coincide = (
                    id_autorizacion is not None and cid == str(id_autorizacion)
                ) or (
                    id_solicitud is not None
                    and concesion.id_solicitud == str(id_solicitud)
                ) or (
                    herramienta is not None
                    and cid in self._solicitudes
                    and self._solicitudes[cid].herramienta
                    == str(herramienta).strip().lower()
                )
                if coincide and not concesion.revocada:
                    concesion.revocada = True
                    solicitud = self._solicitudes.get(cid)
                    if solicitud:
                        solicitud.estado = pm.ESTADO_REVOCADA
                    cantidad += 1
                    self._auditar(
                        "AUTORIZACION_REVOCADA", concesion.id_solicitud,
                        cid, solicitud.herramienta if solicitud else (herramienta or ""),
                        solicitud.origen if solicitud else "usuario",
                        "usuario", "aprobada",
                        "Autorizacion revocada por el usuario.", {},
                    )
        return cantidad

    def obtener_auditoria(
        self, limite: int = 50, solo_denegadas: bool = False
    ) -> list[dict[str, Any]]:
        try:
            tope = max(0, int(limite))
        except Exception:
            tope = 50
        with self._bloqueo:
            eventos = list(reversed(self._auditoria))
            if solo_denegadas:
                eventos = [e for e in eventos if e.decision == "denegada"]
            return [e.a_dict() for e in eventos[:tope]]
