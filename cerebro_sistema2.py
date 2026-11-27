"""Sistema 2 del Cerebro Único: planes multipaso en segundo plano.

No toca Qt, el hilo de audio ni el bucle principal. El resultado se entrega
al final mediante ``SesionKayaLive.enviar_texto`` o por la cola de voz.
"""
import itertools
import os
import threading
import time

import cerebro_planificador
import cerebro_unico
import memoria_razonamiento
import memoria_unificada
import persistencia_segura

_bloqueo = threading.RLock()
_app = None
_tareas = {}
_contador = itertools.count(1)
MAX_RECIENTES = 6
RUTA_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado_sistema2.json")


def configurar_app(app):
    """Registra la app viva para entregar el resultado al motor activo."""
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


def _cortar(valor, limite):
    return str(valor or "").strip()[:limite]


def _publicar_estado(tarea_id, **cambios):
    with _bloqueo:
        tarea = _tareas.setdefault(str(tarea_id), {"id": str(tarea_id)})
        tarea.update(cambios)
        copia = dict(tarea)
        valores = [dict(x) for x in _tareas.values()]
    try:
        recientes = sorted(valores, key=lambda x: str(x.get("id", "")))[-20:]
        persistencia_segura.guardar_json_atomico(
            RUTA_ESTADO, {"tareas": recientes, "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass
    return copia


def estado_tareas_sistema2():
    """Estado breve de tareas en curso y recién terminadas."""
    with _bloqueo:
        valores = [dict(x) for x in _tareas.values()]
    activas = [
        {"id": x.get("id", ""), "estado": "en_curso", "objetivo": _cortar(x.get("objetivo"), 70)}
        for x in valores if x.get("estado") == "en_curso"
    ]
    recientes = [
        {"id": x.get("id", ""), "estado": x.get("estado", ""), "origen": x.get("origen", "live"),
         "objetivo": _cortar(x.get("objetivo"), 70), "resultado": _cortar(x.get("resultado"), 180)}
        for x in reversed(valores)
        if x.get("estado") in ("completada", "con_aviso", "error")
    ][:MAX_RECIENTES]
    return {"activas": activas, "recientes": recientes}


def _razonar(objetivo, contexto_extra, resultado):
    """Contraste local con memoria y cerebro único; nunca llama a endpoints /v1/."""
    try:
        gestor = memoria_unificada._principal()
        if gestor is None or not hasattr(gestor, "almacen"):
            return ""
        base = cerebro_unico.compilar_contexto_unico(objetivo, max_chars=500, estable=True)
        consulta = "\n".join(x for x in (
            f"Objetivo: {_cortar(objetivo, 400)}",
            f"Resultado verificado: {_cortar(resultado, 500)}",
            _cortar(contexto_extra, 300), _cortar(base, 500),
        ) if x)
        informe = memoria_razonamiento.razonar(gestor, consulta, limite=6)
        return memoria_razonamiento.formatear(informe, 260).strip()
    except Exception:
        return ""


def _entregar_cola(coordinador, texto, app=None):
    """Fallback de voz cuando Gemini Live no está activo."""
    if app is None:
        app = getattr(coordinador, "app", None) or _app_registrada()
    cola = getattr(app, "cola", None)
    if cola is None:
        return False
    try:
        cola.put(("hablar", str(texto)))
        return True
    except Exception:
        return False


def _entregar_live_seguro(coordinador, texto, app=None):
    """Inyecta el resultado en la sesión viva; si no hay, cae a la cola de voz."""
    mensaje = str(texto or "").strip()
    if not mensaje:
        return False
    sesion = None
    try:
        import live_motor
        sesion = live_motor.sesion_activa()
    except Exception:
        pass
    if sesion is None and coordinador is not None:
        candidata = getattr(coordinador, "sesion_live", None)
        if getattr(candidata, "activo", False):
            sesion = candidata
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
        except Exception:
            pass
        try:
            if bool(sesion.enviar_texto(mensaje)):
                return True
        except Exception:
            pass
    return _entregar_cola(coordinador, mensaje, app=app)


def _trabajo(tarea_id, objetivo, origen, contexto_extra):
    app = _app_registrada()
    estado, final = "error", ""
    try:
        pasos = cerebro_planificador.descomponer_en_pasos(objetivo, contexto_extra)
        if not pasos:
            raise ValueError("sin_pasos")
        _publicar_estado(tarea_id, pasos=len(pasos))
        resultados = cerebro_planificador.ejecutar_plan_multipaso(pasos, app=app)
        sintesis = cerebro_planificador.verificar_coherencia_y_sintetizar(pasos, resultados)
        final = " ".join(x for x in (sintesis, _razonar(objetivo, contexto_extra, sintesis)) if x).strip()
        completo = bool(resultados) and all(bool(ok) for _, ok, _ in resultados)
        estado = "completada" if completo else "con_aviso"
        _publicar_estado(tarea_id, estado=estado, resultado=final, completo=completo,
                         pasos_ejecutados=len(resultados))
    except Exception as exc:
        final = f"No pude completar el plan en segundo plano: {type(exc).__name__}."
        _publicar_estado(tarea_id, estado="error", resultado=final, completo=False,
                         error=type(exc).__name__)
    try:
        memoria_unificada.recordar(
            f"Plan S2 [{tarea_id}] {estado}: {_cortar(final, 160)}",
            texto_usuario=f"[{origen}] {objetivo}", canal=origen,
            fuente="sistema2", tarea_id=tarea_id, estado=estado,
        )
    except Exception:
        pass
    try:
        coordinador = getattr(app, "coordinador_live", None)
        entregado = _entregar_live_seguro(coordinador, final, app=app)
        _publicar_estado(tarea_id, entregado=bool(entregado))
    except Exception:
        _publicar_estado(tarea_id, entregado=False)


def lanzar_tarea_sistema2(objetivo, origen="live", contexto_extra=""):
    """Lanza el plan en un hilo daemon y devuelve de inmediato."""
    texto = str(objetivo or "").strip()
    if not texto:
        return {"aceptado": False, "id": "", "motivo": "objetivo_vacio"}
    tarea_id = f"s2-{next(_contador)}"
    origen = str(origen or "live")
    with _bloqueo:
        _tareas[tarea_id] = {
            "id": tarea_id, "estado": "en_curso", "objetivo": texto,
            "origen": origen, "contexto_extra": _cortar(contexto_extra, 300),
            "resultado": "",
        }
    _publicar_estado(tarea_id, estado="en_curso")
    threading.Thread(
        target=_trabajo, args=(tarea_id, texto, origen, str(contexto_extra or "")),
        name=f"cerebro-s2-{tarea_id}", daemon=True,
    ).start()
    return {"aceptado": True, "id": tarea_id, "estado": "en_curso"}


__all__ = [
    "configurar_app", "lanzar_tarea_sistema2", "estado_tareas_sistema2",
    "_entregar_live_seguro", "_razonar",
]
