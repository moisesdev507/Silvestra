"""Motor de iniciativa contextual para Silvestra (Etapa 5).

Evalúa el contexto situacional agregado por el Context Engine y decide de forma
prudente, no invasiva y cancelable cuándo iniciar interacción espontánea.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

COOLDOWN_GLOBAL_SEG = 900.0  # 15 min
COOLDOWN_RECORDATORIO_SEG = 1800.0  # 30 min
COOLDOWN_SESION_SEG = 2700.0  # 45 min
COOLDOWN_ACTIVIDAD_SEG = 1800.0  # 30 min
COOLDOWN_CASUAL_SEG = 2700.0  # 45 min

SILENCIO_MINIMO_USUARIO_SEG = 1200.0  # 20 min
UMBRAL_CONFIANZA_MINIMA = 0.65
UMBRAL_STALENESS_INICIATIVA_SEG = 20.0
MAX_HISTORIAL_SUGERENCIAS = 20


class SugerenciaIniciativa:
    """Sugerencia de interacción evaluada por el motor."""

    def __init__(
        self,
        id_sugerencia: str,
        tema: str,
        prioridad: str,
        prompt_orientacion: str,
        emocion_sugerida: str = "calida",
        firma_contexto: str = "",
        metadatos: Optional[dict[str, Any]] = None,
    ):
        self.id_sugerencia = id_sugerencia
        self.tema = tema
        self.prioridad = prioridad
        self.prompt_orientacion = prompt_orientacion
        self.emocion_sugerida = emocion_sugerida
        self.firma_contexto = firma_contexto
        self.metadatos = metadatos or {}
        self.estado = "pendiente"
        self.motivo_cancelacion = ""
        self.timestamp_creacion = time.time()
        self.timestamp_resolucion = 0.0

    def cancelar(self, motivo: str) -> None:
        self.estado = "cancelada"
        self.motivo_cancelacion = motivo
        self.timestamp_resolucion = time.time()

    def marcar_emitida(self) -> None:
        self.estado = "emitida"
        self.timestamp_resolucion = time.time()

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": self.id_sugerencia, "tema": self.tema, "prioridad": self.prioridad,
            "estado": self.estado, "motivo_cancelacion": self.motivo_cancelacion,
            "prompt_orientacion": self.prompt_orientacion, "emocion": self.emocion_sugerida,
            "timestamp_creacion": self.timestamp_creacion, "firma": self.firma_contexto,
        }


class MotorIniciativaContextual:
    """Evalúa el contexto situacional para originar iniciativa conversacional."""

    def __init__(self):
        self._bloqueo = threading.Lock()
        self._ultimo_exito_ts = 0.0
        self._ultima_interaccion_ts = time.time()
        self._cooldowns_por_tema: dict[str, float] = {}
        self._historial_firmas: list[str] = []
        self._sugerencia_pendiente: Optional[SugerenciaIniciativa] = None
        self._historial_sugerencias: list[SugerenciaIniciativa] = []
        self._contador = 0

    @property
    def ultimo_exito_ts(self) -> float:
        with self._bloqueo:
            return self._ultimo_exito_ts

    def registrar_interaccion_usuario(self, t_ahora: Optional[float] = None) -> None:
        ahora = time.time() if t_ahora is None else float(t_ahora)
        with self._bloqueo:
            self._ultima_interaccion_ts = ahora
            if self._sugerencia_pendiente and self._sugerencia_pendiente.estado == "pendiente":
                self._sugerencia_pendiente.cancelar("usuario_interactuo")
                self._sugerencia_pendiente = None

    def _generar_firma(self, tema: str, detalle: str, modo: str) -> str:
        return hashlib.md5(f"{tema}|{detalle}|{modo}".encode("utf-8")).hexdigest()

    def _en_cooldown_tema(self, tema: str, ahora: float, duracion: float) -> bool:
        return (ahora - self._cooldowns_por_tema.get(tema, 0.0)) < duracion

    def evaluar_oportunidad(
        self,
        app: Any,
        contexto: Optional[dict[str, Any]] = None,
        t_ahora: Optional[float] = None,
    ) -> Optional[SugerenciaIniciativa]:
        ahora = time.time() if t_ahora is None else float(t_ahora)
        if app is None or getattr(app, "descansando", False):
            return None
        if hasattr(app, "puede_hablar_sola") and not app.puede_hablar_sola():
            return None

        if hasattr(app, "estudio"):
            en_examen = getattr(app.estudio, "en_examen", lambda: False)()
            if en_examen or getattr(app.estudio, "timer_id", None) is not None:
                return None

        if not (7 <= time.localtime(ahora).tm_hour < 23):
            return None

        with self._bloqueo:
            if self._sugerencia_pendiente and self._sugerencia_pendiente.estado == "pendiente":
                return None
            if (ahora - self._ultima_interaccion_ts) < SILENCIO_MINIMO_USUARIO_SEG:
                return None
            if (ahora - self._ultimo_exito_ts) < COOLDOWN_GLOBAL_SEG:
                return None

        try:
            import naturalidad
            u_turno = getattr(naturalidad, "_ULTIMO_TURNO_TS", 0.0)
            if u_turno and (ahora - u_turno) < SILENCIO_MINIMO_USUARIO_SEG:
                return None
        except Exception:
            pass

        ctx = contexto
        if ctx is None:
            try:
                import contexto_motor
                ctx = contexto_motor.obtener_motor_contexto(app).obtener_contexto()
            except Exception:
                ctx = None

        if not ctx or not isinstance(ctx, dict):
            return None

        ts_ctx = float(ctx.get("timestamp", 0.0))
        if ts_ctx <= 0.0 or (ahora - ts_ctx) > UMBRAL_STALENESS_INICIATIVA_SEG:
            return None

        det = ctx.get("detectado", {})
        prob = ctx.get("probable", {})

        pres = det.get("presencia", {})
        if pres.get("activa", False) and pres.get("ausente", False):
            return None

        modo = det.get("modo_sistema", {}).get("modo", "normal")
        restringido = modo in ("estudio", "noche", "silencio", "concentracion")
        candidato: Optional[SugerenciaIniciativa] = None

        with self._bloqueo:
            # 1. ALTA: Recordatorios
            recs = det.get("recordatorios", {})
            if recs.get("total_pendientes", 0) > 0 and recs.get("proximos"):
                prox = recs["proximos"][0]
                t_rec, h_rec = str(prox.get("texto", "")).strip(), str(prox.get("hora", "")).strip()
                if t_rec and not self._en_cooldown_tema("recordatorio", ahora, COOLDOWN_RECORDATORIO_SEG):
                    firma = self._generar_firma("recordatorio", t_rec, modo)
                    if firma not in self._historial_firmas[-5:]:
                        self._contador += 1
                        prm = f"Recordatorio pendiente: '{t_rec}' ({h_rec}). Menciónalo amablemente."
                        candidato = SugerenciaIniciativa(
                            f"sug_{self._contador}", "recordatorio", "alta", prm, "atenta", firma,
                            {"recordatorio": t_rec, "hora": h_rec}
                        )

            # 2. MEDIA y BAJA
            if candidato is None and not restringido:
                ses = prob.get("sesion_continua", {})
                if ses.get("valor") is True and float(ses.get("confianza", 0.0)) >= UMBRAL_CONFIANZA_MINIMA:
                    if not self._en_cooldown_tema("sesion_continua", ahora, COOLDOWN_SESION_SEG):
                        firma = self._generar_firma("sesion_continua", "pausa", modo)
                        if firma not in self._historial_firmas[-3:]:
                            self._contador += 1
                            prm = "Lleva mucho rato continuo. Sugiere descansar la vista o tomar agua."
                            candidato = SugerenciaIniciativa(
                                f"sug_{self._contador}", "sesion_continua", "media", prm, "calida", firma
                            )

                if candidato is None:
                    act = prob.get("actividad", {})
                    v_act, c_act = str(act.get("valor", "")), float(act.get("confianza", 0.0))
                    if v_act in ("programando", "redaccion", "diseño") and c_act >= UMBRAL_CONFIANZA_MINIMA:
                        proy = prob.get("proyecto", {})
                        nom_p = proy.get("valor") if proy else ""
                        if not self._en_cooldown_tema("actividad_enfoque", ahora, COOLDOWN_ACTIVIDAD_SEG):
                            firma = self._generar_firma("actividad_enfoque", f"{v_act}:{nom_p}", modo)
                            if firma not in self._historial_firmas[-3:]:
                                self._contador += 1
                                ep = f" en {nom_p}" if nom_p else ""
                                prm = f"Enfocado{ep}. Comentario corto y cercano sobre cómo le va."
                                candidato = SugerenciaIniciativa(
                                    f"sug_{self._contador}", "actividad_enfoque", "media", prm, "curiosa", firma,
                                    {"actividad": v_act, "proyecto": nom_p}
                                )

                if candidato is None:
                    if not self._en_cooldown_tema("seguimiento_casual", ahora, COOLDOWN_CASUAL_SEG):
                        firma = self._generar_firma("seguimiento_casual", "silencio", modo)
                        if firma not in self._historial_firmas[-3:]:
                            self._contador += 1
                            prm = "Llevan rato en silencio. Pregunta o saluda en tono panameño amigable."
                            candidato = SugerenciaIniciativa(
                                f"sug_{self._contador}", "seguimiento_casual", "baja", prm, "calida", firma
                            )

            if candidato:
                self._sugerencia_pendiente = candidato
                self._historial_sugerencias.append(candidato)
                if len(self._historial_sugerencias) > MAX_HISTORIAL_SUGERENCIAS:
                    self._historial_sugerencias.pop(0)

        return candidato

    def revalidar_sugerencia(
        self,
        sug: SugerenciaIniciativa,
        app: Any,
        contexto_actual: Optional[dict[str, Any]] = None,
        t_ahora: Optional[float] = None,
    ) -> tuple[bool, str]:
        ahora = time.time() if t_ahora is None else float(t_ahora)
        with self._bloqueo:
            if sug.estado != "pendiente":
                return False, f"ya_{sug.estado}"

        if app is None:
            self._cancelar_interna(sug, "app_no_disponible")
            return False, "app_no_disponible"
        if getattr(app, "descansando", False):
            self._cancelar_interna(sug, "app_descansando")
            return False, "app_descansando"
        if hasattr(app, "puede_hablar_sola") and not app.puede_hablar_sola():
            self._cancelar_interna(sug, "usuario_ocupado")
            return False, "usuario_ocupado"

        ctx = contexto_actual
        if ctx is None:
            try:
                import contexto_motor
                ctx = contexto_motor.obtener_motor_contexto(app).obtener_contexto()
            except Exception:
                ctx = None

        if not ctx or not isinstance(ctx, dict):
            self._cancelar_interna(sug, "contexto_invalido")
            return False, "contexto_invalido"

        ts_ctx = float(ctx.get("timestamp", 0.0))
        if ts_ctx <= 0.0 or (ahora - ts_ctx) > UMBRAL_STALENESS_INICIATIVA_SEG:
            self._cancelar_interna(sug, "contexto_desactualizado")
            return False, "contexto_desactualizado"

        det = ctx.get("detectado", {})
        pres = det.get("presencia", {})
        if pres.get("activa", False) and pres.get("ausente", False):
            self._cancelar_interna(sug, "usuario_ausente")
            return False, "usuario_ausente"

        modo = det.get("modo_sistema", {}).get("modo", "normal")
        if modo in ("estudio", "noche", "silencio", "concentracion") and sug.prioridad != "alta":
            self._cancelar_interna(sug, "modo_restringido")
            return False, "modo_restringido"

        return True, "valida"

    def _cancelar_interna(self, sug: SugerenciaIniciativa, motivo: str) -> None:
        with self._bloqueo:
            sug.cancelar(motivo)
            if self._sugerencia_pendiente is sug:
                self._sugerencia_pendiente = None

    def marcar_emitida(self, sug: SugerenciaIniciativa, t_ahora: Optional[float] = None) -> None:
        ahora = time.time() if t_ahora is None else float(t_ahora)
        with self._bloqueo:
            sug.marcar_emitida()
            self._ultimo_exito_ts = ahora
            self._cooldowns_por_tema[sug.tema] = ahora
            if sug.firma_contexto:
                self._historial_firmas.append(sug.firma_contexto)
                if len(self._historial_firmas) > 30:
                    self._historial_firmas.pop(0)
            if self._sugerencia_pendiente is sug:
                self._sugerencia_pendiente = None

    def cancelar_pendiente(self, motivo: str = "manual") -> bool:
        with self._bloqueo:
            if self._sugerencia_pendiente and self._sugerencia_pendiente.estado == "pendiente":
                self._sugerencia_pendiente.cancelar(motivo)
                self._sugerencia_pendiente = None
                return True
            return False

    def obtener_estado_iniciativa(self, t_ahora: Optional[float] = None) -> dict[str, Any]:
        ahora = time.time() if t_ahora is None else float(t_ahora)
        with self._bloqueo:
            dt_g = max(0.0, ahora - self._ultimo_exito_ts) if self._ultimo_exito_ts > 0 else 9999.0
            rest = max(0.0, COOLDOWN_GLOBAL_SEG - dt_g)
            return {
                "ultimo_exito_ts": self._ultimo_exito_ts,
                "ultima_interaccion_ts": self._ultima_interaccion_ts,
                "en_cooldown_global": rest > 0,
                "segundos_cooldown_global": round(rest, 1),
                "sugerencia_pendiente": self._sugerencia_pendiente.a_dict() if self._sugerencia_pendiente else None,
                "historial_reciente": [s.a_dict() for s in self._historial_sugerencias[-5:]],
            }


_motor_iniciativa_instancia: Optional[MotorIniciativaContextual] = None
_motor_iniciativa_bloqueo = threading.Lock()


def obtener_motor_iniciativa() -> MotorIniciativaContextual:
    global _motor_iniciativa_instancia
    with _motor_iniciativa_bloqueo:
        if _motor_iniciativa_instancia is None:
            _motor_iniciativa_instancia = MotorIniciativaContextual()
        return _motor_iniciativa_instancia


def evaluar_oportunidad_iniciativa(
    app: Any,
    contexto: Optional[dict[str, Any]] = None,
    t_ahora: Optional[float] = None,
) -> Optional[SugerenciaIniciativa]:
    return obtener_motor_iniciativa().evaluar_oportunidad(app, contexto, t_ahora)


def obtener_estado_iniciativa(t_ahora: Optional[float] = None) -> dict[str, Any]:
    return obtener_motor_iniciativa().obtener_estado_iniciativa(t_ahora)


def cancelar_pendiente(motivo: str = "manual") -> bool:
    return obtener_motor_iniciativa().cancelar_pendiente(motivo)
