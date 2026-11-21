"""Composición única de memoria, planificación, ejecución y aprendizaje cognitivo."""
import threading

from experiencia_integracion import AdaptadorExperiencias
from experiencia_motor import MotorExperiencias
from planificacion_motor import PlanificacionMotor


class IntegracionCognitivaFase5:
    def __init__(self, memoria, app=None, sistema_ejecucion=None,
                 verificador=None, motor_permisos=None):
        if not hasattr(memoria, "almacen"):
            raise TypeError("Se requiere la memoria cognitiva existente")
        self.memoria, self.app = memoria, app
        self.usuario_id = memoria.usuario_id
        self._lock = threading.RLock()
        self._cerrado = False
        self.experiencias = MotorExperiencias(memoria.almacen, self.usuario_id)
        self.planificacion = PlanificacionMotor(memoria.almacen, self.usuario_id)
        self.adaptador = AdaptadorExperiencias(self.experiencias)
        if sistema_ejecucion is None:
            from ejecucion_registro import RegistroHerramientas, SistemaEjecucion
            from permisos_motor import MotorPermisos
            motor_permisos = motor_permisos or MotorPermisos()
            sistema_ejecucion = SistemaEjecucion(RegistroHerramientas(), motor_permisos=motor_permisos)
        elif motor_permisos is None:
            motor_permisos = getattr(sistema_ejecucion, "motor_permisos", None)
        if motor_permisos is None:
            from permisos_motor import MotorPermisos
            motor_permisos = MotorPermisos()
            sistema_ejecucion.motor_permisos = motor_permisos
        if verificador is None:
            from verificacion_motor import MotorVerificacionRecuperacion
            verificador = MotorVerificacionRecuperacion()
        self.motor_permisos, self.ejecucion, self.verificador = motor_permisos, sistema_ejecucion, verificador
        self.adaptador.conectar_planificacion(self.planificacion)
        self.adaptador.conectar_ejecucion(self.ejecucion)
        self.adaptador.conectar_verificacion(self.verificador)

    def ejecutar_solicitud(self, solicitud, resultado_esperado=None, token_cancelacion=None):
        if token_cancelacion is not None and token_cancelacion.is_set():
            return {"cancelado": True, "resultado": None, "verificacion": None}
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError("La ejecución controlada debe invocarse fuera del hilo principal de Qt")
        with self._lock:
            if self._cerrado:
                raise RuntimeError("La integración cognitiva está cerrada")
        plan_id = getattr(solicitud, "id_plan", None)
        if plan_id:
            _, analisis = self.planificacion.obtener(plan_id)
            if not analisis or analisis.decision.aprobacion_usuario != "aprobada":
                raise PermissionError("La recomendación requiere aprobación explícita")
        resultado = self.ejecucion.procesar(solicitud)
        self.adaptador.recibir_ejecucion(solicitud, resultado, resultado_esperado)
        if token_cancelacion is not None and token_cancelacion.is_set():
            return {"cancelado": True, "resultado": resultado, "verificacion": None}
        informe = self.verificador.verificar_resultado(solicitud, resultado, resultado_esperado)
        return {"cancelado": False, "resultado": resultado, "verificacion": informe}

    def cerrar(self, timeout=1.0):
        with self._lock:
            if self._cerrado:
                return
            self._cerrado = True
        self.adaptador.cerrar(timeout)
