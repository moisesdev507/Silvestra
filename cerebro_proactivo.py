"""Motor de Proactividad Situacional Inteligente para Silvestra / Lyris.

Implementa iniciativa oportuna con guardarraíles estrictos anti-interrupción:
- Respeta modo Privado (bloqueo total).
- No interrumpe turnos activos (habla, escucha o flujo en curso).
- Enfriamiento mínimo de >= 15 minutos entre avisos.
- Respeta modo Noche (solo sugerencias suaves de descanso/respaldo).

Reglas situacionales:
1. Briefing ejecutivo diario (máx. 1 vez al día, <= 25 palabras).
2. Contexto de proyecto al cambiar de ventana hacia entornos de desarrollo.
3. Cuidado nocturno del dueño entre 01:30 y 04:30 (máx. 1 vez por madrugada).
"""
import datetime
import os
import re
import threading
import time

_bloqueo = threading.RLock()
COOLDOWN_MINIMO_SEGUNDOS = 15 * 60  # 15 minutos


def es_modo_privado(app=None):
    """Verifica si el modo privado está activo en app, ecosistema o estado.json."""
    if app:
        if getattr(app, "modo_privado", False):
            return True
        eco = getattr(app, "ecosistema_gestor", None)
        if eco and hasattr(eco, "modo_privado"):
            try:
                if eco.modo_privado():
                    return True
            except Exception:
                pass
    try:
        import estado
        est = estado.cargar()
        if est.get("modo_privado", False) or est.get("preferencias", {}).get("modo_privado", False):
            return True
    except Exception:
        pass
    return False


def es_modo_noche(app=None):
    """Verifica si el modo operativo actual es noche."""
    try:
        import modos_sistema
        return modos_sistema.obtener_modo_activo(app) == "noche"
    except Exception:
        return False


def turno_activo(app=None):
    """Detecta si Lyris está hablando, escuchando o en medio de un turno de conversación."""
    if not app:
        return False
    if getattr(app, "hablando", False) or getattr(app, "escuchando", False):
        return True
    if getattr(app, "conversacion", False) and getattr(app, "silencios", 0) == 0:
        return True
    if getattr(app, "flujo", None) is not None:
        return True
    return False


