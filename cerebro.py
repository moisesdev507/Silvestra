"""Coordinador del cerebro de Silvestra, historial de diálogo y reflexión."""
import re
import time
import unicodedata

from config import MODELOS
from cerebro_parser import separar, _respuesta_parcial, _cortar
from cerebro_prompt import (
    DIAS,
    MESES,
    SOBRE_MI,
    cargar_alma,
    obtener_hora_local,
    construir_prompt,
)


def ahora_texto():
    """Devuelve la fecha y hora local del sistema."""
    return obtener_hora_local()


class Cerebro:
    def __init__(self, cliente, memoria, app=None):
        self.cliente = cliente
        self.memoria = memoria
        self.app = app
        self.historial = []
        self.modelos = list(MODELOS)
        self.ultima_reflexion = 0.0
        self._seguimiento_visual_pendiente = False

    def reiniciar(self):
        self.historial = []

    def _podar_historial(self):
        if len(self.historial) > 16:
            self.historial = self.historial[-10:]

    def _obtener_historial_podado(self):
        """Devuelve los últimos 4 turnos recortando respuestas largas para no inflar tokens."""
        hist_reciente = self.historial[-4:]
        hist_podado = []
        for h in hist_reciente:
            c = h.get("content", "")
            if h.get("role") == "assistant" and len(c) > 150:
                c = c[:150].rsplit(" ", 1)[0] + "..."
            hist_podado.append({"role": h.get("role"), "content": c})
        return hist_podado

    def instrucciones(self, texto_actual=None):
        es_invitado = bool(getattr(self, "turno_invitado", False))
        app = getattr(self, "app", None)
        puente = getattr(app, "sistema_multimodal", None) if app else None
        pregunta = str(texto_actual or "").strip().lower()
        normal = unicodedata.normalize("NFKD", pregunta).encode("ascii", "ignore").decode("ascii")
        normal = " ".join(re.sub(r"[^a-z0-9 ]", " ", normal).split())
        visual = any(x in normal for x in (
            "pantalla", "ventana", "aplicacion", "archivo", "cambie", "cambio",
            "donde estoy", "que tengo", "ahora que", "a que parte", "a que ventana",
            "que estoy viendo", "que ves"))
        seguimiento = self._seguimiento_visual_pendiente and len(pregunta) <= 70
        consulta = visual or seguimiento or any(x in normal for x in (
            "sonido", "audio", "situacion", "que pasa"))
        contexto_adicional = ""
        datos_multimodales = {}
        contexto_engine = paquete_memoria = None
        if puente is not None and consulta:
            try:
                datos = puente.consultar_entorno_actual(texto_actual) or {}
                datos_multimodales = datos
                ventana = datos.get("ventana") or {}
                proceso = ventana.get("ejecutable") or "no disponible"
                titulo = ("omitido por privacidad" if ventana.get("titulo_omitido")
                          else ventana.get("titulo") or "no disponible")
                contexto_adicional = ("[ESTADO ACTUAL EN VIVO DE WINDOWS]\n"
                    + f'Aplicación activa en Windows: {proceso} | Ventana: "{titulo}"'
                    + "\n[FIN ESTADO ACTUAL EN VIVO DE WINDOWS]\n"
                    + "Contexto multimodal reciente, evidencia observada: ventana externa: "
                    + str(ventana.get("titulo", "sin ventana externa conocida"))
                    + "; audio: " + str(datos.get("audio", "sin datos recientes"))
                    + "; situación: " + str(datos.get("situacion", "sin interpretación"))
                    + "; pantalla: " + str(datos.get("captura_pantalla", "no consultada"))
                    + "\nDistingue hechos de hipótesis. No afirmes causalidad ni inventes detalles visuales; "
                    "explica si faltan permisos, captura o datos.")
                contexto_adicional = contexto_adicional[:1100]
                self._seguimiento_visual_pendiente = visual or seguimiento
            except Exception:
                contexto_adicional = "Contexto multimodal no disponible; no infieras datos del entorno."
                self._seguimiento_visual_pendiente = False
        else:
            self._seguimiento_visual_pendiente = False
        from planificacion_motor import es_solicitud_explicita
        solicitud_plan = es_solicitud_explicita(texto_actual)
        if (len(pregunta) >= 18 or solicitud_plan) and not es_invitado and hasattr(self.memoria, "razonar"):
            try:
                import contexto_motor
                contexto_engine = contexto_motor.obtener_motor_contexto(app).obtener_contexto()
                resultado = self.memoria.razonar(texto_actual, contexto_engine=contexto_engine,
                    multimodal=datos_multimodales or None)
                paquete_memoria = resultado.get("recuperacion")
                from razonamiento_motor import razonar, formatear
                coordinador = getattr(self, "integracion_cognitiva", None) or getattr(app, "integracion_cognitiva", None)
                experiencias = []
                if coordinador:
                    experiencias = coordinador.experiencias.recuperar(texto_actual, 4)
                elif hasattr(self.memoria, "almacen"):
                    try:
                        from experiencia_motor import MotorExperiencias
                        motor_exp = getattr(self, "_motor_experiencias", None)
                        if motor_exp is None or motor_exp.usuario_id != self.memoria.usuario_id:
                            motor_exp = MotorExperiencias(self.memoria.almacen, self.memoria.usuario_id)
                            self._motor_experiencias = motor_exp
                        experiencias = motor_exp.recuperar(texto_actual, 4)
                    except Exception:
                        experiencias = []
                cognicion = razonar(texto_actual, resultado_memoria=resultado,
                    aprendizajes_experienciales=experiencias)
                resumen = formatear(cognicion, 900)
                if resumen:
                    contexto_adicional = (contexto_adicional + "\n" + resumen).strip()[:1800]
                from planificacion_motor import PlanificacionMotor, formatear as formatear_plan
                if solicitud_plan:
                    motor = coordinador.planificacion if coordinador else getattr(self, "_motor_planificacion", None)
                    if not coordinador and (motor is None or motor.usuario_id != self.memoria.usuario_id):
                        motor = PlanificacionMotor(self.memoria.almacen, self.memoria.usuario_id)
                        self._motor_planificacion = motor
                    contexto_plan = dict(contexto_engine or {})
                    contexto_plan["multimodal"] = datos_multimodales or {}
                    contexto_plan["aprendizajes_experienciales"] = experiencias
                    plan = motor.crear_plan(texto_actual, cognicion, contexto_plan,
                        self, token_cancelacion=getattr(self, "token_cancelacion", None))
                    contexto_adicional = (contexto_adicional + "\n" + formatear_plan(plan)).strip()[:2800]
            except Exception as exc:
                print(f"[cerebro] razonamiento de memoria no disponible ({type(exc).__name__})", flush=True)
        return construir_prompt(self.memoria, texto_actual, self._obtener_historial_podado(),
            es_invitado=es_invitado, contexto_adicional=contexto_adicional,
            paquete_memoria=paquete_memoria, contexto_engine=contexto_engine)

    def _pedir(self, mensajes, tarea="charla"):
        import proveedores
        return proveedores.completar(mensajes, tarea=tarea)

    def responder(self, texto):
        """Devuelve (respuesta, accion, emocion). accion es None o 'nombre' / 'nombre | texto'."""
        import pantalla_remota_accion as pra
        if pra.detectar_orden_hud(texto):
            msg = pra.activar_hud(app=getattr(self, "app", None))
            self.historial.append({"role": "user", "content": texto})
            self.historial.append({"role": "assistant", "content": msg})
            self._podar_historial()
            return msg, "activar_hud", "alegre"

        import proveedores_cadenas as pc
        from memoria_adaptadores import atender_turno
        directo = atender_turno(self, texto)
        if directo:
            return directo
        self.ultimo_texto_usuario = texto
        self.historial.append({"role": "user", "content": texto})
        prompt = self.instrucciones(texto)
        mensajes = [{"role": "system", "content": prompt}] + self._obtener_historial_podado()
        tarea = pc.clasificar_dificultad(texto)
        try:
            import cerebro_enrutador
            crudo = cerebro_enrutador.ejecutar_con_enrutador(
                texto, mensajes, tarea=tarea, app=getattr(self, "app", None), fallback_fn=self._pedir
            )
        except Exception as e:
            print(f"[cerebro] Excepción no controlada: {e}. Usando respuesta local.", flush=True)
            crudo = pc.respuesta_emergencia_local()
        respuesta, accion, recuerdo, emocion = separar(crudo)
        if recuerdo and not getattr(self, "turno_invitado", False):
            from memoria_adaptadores import procesar_candidato
            procesar_candidato(self.memoria, recuerdo, texto, fuente="recuerdo_modelo",
                canal=getattr(self.app, "origen_entrada_actual", "texto"))
        self.historial.append({"role": "assistant", "content": respuesta})
        self._podar_historial()
        if not getattr(self, "turno_invitado", False):
            try:
                import aprendizaje
                aprendizaje.registrar_interaccion(texto, respuesta, emocion)
            except Exception as e:
                print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)

        turnos_u = sum(1 for m in self.historial if m.get("role") == "user")
        if turnos_u > 0 and turnos_u % 3 == 0 and not getattr(self, "turno_invitado", False):
            import threading
            threading.Thread(
                target=self.memoria.extraer_hechos_conversacion,
                args=(list(self.historial[-6:]), self._pedir),
                daemon=True,
            ).start()

        return respuesta, accion, emocion

    def reflexionar(self, modulo_hilos):
        """Reflexiona sobre la conversación reciente para extraer hechos y temas pendientes."""
        try:
            ultimos = self.historial[-20:]
            from memoria_adaptadores import historial_prohibido
            if historial_prohibido(ultimos):
                return
            intervenciones = sum(1 for m in ultimos if m.get("role") == "user")
            if intervenciones < 4:
                return

            ahora = time.time()
            if ahora - self.ultima_reflexion < 600:
                return
            self.ultima_reflexion = ahora

            charla = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in ultimos)
            sistema = (
                f"Eres {self.memoria.nombre or 'Lyris'}. Analiza la charla reciente y extrae aprendizajes duraderos.\n"
                "1. Hasta 3 líneas 'HECHO: <dato duradero y concreto sobre el usuario (gustos, familia, metas, proyectos reales)>'.\n"
                "PROHIBIDO: comandos, pruebas, pedidos a Silvestra, HUD, casa inteligente ni conjeturas.\n"
                "2. Hasta 2 líneas 'PREGUNTA: <tema de seguimiento para la próxima>'.\n"
                "Sin datos sensibles ni contraseñas. Si no hay nada nuevo: NINGUNO."
            )
            mensajes = [
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Esta fue la conversación reciente:\n{charla}"},
            ]
            crudo = self._pedir(mensajes, tarea="fondo")
            for linea in (crudo or "").splitlines():
                s = linea.strip()
                if re.match(r"^HECHO\s*:\s*", s, re.I):
                    dato = re.sub(r"^HECHO\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if dato and dato.lower() not in ("ninguno", "ninguna", "nada"):
                        self.memoria.recordar(dato, origen="inferido", texto_usuario=charla,
                                              fuente="extraccion")
                elif re.match(r"^PREGUNTA\s*:\s*", s, re.I):
                    preg = re.sub(r"^PREGUNTA\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if preg and preg.lower() not in ("ninguno", "ninguna", "nada"):
                        modulo_hilos.anotar_pendiente(preg)

            import threading
            threading.Thread(
                target=self.memoria.extraer_hechos_conversacion,
                args=(list(ultimos), self._pedir),
                daemon=True,
            ).start()
        except Exception:
            pass
