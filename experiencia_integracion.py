"""Puente asíncrono entre verificación y aprendizaje; no opera widgets Qt."""
from queue import Queue
from threading import Event, Thread


class AdaptadorExperiencias:
    def __init__(self, motor):
        self.motor = motor
        self._cola = Queue()
        self._cerrando = Event()
        self._plan_callback = self._recibir_tarea_plan
        self._sistemas = set()
        self._hilo = Thread(target=self._consumir, name="experiencias", daemon=True)
        self._hilo.start()

    def conectar_verificacion(self, verificador):
        if self._cerrando.is_set(): return False
        suscribir = getattr(verificador, "suscribir_post_verificacion", None)
        return bool(callable(suscribir) and suscribir(self.recibir_informe))

    def conectar_planificacion(self, planificador):
        if self._cerrando.is_set(): return False
        suscribir = getattr(planificador, "suscribir_resultados", None)
        if not callable(suscribir):
            return False
        return bool(suscribir(self._plan_callback))

    def _recibir_tarea_plan(self, plan, tarea, estado):
        self.recibir_tarea(plan,tarea,estado,False)

    def conectar_ejecucion(self, sistema):
        if self._cerrando.is_set(): return False
        if id(sistema) in self._sistemas: return True
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
        self._sistemas.add(id(sistema))
        return True

    def recibir_informe(self, informe):
        if not self._cerrando.is_set(): self._cola.put_nowait(("informe", informe))

    def recibir_ejecucion(self, solicitud, resultado, esperado=None):
        if not self._cerrando.is_set(): self._cola.put_nowait(("ejecucion", (solicitud, resultado, esperado)))

    def recibir_tarea(self, plan, tarea, estado, verificada=False):
        if not self._cerrando.is_set(): self._cola.put_nowait(("tarea", (plan, tarea, estado, verificada)))

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
                        "categoria": "tarea_planificada", "origen_clave": f"plan:{plan}|tarea:{tarea}"})
            except Exception:
                pass
            finally:
                self._cola.task_done()

    def esperar(self):
        self._cola.join()

    def cerrar(self, timeout=1.0):
        if self._cerrando.is_set(): return
        self._cerrando.set()
        self._cola.join()
        self._cola.put_nowait(("cerrar", None))
        self._hilo.join(max(0.0, float(timeout)))
