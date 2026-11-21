"""Coordinador multimodal con datos protegidos."""
from __future__ import annotations
import threading
import time
from collections import deque
from multimodal_integracion_modelo import (ObservacionIntegrada,
    PoliticaIntegracionMultimodal, SituacionIntegrada, sanitizar_valor,
    confianza_valida)
from multimodal_correlacionador import CorrelacionadorMultimodal


class MotorIntegracionMultimodal:
    def __init__(self, politica=None, correlacionador=None, cerebro=None,
                 contexto_motor=None, iniciativa_contextual=None, app=None,
                 app_cola=None, orquestador=None):
        self._lock = threading.RLock()
        self.politica = politica or PoliticaIntegracionMultimodal()
        self.correlacionador = correlacionador or CorrelacionadorMultimodal(self.politica)
        self.cerebro, self.contexto_motor = cerebro, contexto_motor
        self.iniciativa, self.app, self.app_cola = iniciativa_contextual, app, app_cola
        self.orquestador = orquestador
        self._observaciones = deque(maxlen=self.politica.max_observaciones_historial)
        self._situaciones = deque(maxlen=self.politica.max_situaciones_historial)
        self._dedup = {}
        self._fallos = set()
        self._contexto_windows = {}

    def _purga(self, ahora=None):
        ahora = time.time() if ahora is None else ahora
        self._observaciones = deque((o for o in self._observaciones
            if ahora - o.timestamp <= min(o.ttl_seg, self.politica.ttl_observacion_seg)),
            maxlen=self.politica.max_observaciones_historial)
        ctx = next((o.datos_estructurados for o in reversed(self._observaciones)
                    if o.modalidad == "contexto"), {})
        self._contexto_windows = dict(ctx)
        self._dedup = {k: t for k, t in self._dedup.items()
                       if ahora - t <= self.politica.ventana_dedup_seg}

    def registrar_observacion(self, observacion, publicar=True, token_cancelacion=None):
        if token_cancelacion is not None:
            marca = getattr(token_cancelacion, "esta_cancelado", None)
            cancelado = bool(marca() if callable(marca) else marca)
            cancelado = cancelado or bool(getattr(token_cancelacion, "is_set", lambda: False)())
            if cancelado: raise InterruptedError("Integracion multimodal cancelada")
        if not isinstance(observacion, ObservacionIntegrada):
            raise TypeError("Se esperaba ObservacionIntegrada")
        with self._lock:
            self._purga()
            previo = self._dedup.get(observacion.huella_dedup)
            if previo is not None and abs(observacion.timestamp - previo) <= self.politica.ventana_dedup_seg:
                return None
            self._observaciones.append(observacion)
            self._observaciones = deque(sorted(self._observaciones,
                key=lambda o: o.timestamp), maxlen=self.politica.max_observaciones_historial)
            self._dedup[observacion.huella_dedup] = observacion.timestamp
            if observacion.modalidad == "contexto":
                self._contexto_windows = dict(observacion.datos_estructurados)
            situacion = self._consolidar()
            self._situaciones.append(situacion)
        if publicar:
            self._publicar(situacion)
        return situacion

    def _crear(self, modalidad, tipo, resumen, timestamp=None, etiquetas=(),
               datos=None, confianza=None, relevancia="baja", origen="", contexto=None):
        limpia = sanitizar_valor(datos or {}) or {}
        ctx = contexto or {k: limpia.get(k) for k in ("aplicacion", "hwnd") if limpia.get(k)}
        return ObservacionIntegrada(modalidad=modalidad, tipo_evento=tipo,
            resumen=resumen, timestamp=timestamp or time.time(),
            etiquetas_semanticas=tuple(etiquetas), datos_estructurados=limpia,
            nivel_confianza=confianza_valida(confianza), relevancia=relevancia,
            id_origen=origen, contexto_asociado=ctx,
            ttl_seg=self.politica.ttl_observacion_seg)

    def ingerir_vision(self, resultado):
        get = lambda k, d=None: getattr(resultado, k, d)
        resumen = get("descripcion", "") or get("a_resumen_cerebro", lambda: "")()
        hechos = list(get("observaciones_verificables", []) or [])
        tags = ["vision"] + [str(x).lower() for x in hechos[:8]]
        datos = {"descripcion": resumen, "observaciones": hechos,
                 "texto_extraido": get("texto_extraido", ""),
                 "elementos": [getattr(x, "nombre", "") for x in get("elementos_identificados", [])[:20]],
                 "sugerencia_accion": get("sugerencia_accion"),
                 "nivel_epistemico": "confirmado"}
        return self.registrar_observacion(self._crear("vision", "comprension_visual",
            resumen or "; ".join(hechos), get("timestamp"), tags, datos,
            get("nivel_confianza"), "media", get("id_entrada", "")))

    def ingerir_camara(self, resultado):
        get = lambda k, d=None: getattr(resultado, k, d)
        resumen = get("resumen_breve", "") or get("tipo_evento", "")
        datos = {"puntuacion_cambio": get("puntuacion_cambio"),
                 "detecciones": get("detecciones_locales", []),
                 "significativa": get("significativa", False),
                 "datos_evento": get("datos_sanitizados", {}),
                 "sugerencia_accion": get("sugerencia_accion"),
                 "nivel_epistemico": "confirmado" if get("puntuacion_cambio") is not None else "probable"}
        return self.registrar_observacion(self._crear("camara", "cambio_visual",
            resumen or "Cambio de cámara", get("timestamp"), ("camara", "cambio_visual"),
            datos, get("puntuacion_cambio"), "media", get("id_observacion", "")))

    def ingerir_interfaz(self, mapa, cambio=None):
        get = lambda k, d=None: getattr(mapa, k, d)
        alertas = get("alertas", [])
        textos = [getattr(a, "texto", "") for a in alertas[:12]]
        campos = []
        for e in get("elementos", [])[:30]:
            campos.append({"tipo": getattr(getattr(e, "tipo", ""), "value", getattr(e, "tipo", "")),
                "nombre": "***" if getattr(e, "es_sensible", False) else getattr(e, "nombre", ""),
                "valor": "***" if getattr(e, "es_sensible", False) else getattr(e, "valor", "")})
        app = get("aplicacion", "")
        datos = {"aplicacion": app, "hwnd": get("hwnd"), "alertas": textos,
                 "elementos": campos, "cambio": getattr(cambio, "ventana_cambio", False),
                 "sugerencia_accion": get("sugerencia_accion")}
        tags = ["interfaz", str(app).lower()] + ["alerta" for _ in textos]
        resumen = "; ".join(textos) or f"UI: {app or '?'}"
        datos["nivel_epistemico"] = "confirmado"
        return self.registrar_observacion(self._crear("interfaz", "mapa_interfaz",
            resumen, get("timestamp"), tags, datos, get("nivel_confianza"),
            "alta" if textos else "baja", get("id_mapa", "")))

    def ingerir_alerta_interfaz(self, alerta, contexto=None):
        texto = str(getattr(alerta, "texto", ""))
        datos = {"alerta": texto, "tipo": getattr(alerta, "tipo", "aviso"),
                 "nivel_epistemico": "confirmado"}
        return self.registrar_observacion(self._crear("interfaz", "alerta_interfaz",
            texto or "Alerta visual", time.time(), ("interfaz", "alerta"), datos,
            None, "alta", "alerta_ui", contexto or {}))

    def ingerir_cambio_interfaz(self, cambio, contexto=None):
        score = getattr(cambio, "puntuacion_cambio", None)
        datos = {"puntuacion_cambio": score,
                 "ventana_cambio": getattr(cambio, "ventana_cambio", False),
                 "alertas_nuevas": [getattr(a, "texto", "") for a in
                                    getattr(cambio, "alertas_nuevas", [])[:10]],
                 "nivel_epistemico": "confirmado"}
        return self.registrar_observacion(self._crear("interfaz", "cambio_interfaz",
            "Cambio interfaz", getattr(cambio, "timestamp", time.time()),
            ("interfaz", "cambio_visual"), datos, score, "media",
            "cambio_ui", contexto or {}))

    def ingerir_audio(self, evento):
        get = lambda k, d=None: getattr(evento, k, d)
        clas = get("clasificacion")
        categoria = getattr(getattr(clas, "categoria", "desconocido"), "value",
                            getattr(clas, "categoria", "desconocido"))
        if categoria in ("eco_silvestra", "ruido_ambiental") or get("relevancia", None) == "irrelevante":
            return None
        contexto = get("contexto_windows_asociado", {})
        datos = {"categoria": categoria, "energia_rms": get("energia_rms"),
                 "ratio_voz_vad": get("ratio_voz_vad"),
                 "repeticiones": get("repeticiones_recientes"),
                 "sugerencia_accion": get("sugerencia_accion"), **contexto}
        conf = getattr(clas, "confianza", None)
        resumen = f"Audio: {categoria}"
        datos["nivel_epistemico"] = "probable"
        tags = ["audio", str(categoria)]
        if categoria in ("alarma", "sirena", "timbre"):
            tags.append("alerta")
        return self.registrar_observacion(self._crear("audio", "evento_acustico",
            resumen, get("timestamp"), tags, datos,
            conf, getattr(get("relevancia", "baja"), "value", get("relevancia", "baja")),
            get("id_evento", ""), contexto))

    def ingerir_contexto_windows(self, contexto=None):
        if contexto is None:
            from contexto_windows import obtener_contexto_windows
            contexto = obtener_contexto_windows()
        ctx = sanitizar_valor(contexto) or {}
        ctx["nivel_epistemico"] = "confirmado"
        self._contexto_windows = ctx
        app = ctx.get("ejecutable") or ctx.get("titulo") or ""
        contexto_rel = {"aplicacion": app, "hwnd": ctx.get("hwnd")}
        return self.registrar_observacion(self._crear("contexto", "actividad_windows",
            f"App: {app}" if app else "Windows activo",
            ctx.get("timestamp"), ("windows", str(app).lower()) if app else ("windows",),
            ctx, None, "baja", "windows", contexto_rel))

    def registrar_fallo_modalidad(self, modalidad, detalle=""):
        with self._lock: self._fallos.add(str(modalidad))
    def recuperar_modalidad(self, modalidad):
        with self._lock: self._fallos.discard(str(modalidad))

    def _consolidar(self):
        obs = sorted(self._observaciones, key=lambda x: x.timestamp)
        correlaciones = self.correlacionador.correlacionar(obs)
        hechos = [o.resumen for o in obs
                  if o.resumen and o.datos_estructurados.get("nivel_epistemico") == "confirmado"]
        resumenes = [o.resumen for o in obs if o.resumen]
        resumen = " | ".join(resumenes[-8:])[:self.politica.max_resumen_cerebro_chars]
        atencion = any(o.relevancia in ("critica", "alta") for o in obs)
        propuesta = next((o.datos_estructurados.get("sugerencia_accion")
                          for o in reversed(obs)
                          if o.datos_estructurados.get("sugerencia_accion")), None)
        return SituacionIntegrada(resumen, hechos_confirmados=hechos,
            correlaciones_probables=correlaciones,
            modalidades_activas=list(dict.fromkeys(o.modalidad for o in obs)),
            modalidades_con_fallo=sorted(self._fallos),
            contexto_windows=dict(self._contexto_windows), requiere_atencion=atencion,
            sugerencia_accion=propuesta)

    def consultar_situacion_actual(self, pregunta=""):
        with self._lock:
            self._purga()
            situacion = self._consolidar()
            self._situaciones.append(situacion)
        respuesta = situacion.resumen_consolidado or "Sin observaciones vigentes."
        if situacion.correlaciones_probables:
            respuesta += " Posibles relaciones entre modalidades: " + str(len(situacion.correlaciones_probables)) + "."
        return {"respuesta": respuesta[:self.politica.max_resumen_cerebro_chars],
            "hechos_confirmados": list(situacion.hechos_confirmados),
            "correlaciones_probables": [c.hipotesis_correlacion for c in situacion.correlaciones_probables],
            "situacion": situacion}

    def _publicar(self, situacion):
        resumen = situacion.resumen_consolidado[:self.politica.max_resumen_cerebro_chars]
        if self.cerebro is not None:
            try: self.cerebro.historial.append({"role":"system", "content":"[MULTIMODAL] " + resumen})
            except Exception: pass
        if self.contexto_motor is not None:
            try: self.contexto_motor.confirmar_contexto("situacion_multimodal",
                {"hechos": situacion.hechos_confirmados}, origen="multimodal", ttl_seg=30)
            except Exception: pass
        if self.iniciativa is not None and self.app is not None:
            try: self.iniciativa.evaluar_oportunidad(app=self.app, contexto={
                "tema":"multimodal", "detalle":resumen, "requiere_atencion":situacion.requiere_atencion})
            except Exception: pass
        if self.app_cola is not None:
            try: self.app_cola.put_nowait(("multimodal_situacion", resumen))
            except Exception: pass
        if self.orquestador is not None and situacion.sugerencia_accion:
            try: self.orquestador.recibir(str(situacion.sugerencia_accion),
                origen="multimodal", requiere_ejecucion=False, modo="restringido")
            except Exception: pass
