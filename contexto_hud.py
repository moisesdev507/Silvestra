"""Módulo puente de telemetría y sanitización para el HUD remoto (Etapa 4).

Transforma el snapshot del Silvestra Context Engine en telemetría visual segura,
con control estricto de frescura (staleness), sanitización de privacidad y
deduplicación anti-spam para la infraestructura SSE existente.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

UMBRAL_STALENESS_HUD_SEG = 15.0

# Almacén de deduplicación en memoria
_ultimo_hash_telemetria: str = ""
_ultimo_estado_frescura: str = ""


def sanitizar_titulo_ventana(titulo: str) -> str:
    """Sanitiza el título de la ventana removiendo rutas de disco o datos sensibles."""
    if not titulo:
        return ""
    t = str(titulo).strip()
    # Ocultar rutas de archivo completas (C:\... o /...)
    if ":\\" in t or t.startswith("/"):
        partes = t.replace("\\", "/").split("/")
        t = partes[-1]
    # Limitar longitud para evitar desbordar la tarjeta del HUD
    return t[:40] if len(t) <= 40 else t[:37] + "..."


def obtener_telemetria_contexto(app: Any = None) -> dict[str, Any]:
    """Genera la estructura de telemetría situacional lista para el HUD y SSE."""
    try:
        import contexto_motor
        motor = contexto_motor.obtener_motor_contexto(app)
        ctx = motor.obtener_contexto()
    except Exception:
        ctx = {}

    t_ahora = time.time()
    ts = float(ctx.get("timestamp", 0.0))
    edad_seg = round(max(0.0, t_ahora - ts), 1) if ts > 0.0 else 999.0

    # Control de frescura (staleness)
    if ts <= 0.0:
        estado_actualizacion = "no_disponible"
    elif edad_seg > UMBRAL_STALENESS_HUD_SEG:
        estado_actualizacion = "desactualizado"
    else:
        estado_actualizacion = "en_vivo"

    det = ctx.get("detectado", {})
    prob = ctx.get("probable", {})
    conf = ctx.get("confirmado", {})
    fuentes = det.get("fuentes_estado", {})

    # 1. Sistema
    win = det.get("ventana", {})
    exe = str(win.get("ejecutable") or "").strip()
    tit = sanitizar_titulo_ventana(str(win.get("titulo") or ""))
    inact = float(win.get("inactividad_seg", 0.0))
    inact_tramo = int(round(inact / 5.0) * 5)  # redondeo a 5s para deduplicación

    proy = prob.get("proyecto", {})
    nom_proy = str(proy.get("valor") or "").strip() if proy else ""

    app_display = exe or "En reposo"
    if nom_proy:
        app_display = f"{exe} [{nom_proy}]"
    elif tit and tit != exe:
        app_display = f"{exe} ({tit})"

    # 2. Actividad y certeza
    act = prob.get("actividad", {})
    act_val = str(act.get("valor") or "desconocida")
    act_conf = float(act.get("confianza", 0.0))
    act_regla = str(act.get("regla") or "")

    modo = det.get("modo_sistema", {})
    modo_val = str(modo.get("modo", "normal"))
    modo_lbl = str(modo.get("etiqueta", "Normal"))

    # Nivel de certeza visual (CONFIRMADO, PROBABLE o DETECTADO)
    if conf:
        certeza = "CONFIRMADO"
        certeza_detalle = ", ".join(f"{k}={v.get('valor')}" for k, v in conf.items())
    elif act_val in ("ausente", "programando", "navegando", "comunicacion", "multimedia"):
        certeza = "PROBABLE"
        certeza_detalle = f"{int(act_conf * 100)}% conf"
    else:
        certeza = "DETECTADO"
        certeza_detalle = "telemetría"

    # 3. Presencia
    pres = det.get("presencia", {})
    pres_activa = bool(pres.get("activa", False))
    pres_ausente = bool(pres.get("ausente", False))
    if not pres_activa:
        pres_estado = "Inactiva"
    elif pres_ausente:
        pres_estado = "Ausente"
    else:
        pres_estado = "Presente"

    # 4. Recordatorios
    recs = det.get("recordatorios", {})
    total_recs = int(recs.get("total_pendientes", 0))
    prox_txt = "Sin pendientes"
    if total_recs > 0 and recs.get("proximos"):
        p = recs["proximos"][0]
        prox_txt = f"{p.get('hora', '')}: {p.get('texto', '')}"[:30]

    return {
        "sistema": {
            "aplicacion": app_display[:45],
            "ejecutable": exe,
            "inactividad_seg": round(inact, 1),
            "inactividad_tramo": inact_tramo,
            "proyecto": nom_proy,
        },
        "actividad": {
            "valor": act_val,
            "certeza": certeza,
            "certeza_detalle": certeza_detalle,
            "confianza": act_conf,
            "regla": act_regla,
            "modo": modo_val,
            "modo_etiqueta": modo_lbl,
        },
        "presencia": {
            "activa": pres_activa,
            "ausente": pres_ausente,
            "estado": pres_estado,
        },
        "recordatorios": {
            "total": total_recs,
            "proximo": prox_txt,
        },
        "conexion": {
            "estado_actualizacion": estado_actualizacion,
            "edad_seg": edad_seg,
            "timestamp": ts,
            "fuentes": fuentes,
        },
    }


def calcular_firma_telemetria(datos: dict[str, Any]) -> str:
    """Calcula firma semántica para evitar emitir ráfagas de eventos duplicados."""
    sis = datos.get("sistema", {})
    act = datos.get("actividad", {})
    pre = datos.get("presencia", {})
    rec = datos.get("recordatorios", {})
    con = datos.get("conexion", {})

    nucleo = (
        f"{sis.get('aplicacion')}|{sis.get('inactividad_tramo')}|"
        f"{act.get('valor')}|{act.get('certeza')}|{act.get('modo')}|"
        f"{pre.get('estado')}|{rec.get('total')}|{rec.get('proximo')}|"
        f"{con.get('estado_actualizacion')}"
    )
    return hashlib.md5(nucleo.encode("utf-8")).hexdigest()


def telemetria_ha_cambiado(datos: dict[str, Any]) -> bool:
    """Indica si el estado contextual ha cambiado semánticamente desde el último evento."""
    global _ultimo_hash_telemetria, _ultimo_estado_frescura
    firma = calcular_firma_telemetria(datos)
    frescura = datos.get("conexion", {}).get("estado_actualizacion", "")

    cambio = (firma != _ultimo_hash_telemetria) or (frescura != _ultimo_estado_frescura)
    if cambio:
        _ultimo_hash_telemetria = firma
        _ultimo_estado_frescura = frescura
    return cambio
