"""Políticas conservadoras para retención y mantenimiento de recuerdos."""
from datetime import datetime, timezone

PROTEGIDOS = {"explicito", "perfil", "identidad", "procedimental"}


def _dias(recuerdo, ahora=None):
    try:
        fecha = datetime.fromisoformat(str(recuerdo.get("actualizado_en") or recuerdo.get("creado_en")).replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return max(0, ((ahora or datetime.now(timezone.utc)) - fecha).days)
    except (TypeError, ValueError):
        return 0


def evaluar_retencion(recuerdo, ahora=None, umbral_dias=365):
    """Devuelve conservar, revisar u obsoleto; la edad por sí sola nunca borra."""
    meta = recuerdo.get("metadatos") or {}
    tipo, origen = recuerdo.get("tipo_memoria"), recuerdo.get("origen")
    try:
        confianza = float(recuerdo.get("confianza", 0))
        importancia = float(meta.get("importancia", meta.get("relevancia", 0)))
    except (TypeError, ValueError):
        confianza = importancia = 0
    if (origen == "explicito" or tipo == "procedimental" or
            str(meta.get("categoria", "")).casefold() in PROTEGIDOS or
            confianza >= .9 or importancia >= .85):
        return {"decision": "conservar", "motivo": "protegido"}
    edad = _dias(recuerdo, ahora)
    confirmaciones = int(meta.get("confirmaciones_posteriores", 0) or 0)
    actualizaciones = int(meta.get("frecuencia_actualizacion", 0) or 0)
    if edad < int(umbral_dias) or confirmaciones or actualizaciones >= 2:
        return {"decision": "conservar", "motivo": "vigente"}
    if tipo == "episodica" and edad >= int(umbral_dias) * 2:
        return {"decision": "obsoleto", "motivo": "episodio_antiguo_sin_confirmacion"}
    return {"decision": "revisar", "motivo": "antiguedad_sin_evidencia_suficiente"}


def evaluar_actualizacion(anterior, nuevo):
    if anterior.get("usuario_id") != nuevo.get("usuario_id"):
        return "rechazar"
    return "reemplazar_con_historial" if anterior.get("id") else "crear"
