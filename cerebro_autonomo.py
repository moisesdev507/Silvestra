"""Consolidación en reposo y gatekeeper único de atención para Live y Celeste.

Un sola candado, un solo anti-spam; SQLite y red corren siempre en daemon.
"""
import contextlib
import io
import os
import threading
import time

import cerebro_proactivo
import estado_emocional_kaya
import iniciativa_unificada

_COOLDOWN_REPOSO_SEG = 15 * 60
_COOLDOWN_ATENCION_SEG = 15 * 60
_REPOSO_SEG = 10 * 60
_UMBRAL_TURNOS = 6
_CONF_MAX = 0.95
_CONF_DELTA = 0.05
_CACHE_TONO_SEG = 60.0

_bloqueo = threading.RLock()
_app = None
_tono_cache = ("", 0.0)
_consolidando = False
_ultima_consolidacion = 0.0
_ultima_actividad = 0.0
_turnos = 0
_ultima_atencion = 0.0


def configurar_app(app):
    """Registra la app viva (Live o Celeste) para entregar los avisos."""
    global _app
    if app is None:
        return False
    with _bloqueo:
        _app = app
    return True


def _app_registrada():
    with _bloqueo:
        app = _app
    if app is not None:
        return app
    try:
        import pantalla_remota_accion
        return pantalla_remota_accion.obtener_app()
    except Exception:
        return None


def _usuario(app):
    memoria = getattr(app, "memoria", None) if app is not None else None
    return getattr(memoria, "usuario_id", "local") or "local"


def _ruta_db(app):
    """Ruta real de la memoria principal; nunca crea una base paralela."""
    principal = None
    try:
        import memoria
        principal = memoria.instancia_principal()
    except Exception:
        pass
    ruta = getattr(getattr(principal, "almacen", None), "ruta", None)
    if ruta:
        return ruta
    ruta = os.environ.get("SILVESTRA_MEMORIA_DB")
    if ruta:
        return ruta
    try:
        import ciclo_sueno_kaya
        return ciclo_sueno_kaya.RUTA_DB
    except Exception:
        return "silvestra_memoria.db"


def _reforzar_confianza(almacen):
    """Refuerza la confianza de los ganadores de la deduplicación."""
    con = getattr(almacen, "conexion", None)
    if con is None:
        return 0
    try:
        with almacen._lock:
            filas = con.execute(
                "SELECT DISTINCT reemplaza_a_id AS id FROM recuerdos "
                "WHERE reemplaza_a_id IS NOT NULL AND estado != 'obsoleto'"
            ).fetchall()
            for fila in filas:
                con.execute(
                    "UPDATE recuerdos SET confianza = MIN(?, COALESCE(confianza, 0.5) + ?) "
                    "WHERE id = ? AND estado != 'obsoleto'",
                    (_CONF_MAX, _CONF_DELTA, fila[0]))
            con.commit()
            return len(filas)
    except Exception:
        return 0


def _consolidar(uid, ruta_db, app):
    """Secuencia en daemon: una sola escritora SQLite a la vez."""
    global _consolidando
    silencio = io.StringIO()
    resultado = {"intuiciones": 0, "duplicados": 0, "resumenes": 0,
                 "consolidados": 0, "confianza": 0, "pasos": 0}
    with contextlib.redirect_stdout(silencio):
        try:
            import memoria_contexto
            turnos = memoria_contexto.turnos_recientes()
        except Exception:
            turnos = []
        try:
            import ciclo_sueno_kaya
            resultado["intuiciones"] = int(
                ciclo_sueno_kaya.consolidar(turnos, uid) or 0)
            resultado["pasos"] += 1
        except Exception:
            pass
        try:
            import memoria_sueno
            sueno = memoria_sueno.ejecutar_sueno_cognitivo(db_path=ruta_db)
            resultado["duplicados"] = int(sueno.get("duplicados_consolidados", 0))
            resultado["resumenes"] = int(sueno.get("resumenes_generados", 0))
            resultado["pasos"] += 1
        except Exception:
            pass
        try:
            import memoria_unificada
            almacen = getattr(memoria_unificada._principal(), "almacen", None)
            if almacen is not None:
                import memoria_consolidacion
                plan = memoria_consolidacion.consolidar(almacen, uid)
                resultado["consolidados"] = len(plan.get("consolidados", []))
                resultado["pasos"] += 1
                resultado["confianza"] = _reforzar_confianza(almacen)
        except Exception:
            pass
    with _bloqueo:
        _consolidando = False
    return resultado


