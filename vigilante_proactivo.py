"""Vigilante proactivo ligero: entregas próximas y alertas de hardware.

Evalúa como máximo cada 5 minutos, aplica 20 minutos de cooldown por tipo de
aviso y devuelve texto vacío en turnos normales. Nunca escribe en app.cola.
"""
import datetime as dt
import time

COOLDOWN_SEG = 20 * 60
REEVALUAR_SEG = 5 * 60
VENTANA_SEG = 45 * 60
_estado = {"ultimo": {}, "evaluado": 0.0}


def _numero(valor):
    try:
        return float(valor)
    except Exception:
        return 0.0


def _parsear_inicio(valor):
    texto = str(valor or "")
    if not texto:
        return 0.0
    try:
        fecha = dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.astimezone()
        return fecha.timestamp()
    except Exception:
        return 0.0


def _aviso(tipo, mensaje, emocion, ahora):
    if ahora - _estado["ultimo"].get(tipo, -1.0e18) < COOLDOWN_SEG:
        return None
    return {"tipo": tipo, "mensaje": mensaje, "emocion": emocion,
            "timestamp": ahora}


def _marcar(aviso):
    _estado["ultimo"][aviso["tipo"]] = aviso["timestamp"]


def _entrega(ahora):
    """Cruza recordatorios, memoria persistente y Agenda de Google."""
    candidatos = []
    try:
        import recordatorios
        for fila in recordatorios._cargar() or []:
            if fila.get("completado"):
                continue
            momento = _numero(fila.get("timestamp"))
            if 0 <= momento - ahora <= VENTANA_SEG:
                candidatos.append((momento, str(fila.get("texto") or "tarea")[:70]))
    except Exception:
        pass
    try:
        import memoria_persistente as memoria
        import recordatorios
        for fila in memoria.listar_recuerdos(limite=15) or []:
            texto = str(fila.get("valor") or "")
            try:
                momento = _numero(recordatorios.parsear_tiempo(texto)[0])
            except Exception:
                continue
            if 0 <= momento - ahora <= VENTANA_SEG:
                candidatos.append((momento, texto[:70]))
    except Exception:
        pass
    try:
        import google_workspace as google
        datos = google.agenda_hoy(dias=1)
        if datos.get("ok"):
            for evento in datos.get("eventos", []):
                momento = _parsear_inicio(evento.get("inicio"))
                if 0 <= momento - ahora <= VENTANA_SEG:
                    candidatos.append((momento, str(evento.get("titulo") or "evento")[:70]))
    except Exception:
        pass
    if not candidatos:
        return None
    momento, texto = min(candidatos)
    minutos = max(1, int((momento - ahora + 59) // 60))
    return _aviso("entrega", f"Aviso: {texto} en {minutos} min.", "concentrada", ahora)


def _hardware(ahora):
    """Batería crítica sin cargador o RAM por encima del 90%."""
    try:
        import telemetria
        bateria = telemetria.estado_bateria() or {}
        porcentaje = _numero(bateria.get("porcentaje"))
        if (bateria.get("disponible") and not bateria.get("cargando")
                and 0 < porcentaje < 18):
            return _aviso("bateria",
                          f"Aviso: batería al {int(porcentaje)}% y sin cargador.",
                          "preocupada", ahora)
        ram = _numero((telemetria.metricas() or (0, 0))[1])
        if ram > 90:
            return _aviso("ram", f"Aviso: RAM al {int(ram)}%.",
                          "preocupada", ahora)
    except Exception:
        pass
    return None


def evaluar(consulta="", ahora=None, forzar=False, app=None):
    """Devuelve un aviso (tipo, mensaje, emoción) o ``None``."""
    momento = time.time() if ahora is None else float(ahora)
    if not forzar and momento - _estado["evaluado"] < REEVALUAR_SEG:
        return None
    _estado["evaluado"] = momento
    aviso = _entrega(momento) or _hardware(momento)
    if not aviso and app:
        try:
            import iniciativa_kaya
            aviso = iniciativa_kaya.evaluar_iniciativa_organica(app, ahora=momento)
        except Exception:
            pass
    if aviso:
        _marcar(aviso)
    return aviso


def contexto_para_prompt(consulta="", ahora=None):
    """Un único aviso breve para ``contexto_adicional`` o cadena vacía."""
    aviso = evaluar(consulta, ahora)
    return aviso["mensaje"] if aviso else ""


def reiniciar():
    """Reinicia cooldowns y cadencia (tests)."""
    _estado["ultimo"].clear()
    _estado["evaluado"] = 0.0
    return True


__all__ = ["COOLDOWN_SEG", "VENTANA_SEG", "evaluar",
           "contexto_para_prompt", "reiniciar"]
