"""Motor de agregación y contexto situacional para Silvestra (Etapa 2).

Consolida la telemetría de Windows, presencia, modos, recordatorios, interacción,
memoria y tiempo en un modelo de certeza en 3 niveles: detectado, probable y confirmado.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

from contexto_reglas import (
    clasificar_actividad,
    evaluar_disponibilidad_usuario,
    evaluar_sesion_continua,
    extraer_proyecto_de_titulo,
    generar_contexto_temporal,
)


class MotorContexto:
    """Motor de contexto que agrega, infiere y expone el estado situacional."""

    def __init__(self, app: Any = None, sensor_windows: Any = None) -> None:
        self._app = app
        self._sensor_windows = sensor_windows
        self._bloqueo = threading.RLock()
        self._tiempo_inicio_motor = time.time()
        self._ultimo_estado: dict[str, Any] = {}
        self._ultimo_ts_actualizacion: float = 0.0
        self._ttl_cache_seg: float = 1.0
        self._confirmados: dict[str, dict[str, Any]] = {}
        self._hilo: threading.Thread | None = None
        self._evento_detener = threading.Event()
        self._intervalo_bucle: float = 2.0

    def iniciar(self, intervalo_seg: float = 2.0) -> None:
        """Inicia el hilo daemon para actualización periódica."""
        with self._bloqueo:
            if self._hilo and self._hilo.is_alive():
                return
            self._intervalo_bucle = max(0.5, float(intervalo_seg))
            self._evento_detener.clear()
            self._hilo = threading.Thread(
                target=self._bucle_actualizacion, daemon=True, name="MotorContextoDaemon"
            )
            self._hilo.start()

    def detener(self, timeout: float = 2.0) -> None:
        """Detiene de forma limpia el hilo en segundo plano."""
        with self._bloqueo:
            self._evento_detener.set()
            hilo = self._hilo
        if hilo and hilo.is_alive():
            hilo.join(timeout=max(0.1, float(timeout)))

    def _bucle_actualizacion(self) -> None:
        while not self._evento_detener.is_set():
            try:
                self.actualizar(forzar=True)
            except Exception:
                pass
            self._evento_detener.wait(self._intervalo_bucle)

    def confirmar_contexto(
        self, clave: str, valor: Any, origen: str = "usuario", ttl_seg: float | None = 3600.0
    ) -> None:
        """Establece un dato confirmado por el usuario con TTL opcional."""
        if not clave:
            return
        t_ahora = time.time()
        expira = (t_ahora + float(ttl_seg)) if ttl_seg is not None else None
        with self._bloqueo:
            self._confirmados[str(clave).strip()] = {
                "valor": valor,
                "origen": str(origen),
                "timestamp": t_ahora,
                "ttl_seg": ttl_seg,
                "expira": expira,
            }

    def limpiar_confirmado(self, clave: str | None = None) -> None:
        """Elimina una clave confirmada específica o todas si clave es None."""
        with self._bloqueo:
            if clave is None:
                self._confirmados.clear()
            else:
                self._confirmados.pop(str(clave).strip(), None)

    def _obtener_confirmados_vigentes(self) -> dict[str, dict[str, Any]]:
        t_ahora = time.time()
        with self._bloqueo:
            caducadas = [k for k, it in self._confirmados.items() if it.get("expira") and t_ahora >= it["expira"]]
            for k in caducadas:
                self._confirmados.pop(k, None)
            return {k: dict(v) for k, v in self._confirmados.items()}

    def _recopilar_windows(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            if self._sensor_windows is not None:
                ctx = self._sensor_windows.leer()
            else:
                from contexto_windows import obtener_contexto_windows
                ctx = obtener_contexto_windows()
            fuentes["windows"] = "ok" if ctx.get("disponible") else "no_disponible"
            return {
                "hwnd": ctx.get("hwnd"),
                "titulo": ctx.get("titulo") or "",
                "pid": ctx.get("pid"),
                "ejecutable": ctx.get("ejecutable") or "",
                "inactividad_seg": float(ctx.get("inactividad_seg", 0.0)),
            }
        except Exception:
            fuentes["windows"] = "error"
            return {"hwnd": None, "titulo": "", "pid": None, "ejecutable": "", "inactividad_seg": 0.0}

    def _recopilar_presencia(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            gestor = getattr(self._app, "presencia", None)
            if gestor:
                act = bool(getattr(gestor, "activa", False))
                aus = bool(getattr(gestor, "ausente", False))
                ult = float(getattr(gestor, "ult_persona", 0.0))
                fuentes["presencia"] = "ok"
                return {"activa": act, "ausente": aus, "segundos_sin_ver": round(time.time() - ult, 1) if ult > 0 else None}
            import estado
            d = estado.cargar()
            fuentes["presencia"] = "ok"
            return {"activa": bool(d.get("presencia_activa", False)), "ausente": False, "segundos_sin_ver": None}
        except Exception:
            fuentes["presencia"] = "no_disponible"
            return {"activa": False, "ausente": False, "segundos_sin_ver": None}

    def _recopilar_modo_sistema(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            import modos_sistema
            m = modos_sistema.obtener_modo_activo(self._app)
            lbl = modos_sistema.MODOS_CONFIG.get(m, {}).get("etiqueta", m)
            fuentes["modos_sistema"] = "ok"
            return {"modo": m, "etiqueta": lbl}
        except Exception:
            fuentes["modos_sistema"] = "error"
            return {"modo": "normal", "etiqueta": "Normal"}

    def _recopilar_recordatorios(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            import recordatorios
            datos = recordatorios._cargar()
            pends = [r for r in datos if not r.get("completado")]
            pends.sort(key=lambda r: float(r.get("timestamp", 0.0)))
            proxs = [{"texto": r.get("texto", ""), "hora": r.get("hora_exacta", "")} for r in pends[:3]]
            fuentes["recordatorios"] = "ok"
            return {"total_pendientes": len(pends), "proximos": proxs}
        except Exception:
            fuentes["recordatorios"] = "error"
            return {"total_pendientes": 0, "proximos": []}

    def _recopilar_interaccion(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            t_nat, pista = 0.0, ""
            try:
                import naturalidad
                t_nat = float(getattr(naturalidad, "_ULTIMO_TURNO_TS", 0.0))
                pista = naturalidad.obtener_pista_continuidad()
            except Exception:
                pass
            ini = getattr(self._app, "iniciativa", None)
            t_ini = float(getattr(ini, "ultima_interaccion_usuario", 0.0)) if ini else 0.0
            t_ult = max(t_nat, t_ini)
            fuentes["interaccion"] = "ok"
            return {
                "segundos_desde_ultima": round(time.time() - t_ult, 1) if t_ult > 0 else None,
                "pista_continuidad": pista,
            }
        except Exception:
            fuentes["interaccion"] = "error"
            return {"segundos_desde_ultima": None, "pista_continuidad": ""}

    def _recopilar_memoria(self, fuentes: dict[str, str]) -> dict[str, Any]:
        try:
            mem = getattr(self._app, "memoria", None)
            if mem is None:
                import memoria
                mem = getattr(memoria, "_memoria_instancia", None)
            if mem is not None:
                fuentes["memoria"] = "ok"
                return {"total_hechos": len(getattr(mem, "hechos", [])), "creador": getattr(mem, "creador", "Moisés")}
            fuentes["memoria"] = "no_disponible"
            return {"total_hechos": 0, "creador": "Moisés"}
        except Exception:
            fuentes["memoria"] = "error"
            return {"total_hechos": 0, "creador": "Moisés"}

    def _recopilar_temporal(self) -> dict[str, Any]:
        return generar_contexto_temporal(self._tiempo_inicio_motor)

    def actualizar(self, forzar: bool = False) -> dict[str, Any]:
        """Recopila sensores, genera inferencias y actualiza el estado consolidado."""
        t_ahora = time.time()
        with self._bloqueo:
            if not forzar and self._ultimo_estado and (t_ahora - self._ultimo_ts_actualizacion < self._ttl_cache_seg):
                return copy.deepcopy(self._ultimo_estado)

        fuentes: dict[str, str] = {}
        win = self._recopilar_windows(fuentes)
        pres = self._recopilar_presencia(fuentes)
        modo = self._recopilar_modo_sistema(fuentes)
        recs = self._recopilar_recordatorios(fuentes)
        inter = self._recopilar_interaccion(fuentes)
        memo = self._recopilar_memoria(fuentes)
        temp = self._recopilar_temporal()

        detectado = {
            "fuentes_estado": fuentes,
            "ventana": win,
            "inactividad_seg": win.get("inactividad_seg", 0.0),
            "presencia": pres,
            "modo_sistema": modo,
            "recordatorios": recs,
            "interaccion": inter,
            "memoria": memo,
            "temporal": temp,
            "timestamp": t_ahora,
        }

        exe, tit = win.get("ejecutable", ""), win.get("titulo", "")
        inact, aus_pres = float(win.get("inactividad_seg", 0.0)), bool(pres.get("ausente", False))

        act = clasificar_actividad(exe, tit, inact, aus_pres)
        proy = extraer_proyecto_de_titulo(tit, exe)
        ses_cont = evaluar_sesion_continua(temp["sesion_seg"], inact)
        disp = evaluar_disponibilidad_usuario(inact, modo.get("modo", "normal"), act.get("valor", ""))

        consolidado = {
            "detectado": detectado,
            "probable": {
                "actividad": act,
                "proyecto": proy,
                "sesion_continua": ses_cont,
                "disponibilidad_usuario": disp,
            },
            "confirmado": self._obtener_confirmados_vigentes(),
            "timestamp": t_ahora,
        }

        with self._bloqueo:
            self._ultimo_estado = consolidado
            self._ultimo_ts_actualizacion = t_ahora
            return copy.deepcopy(self._ultimo_estado)

    def obtener_contexto(self) -> dict[str, Any]:
        """Retorna una copia segura del último contexto situacional consolidado."""
        with self._bloqueo:
            if not self._ultimo_estado:
                return self.actualizar(forzar=True)
            return copy.deepcopy(self._ultimo_estado)

    def resumen_compacto(self) -> str:
        """Devuelve una síntesis textual estructurada en los 3 niveles de certeza."""
        ctx = self.obtener_contexto()
        det, prob, conf = ctx.get("detectado", {}), ctx.get("probable", {}), ctx.get("confirmado", {})
        win, temp = det.get("ventana", {}), det.get("temporal", {})
        modo, recs = det.get("modo_sistema", {}), det.get("recordatorios", {})
        pres, inter = det.get("presencia", {}), det.get("interaccion", {})

        exe_str = win.get("ejecutable") or "ninguno"
        tit_str = f' ("{win.get("titulo")}")' if win.get("titulo") else ""
        inact_str = f"{round(win.get('inactividad_seg', 0.0), 1)}s"

        lineas = [
            "[DETECTADO]",
            f"- Ventana: {exe_str}{tit_str} | Inactividad: {inact_str}",
            f"- Temporal: {temp.get('dia_semana', '')} {temp.get('hora', '')} ({temp.get('franja', '')}) | "
            f"Modo: {modo.get('modo', 'normal')} | Recordatorios: {recs.get('total_pendientes', 0)} pend.",
        ]
        if pres.get("activa"):
            lineas.append(f"- Presencia: {'ausente' if pres.get('ausente') else 'presente'}")
        if inter.get("segundos_desde_ultima") is not None:
            lineas.append(f"- Interacción: hace {inter.get('segundos_desde_ultima')}s")

        lineas.append("[PROBABLE]")
        act = prob.get("actividad", {})
        lineas.append(f"- Actividad: {act.get('valor', 'desconocida')} (conf: {act.get('confianza', 0.0):.2f}, regla: {act.get('regla', '')})")
        proy = prob.get("proyecto")
        if proy:
            lineas.append(f"- Proyecto: {proy.get('valor')} (conf: {proy.get('confianza', 0.0):.2f}, regla: {proy.get('regla', '')})")
        disp = prob.get("disponibilidad_usuario", {})
        lineas.append(f"- Disponibilidad: {disp.get('valor', 'desconocida')} (conf: {disp.get('confianza', 0.0):.2f}, regla: {disp.get('regla', '')})")

        lineas.append("[CONFIRMADO]")
        if not conf:
            lineas.append("- (ninguno)")
        else:
            ahora = time.time()
            for k, it in conf.items():
                exp = it.get("expira")
                exp_s = f", expira en {int(exp - ahora)}s" if exp else ""
                lineas.append(f"- {k}: {it.get('valor')!r} (origen: {it.get('origen', 'usuario')}{exp_s})")

        return "\n".join(lineas)


_motor_instancia: MotorContexto | None = None
_motor_bloqueo = threading.RLock()


def obtener_motor_contexto(app: Any = None) -> MotorContexto:
    """Retorna la instancia global del motor de contexto situacional."""
    global _motor_instancia
    with _motor_bloqueo:
        if _motor_instancia is None:
            _motor_instancia = MotorContexto(app=app)
        elif app is not None and _motor_instancia._app is None:
            _motor_instancia._app = app
        return _motor_instancia


def obtener_contexto_actual(app: Any = None) -> dict[str, Any]:
    """Función de conveniencia para obtener el contexto situacional consolidado."""
    return obtener_motor_contexto(app).obtener_contexto()


def resumen_contexto_compacto(app: Any = None) -> str:
    """Función de conveniencia para obtener el resumen textual estructurado."""
    return obtener_motor_contexto(app).resumen_compacto()
