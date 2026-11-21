"""Puente asíncrono entre verificación y aprendizaje; no opera widgets Qt."""
from queue import Queue
from threading import Thread


class AdaptadorExperiencias:
    def __init__(self, motor):
        self.motor = motor
        self._cola = Queue()
        self._hilo = Thread(target=self._consumir, name="experiencias", daemon=True)
        self._hilo.start()

    def conectar_verificacion(self, verificador):
        suscribir = getattr(verificador, "suscribir_post_verificacion", None)
        return bool(callable(suscribir) and suscribir(self.recibir_informe))

    def conectar_planificacion(self, planificador):
        suscribir = getattr(planificador, "suscribir_resultados", None)
        if not callable(suscribir):
            return False
        return bool(suscribir(lambda plan, tarea, estado:
            self.recibir_tarea(plan, tarea, estado, False)))

    def conectar_ejecucion(self, sistema):
        previo = getattr(sistema, "post_ejecucion", None)
        if getattr(sistema, "_adaptador_experiencias", None) is self:
            return True
        def posterior(solicitud, contrato, resultado):
            if callable(previo):
                try: previo(solicitud, contrato, resultado)
                except Exception: pass
            self.recibir_ejecucion(solicitud, resultado)
        sistema.post_ejecucion = posterior
        sistema._adaptador_experiencias = self
        return True

    def recibir_informe(self, informe):
        self._cola.put_nowait(("informe", informe))

    def recibir_ejecucion(self, solicitud, resultado, esperado=None):
        self._cola.put_nowait(("ejecucion", (solicitud, resultado, esperado)))

    def recibir_tarea(self, plan, tarea, estado, verificada=False):
        self._cola.put_nowait(("tarea", (plan, tarea, estado, verificada)))

    def _consumir(self):
        while True:
            tipo, dato = self._cola.get()
            try:
                if tipo == "cerrar":
                    return
                if tipo == "informe":
                    self.motor.registrar_informe(dato)
                elif tipo == "ejecucion":
                    self.motor.registrar_ejecucion(*dato)
                else:
                    plan, tarea, estado, verificada = dato
                    self.motor.registrar({"resultado_esperado": "estado completado",
                        "resultado_observado": "tarea " + str(estado), "factores": [str(tarea)],
                        "origen_ids": [str(plan), str(tarea)], "verificada": bool(verificada),
                        "exito": True if verificada and estado == "completada" else None,
                        "categoria": "tarea_planificada"})
            except Exception:
                pass
            finally:
                self._cola.task_done()

    def esperar(self):
        self._cola.join()

    def cerrar(self, timeout=1.0):
        self._cola.put_nowait(("cerrar", None))
        self._hilo.join(max(0.0, float(timeout)))