class MotorProactivo:
    """Motor de proactividad situacional con reglas cognitivas y telemetría."""

    def __init__(self):
        self.ultimo_aviso = 0.0
        self.ultimo_briefing_fecha = None
        self.ultimo_aviso_nocturno_fecha = None
        self.proyectos_comentados_sesion = set()

    def reiniciar(self):
        """Restablece los marcadores temporales (útil para pruebas unitarias)."""
        with _bloqueo:
            self.ultimo_aviso = 0.0
            self.ultimo_briefing_fecha = None
            self.ultimo_aviso_nocturno_fecha = None
            self.proyectos_comentados_sesion.clear()

    def puede_intervenir(self, app=None, forzar_cooldown=False):
        """Evalúa si se cumplen los guardarraíles para hablar de forma espontánea."""
        if es_modo_privado(app):
            return False, "modo_privado"

        if turno_activo(app):
            return False, "turno_activo"

        ahora = time.time()
        if not forzar_cooldown and (ahora - self.ultimo_aviso) < COOLDOWN_MINIMO_SEGUNDOS:
            return False, "cooldown_activo"

        return True, "ok"

    def _obtener_resumen_recordatorios(self):
        """Devuelve el total de recordatorios pendientes futuros."""
        try:
            import recordatorios
            items = recordatorios._cargar()
            ahora_ts = time.time()
            pendientes = [it for it in items if not it.get("completado") and it.get("timestamp", 0) > ahora_ts]
            return len(pendientes)
        except Exception:
            return 0

    def _obtener_proyecto_grafo(self, creador="Moisés"):
        """Busca el proyecto o trabajo principal registrado en el grafo de conocimiento."""
        try:
            import cerebro_grafo
            relaciones = cerebro_grafo.consultar_relaciones(creador, limite=10)
            for r in relaciones:
                rel = r.get("relacion", "").lower()
                if rel in ("trabaja_en", "proyecto", "desarrolla", "estudia"):
                    return r.get("objeto")
        except Exception:
            pass
        return "Proyecto Silvestra"

    def evaluar_briefing_diario(self, app=None, forzar=False):
        """Genera el briefing ejecutivo diario (máx. 1 vez al día, <= 25 palabras)."""
        hoy_str = datetime.date.today().isoformat()
        if not forzar and self.ultimo_briefing_fecha == hoy_str:
            return None

        creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
        n_rec = self._obtener_resumen_recordatorios()
        proyecto = self._obtener_proyecto_grafo(creador)

        if n_rec > 0:
            rec_str = f"Tienes {n_rec} recordatorios pendientes"
        else:
            rec_str = "No tienes recordatorios pendientes"

        saludo = f"Buenos días, {creador}. {rec_str} y seguimos con {proyecto}. ¿En qué avanzamos?"
        palabras = saludo.split()
        if len(palabras) > 25:
            saludo = " ".join(palabras[:25])

        self.ultimo_briefing_fecha = hoy_str
        return saludo, "alegre"

    def evaluar_cuidado_nocturno(self, app=None, forzar=False):
        """Sugiere descanso o respaldo si hay actividad prolongada entre 01:30 y 04:30."""
        hoy_str = datetime.date.today().isoformat()
        if not forzar and self.ultimo_aviso_nocturno_fecha == hoy_str:
            return None

        ahora_dt = datetime.datetime.now()
        hora_dec = ahora_dt.hour + ahora_dt.minute / 60.0

        if not forzar and not (1.5 <= hora_dec <= 4.5):
            return None

        creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
        msg = f"{creador}, son pasadas de las dos de la madrugada. Recuerda guardar tus avances y descansar un rato."
        self.ultimo_aviso_nocturno_fecha = hoy_str
        return msg, "calida"

    def evaluar_cambio_ventana(self, app=None, ventana=None, forzar=False):
        """Ofrece contexto si el usuario cambia a un entorno de desarrollo registrado."""
        if not ventana or not isinstance(ventana, dict):
            return None

        ejec = str(ventana.get("ejecutable") or "").lower()
        tit = str(ventana.get("titulo") or "").lower()

        es_dev = False
        if any(ide in ejec for ide in ("code.exe", "antigravity.exe", "devenv.exe", "pycharm", "idea")):
            es_dev = True
        elif any(web in tit for web in ("supabase", "netlify", "github", "gitlab", "antigravity")):
            es_dev = True

        if not es_dev:
            return None

        creador = getattr(getattr(app, "memoria", None), "creador", "Moisés") or "Moisés"
        proyecto = self._obtener_proyecto_grafo(creador)
        clave_proy = proyecto.lower()

        if not forzar and clave_proy in self.proyectos_comentados_sesion:
            return None

        self.proyectos_comentados_sesion.add(clave_proy)
        msg = f"Detecté tu entorno de desarrollo. ¿Deseas que revisemos los pendientes de {proyecto}?"
        return msg, "atenta"

    def evaluar_oportunidad(self, app=None, motivo=None, ventana=None, forzar_cooldown=False):
        """Evalúa todas las reglas de proactividad y devuelve (mensaje, emocion) si aplica."""
        with _bloqueo:
            puede, razon = self.puede_intervenir(app, forzar_cooldown=forzar_cooldown)
            if not puede:
                return None

            es_noche = es_modo_noche(app)

            # En modo noche, únicamente se permite el cuidado nocturno
            if es_noche:
                res_nocturno = self.evaluar_cuidado_nocturno(app, forzar=forzar_cooldown)
                if res_nocturno:
                    self.ultimo_aviso = time.time()
                    return res_nocturno
                return None

            # 1. Regla ante cambio de ventana
            if motivo == "ventana" and ventana:
                res_v = self.evaluar_cambio_ventana(app, ventana, forzar=forzar_cooldown)
                if res_v:
                    self.ultimo_aviso = time.time()
                    return res_v

            # 2. Regla de cuidado nocturno
            res_noc = self.evaluar_cuidado_nocturno(app, forzar=forzar_cooldown)
            if res_noc:
                self.ultimo_aviso = time.time()
                return res_noc

            # 3. Regla de briefing diario
            res_brief = self.evaluar_briefing_diario(app, forzar=forzar_cooldown)
            if res_brief:
                self.ultimo_aviso = time.time()
                return res_brief

            return None


_motor_global = MotorProactivo()


def obtener_motor_proactivo():
    """Devuelve la instancia singleton del motor proactivo."""
    return _motor_global


def evaluar_proactividad(app=None, motivo=None, ventana=None, forzar_cooldown=False):
    """Punto de entrada seguro y no bloqueante para evaluar y emitir proactividad."""
    try:
        motor = obtener_motor_proactivo()
        res = motor.evaluar_oportunidad(app=app, motivo=motivo, ventana=ventana, forzar_cooldown=forzar_cooldown)
        if res:
            mensaje, emocion = res
            if hasattr(app, "cola") and app.cola:
                app.cola.put(("hablar", (mensaje, emocion)))
            return True, mensaje
    except Exception as e:
        print(f"[proactividad] Error evaluando oportunidad: {e}", flush=True)
    return False, ""
