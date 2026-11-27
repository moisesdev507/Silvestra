"""Iniciativa proactiva compartida: Gemini Live y Celeste con las mismas reglas.

Toma seguimientos vencidos, recordatorios y avisos de ``cerebro_proactivo``;
respeta cooldown, modo Privado y modo Noche. Con Live activo inyecta la voz
por la sesión (incluso en Reposo Azul); si no, encola la frase para Celeste.
"""
import hashlib
import threading
import time

_MAX_EMITIDOS = 64
_bloqueo = threading.RLock()
_emitidos = {}


def _token(tipo, mensaje):
    return str(tipo) + ":" + hashlib.sha1(str(mensaje).encode("utf-8")).hexdigest()[:12]


def _aviso(tipo, mensaje, emocion="neutral"):
    return {"tipo": tipo, "mensaje": " ".join(str(mensaje or "").split())[:180],
            "emocion": emocion or "neutral"}


def obtener_aviso(app=None):
    """Devuelve un aviso real pendiente o ``None``; nunca inventa temas."""
    try:
        import ciclo_sueno_kaya
        memoria = getattr(app, "memoria", None) if app is not None else None
        uid = getattr(memoria, "usuario_id", "local") or "local"
        seguimiento = ciclo_sueno_kaya.seguimiento_para_prompt(usuario_id=uid)
        if seguimiento:
            return _aviso("seguimiento", seguimiento, "calida")
    except Exception:
        pass

    try:
        import recordatorios
        ahora = time.time()
        with _bloqueo:
            vistos = dict(_emitidos)
        for fila in recordatorios._cargar():
            if fila.get("completado") or float(fila.get("timestamp", 0)) > ahora:
                continue
            if ahora - float(fila.get("timestamp", 0)) > 86400.0:
                continue
            texto = str(fila.get("texto") or fila.get("mensaje") or "").strip()
            if texto and _token("recordatorio", texto) not in vistos:
                return _aviso("recordatorio", texto, "neutral")
    except Exception:
        pass

    try:
        import cerebro_proactivo
        resultado = cerebro_proactivo.obtener_motor_proactivo().evaluar_oportunidad(app=app)
        if resultado:
            mensaje, emocion = resultado
            return _aviso("proactivo", mensaje, emocion)
    except Exception:
        pass
    return None


def puede_emitir(app, aviso, forzar=False):
    """Aplica Privado, Noche y el cooldown del motor proactivo existente."""
    if app is None:
        return False, "sin_app"
    try:
        import cerebro_proactivo as cp
        if cp.es_modo_privado(app):
            return False, "modo_privado"
        if cp.es_modo_noche(app) and aviso.get("tipo") != "cuidado_nocturno":
            return False, "modo_noche"
        motor = cp.obtener_motor_proactivo()
        return motor.puede_intervenir(
            app=app, forzar_cooldown=bool(forzar), motivo=aviso.get("tipo"))
    except Exception:
        return False, "motor_no_disponible"


def emitir(app=None, forzar=False):
    """Entrega el aviso por Live o por Celeste; True si llegó a.emitirse."""
    aviso = obtener_aviso(app)
    if not aviso:
        return False
    # 'evaluar_oportunidad' ya aplicó cooldown/Privado/Noche a los avisos
    # proactivos y actualizó ultimo_aviso: no volver a bloquearlos aquí.
    if aviso["tipo"] == "proactivo":
        autorizado, motivo = True, ""
    else:
        autorizado, motivo = puede_emitir(app, aviso, forzar)
    if not autorizado:
        print(f"[PRO-UNIFICADO] Aviso {aviso['tipo']} omitido: {motivo}", flush=True)
        return False
    mensaje = aviso["mensaje"]
    if not mensaje:
        return False
    token = _token(aviso["tipo"], mensaje)
    with _bloqueo:
        if token in _emitidos and not forzar:
            return False
    orden = f"Di en voz alta, breve y natural: {mensaje}"
    entregado = False
    sesion = None
    try:
        import live_motor
        sesion = live_motor.sesion_activa()
    except Exception:
        pass
    if sesion is not None:
        try:
            puente = getattr(sesion, "_puente_webrtc", None)
            if puente is not None and getattr(puente, "dormida", False):
                try:
                    puente.despertar()
                except Exception:
                    pass
                puente.dormida = False
            import live_estado
            live_estado.reanudar_escucha(sesion)
            entregado = bool(sesion.enviar_texto(orden, turn_complete=False))
        except Exception:
            entregado = False
    cl = getattr(app, "coordinador_live", None)
    if not entregado and cl is not None:
        try:
            if cl.esta_live_activo():
                # Reposo Azul: despierta el micrófono y deja pasar la voz.
                sesion_cl = getattr(cl, "sesion_live", None)
                puente = getattr(sesion_cl, "_puente_webrtc", None)
                if puente is not None and getattr(puente, "dormida", False):
                    try:
                        puente.despertar()
                    except Exception:
                        pass
                    puente.dormida = False
                entregado = bool(cl.enviar_orden(orden, turn_complete=False))
            elif cl.es_modo_principal():
                entregado = bool(cl.intentar_activar_live(orden))
        except Exception:
            entregado = False
    if not entregado:
        cola = getattr(app, "cola", None)
        if cola is None:
            return False
        cola.put(("hablar", (mensaje, aviso.get("emocion", "neutral"))))
        entregado = True
    with _bloqueo:
        _emitidos[token] = time.time()
        while len(_emitidos) > _MAX_EMITIDOS:
            _emitidos.pop(next(iter(_emitidos)))
    try:
        import cerebro_proactivo
        cerebro_proactivo.obtener_motor_proactivo().ultimo_aviso = time.time()
    except Exception:
        pass
    print(f"[PRO-UNIFICADO] {aviso['tipo']}: {mensaje}", flush=True)
    return entregado


def reiniciar():
    """Limpia la memoria de avisos ya entregados."""
    with _bloqueo:
        _emitidos.clear()
    return True


__all__ = ["obtener_aviso", "puede_emitir", "emitir", "reiniciar"]
