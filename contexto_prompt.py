"""Módulo puente entre el Silvestra Context Engine y el prompt del cerebro (Etapa 3).

Transforma el snapshot situacional en una directiva ultra-compacta (<= 50 tokens),
validando frescura (staleness), omitiendo fuentes inactivas y reforzando
reglas de certeza, discreción y privacidad para el LLM.
"""
from __future__ import annotations

import time
from typing import Any

UMBRAL_STALENESS_SEG = 15.0


def formatear_relaciones(relaciones, limite=500):
    lineas = []
    for r in (relaciones or [])[:8]:
        if r.get("estado") != "activo" or float(r.get("confianza", 0)) < .75:
            continue
        marca = "confirmada" if r.get("origen") == "explicita" else "inferida"
        linea = f"{r.get('nombre_origen','?')} —{r.get('tipo_relacion')}→ {r.get('nombre_destino','?')} ({marca}, confianza {float(r.get('confianza',0)):.2f})"
        lineas.append(linea)
    return ("Relaciones de alta confianza:\n" + "\n".join(lineas))[:max(0, int(limite))] if lineas else ""


def formatear_contexto_para_prompt(ctx: dict[str, Any], t_ahora: float | None = None) -> str:
    """Sintetiza el contexto en una directiva ultra-breve respetando el presupuesto de tokens."""
    if not ctx or not isinstance(ctx, dict):
        return ""

    ahora = time.time() if t_ahora is None else float(t_ahora)
    ts = float(ctx.get("timestamp", 0.0))

    # Validación de frescura (staleness): descartar si supera el umbral
    if ts <= 0.0 or (ahora - ts) > UMBRAL_STALENESS_SEG:
        return ""

    det = ctx.get("detectado", {})
    prob = ctx.get("probable", {})
    conf = ctx.get("confirmado", {})
    fuentes = det.get("fuentes_estado", {})

    elementos_det: list[str] = []

    # 1. Ventana activa / Proyecto
    if fuentes.get("windows") == "ok":
        win = det.get("ventana", {})
        exe = (win.get("ejecutable") or "").strip()
        proy = prob.get("proyecto", {})
        nombre_proy = proy.get("valor") if proy else None

        if exe:
            if nombre_proy:
                elementos_det.append(f"{exe} [{nombre_proy}]")
            else:
                elementos_det.append(exe)

        inact = float(win.get("inactividad_seg", 0.0))
        if inact >= 10.0:
            elementos_det.append(f"inact:{int(inact)}s")

    # 2. Modo no estándar
    if fuentes.get("modos_sistema") == "ok":
        modo = det.get("modo_sistema", {}).get("modo", "normal")
        if modo and modo != "normal":
            elementos_det.append(f"modo:{modo}")

    # 3. Presencia (solo si relevante)
    if fuentes.get("presencia") == "ok":
        pres = det.get("presencia", {})
        if pres.get("activa") and pres.get("ausente"):
            elementos_det.append("dueño:ausente")

    # 4. Recordatorios próximos (solo si existen)
    if fuentes.get("recordatorios") == "ok":
        recs = det.get("recordatorios", {})
        if recs.get("total_pendientes", 0) > 0 and recs.get("proximos"):
            prox = recs["proximos"][0]
            txt = prox.get("texto", "")[:20]
            elementos_det.append(f"rec:{txt}")

    # Si no hay ningún dato detectado válido, no inyectar ruido
    if not elementos_det and not conf:
        return ""

    lineas = ["[CONTEXTO (discreto)]"]
    if elementos_det:
        lineas.append(f"- DETECTADO: {', '.join(elementos_det)}")

    # Actividad probable (siempre calificada como inferencia, jamás certeza)
    act = prob.get("actividad", {})
    val_act = act.get("valor")
    if val_act and val_act not in ("desconocida", "actividad_general"):
        lineas.append(f"- PROBABLE: {val_act} (hipótesis)")

    # Hechos confirmados explícitos vigentes
    if conf:
        items_c = [f"{k}={it.get('valor')!r}" for k, it in conf.items() if it.get("valor") is not None]
        if items_c:
            lineas.append(f"- CONFIRMADO: {', '.join(items_c)}")

    lineas.append("*Regla: PROBABLE es hipótesis. Úsalo solo si aporta; jamás finjas ver su pantalla.")
    return "\n".join(lineas)


def generar_directiva_contexto(app: Any = None, max_antiguedad_seg: float = UMBRAL_STALENESS_SEG) -> str:
    """Consulta el motor de contexto y produce el bloque formateado para cerebro_prompt."""
    try:
        import contexto_motor
        motor = contexto_motor.obtener_motor_contexto(app)
        ctx = motor.obtener_contexto()

        t_ahora = time.time()
        ts = float(ctx.get("timestamp", 0.0))

        # Si el snapshot está vencido, intentar refresco rápido
        if ts <= 0.0 or (t_ahora - ts) > max_antiguedad_seg:
            ctx = motor.actualizar(forzar=False)

        return formatear_contexto_para_prompt(ctx, t_ahora=t_ahora)
    except Exception:
        return ""