def ejecutar_consolidacion_reposo(forzar=False):
    """Encola la consolidación en daemon; devuelve True si se lanzó."""
    global _consolidando, _ultima_consolidacion
    ahora = time.time()
    with _bloqueo:
        if _consolidando:
            return False
        if not forzar:
            if (ahora - _ultima_consolidacion) < _COOLDOWN_REPOSO_SEG:
                return False
            try:
                import ciclo_sueno_kaya
                if not ciclo_sueno_kaya.sueno_debido(_usuario(_app_registrada())):
                    return False
            except Exception:
                pass
        _consolidando = True
        _ultima_consolidacion = ahora
    app = _app_registrada()
    try:
        hilo = threading.Thread(
            target=_consolidar,
            args=(_usuario(app), _ruta_db(app), app),
            daemon=True, name="cerebro-consolidacion-reposo")
        hilo.start()
    except Exception:
        with _bloqueo:
            _consolidando = False
        return False
    return True


def notificar_actividad(origen=""):
    """Dispara reposo tras inactividad o tras un ciclo de varias intervenciones."""
    global _ultima_actividad, _turnos
    ahora = time.time()
    with _bloqueo:
        inactivo = bool(_ultima_actividad) and (ahora - _ultima_actividad) >= _REPOSO_SEG
        _ultima_actividad = ahora
        _turnos = 0 if inactivo else _turnos + 1
        disparar = inactivo or _turnos >= _UMBRAL_TURNOS
        if disparar:
            _turnos = 0
    return ejecutar_consolidacion_reposo() if disparar else False


def _tono(app):
    """Directriz emocional cacheada (evita SQLite en cada prompt)."""
    global _tono_cache
    ahora = time.time()
    with _bloqueo:
        texto, instante = _tono_cache
        if texto and (ahora - instante) < _CACHE_TONO_SEG:
            return texto
    try:
        texto = str(estado_emocional_kaya.resumen_estado_emocional(
            _usuario(app)) or "").strip()
    except Exception:
        texto = ""
    with _bloqueo:
        _tono_cache = (texto, ahora)
    return texto


def linea_estado_atencion():
    """Línea compacta para el prompt; ``''`` cuando no hay señal útil."""
    texto = _tono(_app_registrada())
    if not texto:
        return ""
    with _bloqueo:
        pausa = (time.time() - _ultima_atencion) < _COOLDOWN_ATENCION_SEG
    return (texto + (" (atención en pausa)" if pausa else ""))[:160]


def evaluar_atencion_proactiva(evento="", contexto=""):
    """Gatekeeper único: un cooldown, un tono y una entrega Live/Celeste."""
    global _ultima_atencion
    app = _app_registrada()
    ahora = time.time()
    with _bloqueo:
        if (ahora - _ultima_atencion) < _COOLDOWN_ATENCION_SEG:
            return False, "cooldown_atencion"
        if cerebro_proactivo.es_modo_privado(app):
            return False, "modo_privado"
        if cerebro_proactivo.es_modo_noche(app):
            return False, "modo_noche"
    tono = _tono(app)
    motivo = " ".join(str(evento or "").split())[:80]
    if contexto and motivo:
        motivo = (motivo + " " + " ".join(str(contexto).split()))[:80]
    # Cooldown forzado: el anti-spam único es este gate, no el motor heredado.
    try:
        autorizado, razon = iniciativa_unificada.puede_emitir(
            app, {"tipo": "gate", "mensaje": ""}, forzar=True)
    except Exception:
        autorizado, razon = False, "motor_no_disponible"
    if not autorizado:
        return False, razon
    entregado, detalle = False, "sin_aviso"
    try:
        entregado = bool(iniciativa_unificada.emitir(app))
        if entregado:
            detalle = "iniciativa_unificada"
    except Exception:
        detalle = "entrega_fallida"
    if not entregado:
        try:
            ok, _ = cerebro_proactivo.evaluar_proactividad(app, motivo=motivo or None)
            if ok:
                entregado, detalle = True, "proactivo"
        except Exception:
            pass
    with _bloqueo:
        if entregado:
            _ultima_atencion = time.time()
    texto = f"{detalle} | {tono}" if tono else detalle
    return entregado, texto[:200]


def reiniciar():
    """Limpia cooldowns y cachés."""
    global _consolidando, _ultima_consolidacion, _ultima_actividad
    global _turnos, _ultima_atencion, _tono_cache
    with _bloqueo:
        _consolidando = False
        _ultima_consolidacion = _ultima_actividad = _ultima_atencion = 0.0
        _turnos = 0
        _tono_cache = ("", 0.0)
    return True


__all__ = [
    "configurar_app", "ejecutar_consolidacion_reposo", "notificar_actividad",
    "linea_estado_atencion", "evaluar_atencion_proactiva", "reiniciar",
]
