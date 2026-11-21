"""17 pruebas del motor concurrente de ejecucion — Fase 2 Etapa 3."""
from __future__ import annotations

import threading
import time
import unittest

import ejecucion_modelo as em
import ejecucion_registro as er
import permisos_modelo as pm
import permisos_motor as perms
from motor_ejecucion_estado import (
    COMPLETADA,
    EJECUTANDO,
    EN_COLA,
    ESPERANDO_AUTORIZACION,
    EXPIRADA,
    FALLIDA,
    PENDIENTE,
    VALIDANDO,
    TRANSICIONES_VALIDAS,
    ColaPrioridadEjecucion,
    FichaTareaEjecucion,
    TokenCancelacion,
)
from motor_ejecucion import MotorEjecucionTareas


class TestMotorEjecucion(unittest.TestCase):
    def setUp(self):
        self.registro = er.RegistroHerramientas()
        self.permisos = perms.MotorPermisos()
        self.motor = MotorEjecucionTareas(
            self.registro, self.permisos, max_workers=2
        )

    def tearDown(self):
        self.motor.detener(esperar=False)

    def registrar(self, nombre, handler=None, riesgo="bajo",
                  nivel=pm.NIVEL_SOLO_LECTURA, timeout=5.0,
                  esquema=None):
        contrato = em.ContratoHerramienta(
            nombre, "consulta", "Herramienta segura de prueba",
            parametros_esquema=esquema or {
                "requeridos": [], "opcionales": ["valor"],
                "tipos": {"valor": "int"},
            },
            handler=handler,
            nivel_riesgo=riesgo,
            timeout_seg=timeout,
        )
        self.registro.registrar(contrato)
        self.permisos.registrar_politica(pm.PoliticaOperacion(
            nombre, nivel, riesgo_maximo_permitido=riesgo,
            ttl_seg_por_defecto=300.0,
        ))
        return contrato

    def esperar_estado(self, id_solicitud, estados, timeout=2.0):
        fin = time.time() + timeout
        while time.time() < fin:
            estado = self.motor.obtener_estado_tarea(id_solicitud)
            if estado and estado["estado"] in estados:
                return estado
            time.sleep(0.01)
        return self.motor.obtener_estado_tarea(id_solicitud)

    def test_1_solicitud_estandarizada(self):
        sol = em.SolicitudEjecucion("usuario", "demo", {"valor": 1})
        self.assertIn(sol.id_solicitud, sol.a_dict().values())
        self.assertEqual(sol.origen, "usuario")

    def test_2_encola_consulta_pendientes(self):
        bloqueado = threading.Event()
        def hilo(params):
            bloqueado.wait(0.15)
            return "ok"
        self.registrar("cola", hilo)
        sol = em.SolicitudEjecucion("usuario", "cola", {"valor": 1})
        self.motor.encolar(sol, prioridad=3)
        datos = self.motor.obtener_estado_tarea(sol.id_solicitud)
        self.assertIsNotNone(datos)
        self.assertIn(datos["estado"], ("en_cola", "ejecutando", "completada"))
        self.esperar_estado(sol.id_solicitud, (COMPLETADA,), 1)

    def test_3_ejecucion_exitosa_simulada(self):
        self.registrar("eco", lambda p: {"eco": p["valor"]})
        sol = em.SolicitudEjecucion("usuario", "eco", {"valor": 9})
        self.motor.encolar(sol)
        estado = self.esperar_estado(sol.id_solicitud, (COMPLETADA,), 1)
        self.assertEqual(estado["estado"], COMPLETADA)
        res = self.motor.obtener_resultado(sol.id_solicitud)
        self.assertTrue(res.exito)
        self.assertEqual(res.datos["eco"], 9)

    def test_4_solo_lectura_y_confirmacion_usuario(self):
        self.registrar("lectura", lambda p: "ok")
        lectura = em.SolicitudEjecucion("sistema", "lectura", {})
        self.motor.encolar(lectura)
        self.esperar_estado(lectura.id_solicitud, (COMPLETADA,), 1)
        self.assertTrue(self.motor.obtener_resultado(lectura.id_solicitud).exito)

        self.registrar("confirmar", lambda p: "ok",
                       nivel=pm.NIVEL_REQUIERE_CONFIRMACION)
        sol = em.SolicitudEjecucion("cerebro", "confirmar", {})
        resultado = self.motor.encolar(sol)
        self.assertEqual(resultado.estado, "esperando_autorizacion")
        id_auth = resultado.metadatos["id_autorizacion"]
        aprobada = self.permisos.confirmar_autorizacion(id_auth, actor="usuario")
        self.assertTrue(aprobada["aprobada"])
        self.assertTrue(self.motor.reanudar_autorizada(sol.id_solicitud))
        self.esperar_estado(sol.id_solicitud, (COMPLETADA,), 1)

    def test_5_denegaciones_y_autoaprobacion_llm(self):
        self.registrar("prohibida", lambda p: "nunca",
                       nivel=pm.NIVEL_PROHIBIDA)
        sol = em.SolicitudEjecucion("cerebro", "prohibida", {})
        res = self.motor.encolar(sol)
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "OPERACION_PROHIBIDA")

        sin = er.RegistroHerramientas()
        motor_sin = MotorEjecucionTareas(sin, perms.MotorPermisos(), 1)
        contrato = em.ContratoHerramienta(
            "sin", "consulta", "sin",
            handler=lambda p: "nunca",
        )
        sin.registrar(contrato)
        self.assertEqual(
            motor_sin.encolar(
                em.SolicitudEjecucion("sistema", "sin", {})
            ).error["codigo"],
            "SIN_POLITICA",
        )
        motor_sin.detener(False)

        self.registrar("humano", lambda p: "ok",
                       nivel=pm.NIVEL_REQUIERE_CONFIRMACION)
        pend = em.SolicitudEjecucion("cerebro", "humano", {})
        res = self.motor.encolar(pend)
        id_auth = res.metadatos["id_autorizacion"]
        intento = self.permisos.confirmar_autorizacion(id_auth, actor="llm")
        self.assertFalse(intento["aprobada"])

    def test_6_caducada_revocada_parametros(self):
        self.registrar("caduca", lambda p: "ok",
                       nivel=pm.NIVEL_REQUIERE_CONFIRMACION)
        sol = em.SolicitudEjecucion("usuario", "caduca", {"valor": 1})
        pend = self.motor.encolar(sol)
        id_auth = pend.metadatos["id_autorizacion"]
        self.permisos.confirmar_autorizacion(id_auth, actor="usuario", ttl_seg=0.01)
        time.sleep(0.02)
        self.assertFalse(self.motor.reanudar_autorizada(sol.id_solicitud))

        sol2 = em.SolicitudEjecucion("usuario", "caduca", {"valor": 2})
        pend2 = self.motor.encolar(sol2)
        id2 = pend2.metadatos["id_autorizacion"]
        self.permisos.confirmar_autorizacion(id2, actor="usuario")
        sol2.parametros["valor"] = 99
        self.assertFalse(self.motor.reanudar_autorizada(sol2.id_solicitud))

        sol3 = em.SolicitudEjecucion("usuario", "caduca", {"valor": 3})
        pend3 = self.motor.encolar(sol3)
        id3 = pend3.metadatos["id_autorizacion"]
        self.permisos.confirmar_autorizacion(id3, actor="usuario")
        self.permisos.revocar_autorizacion(id_autorizacion=id3)
        self.assertFalse(self.motor.reanudar_autorizada(sol3.id_solicitud))

    def test_7_prioridad_mayor_primero(self):
        orden = []
        bloqueo = threading.Event()
        bloqueo.set()
        def lenta(p):
            bloqueo.wait()
            orden.append(p["valor"])
            return p["valor"]
        self.registrar("prioridad", lenta)
        bloqueo.clear()
        motor_prioridad = MotorEjecucionTareas(
            self.registro, self.permisos, max_workers=1
        )
        primero = em.SolicitudEjecucion("usuario", "prioridad", {"valor": -1})
        motor_prioridad.encolar(primero, prioridad=100)
        time.sleep(0.03)
        alta = em.SolicitudEjecucion("usuario", "prioridad", {"valor": 1})
        baja = em.SolicitudEjecucion("usuario", "prioridad", {"valor": 0})
        motor_prioridad.encolar(alta, prioridad=10)
        motor_prioridad.encolar(baja, prioridad=1)
        bloqueo.set()
        time.sleep(0.2)
        self.assertEqual(orden[:1], [-1])
        motor_prioridad.detener(False)

    def test_8_concurrencia_max_workers(self):
        estado = {"activo": 0, "maximo": 0}
        bloqueo = threading.Lock()
        def concurrente(p):
            with bloqueo:
                estado["activo"] += 1
                estado["maximo"] = max(estado["maximo"], estado["activo"])
            time.sleep(0.05)
            with bloqueo:
                estado["activo"] -= 1
            return p["valor"]
        self.registrar("concurrente", concurrente)
        for i in range(6):
            self.motor.encolar(
                em.SolicitudEjecucion("usuario", "concurrente", {"valor": i})
            )
        time.sleep(0.5)
        self.assertLessEqual(estado["maximo"], 2)
        self.assertGreaterEqual(estado["maximo"], 1)

    def test_9_cancelacion_cola_y_activa(self):
        bloqueo = threading.Event()
        def lenta(params, token_cancelacion):
            if bloqueo.wait(0.15):
                return "salida"
            return "cancelable"
        self.registrar("cancelar", lenta, timeout=5)
        sol = em.SolicitudEjecucion("usuario", "cancelar", {})
        self.motor.encolar(sol)
        time.sleep(0.02)
        self.assertTrue(self.motor.cancelar(sol.id_solicitud, "prueba"))
        estado = self.esperar_estado(sol.id_solicitud, ("cancelada",), 1)
        self.assertEqual(estado["estado"], "cancelada")

        cola = em.SolicitudEjecucion("usuario", "cancelar", {})
        self.motor.encolar(cola)
        self.assertTrue(self.motor.cancelar(cola.id_solicitud))

    def test_10_timeout_honesto_salida_tardia_descartada(self):
        def bloqueante(params, token):
            time.sleep(0.12)
            return "salida tardia"
        self.registrar("timeout", bloqueante, timeout=0.03)
        sol = em.SolicitudEjecucion("usuario", "timeout", {})
        self.motor.encolar(sol)
        estado = self.esperar_estado(sol.id_solicitud, (EXPIRADA,), 1)
        self.assertEqual(estado["estado"], EXPIRADA)
        res = self.motor.obtener_resultado(sol.id_solicitud)
        self.assertEqual(res.error["codigo"], "TIMEOUT_EJECUCION")
        self.assertTrue(res.metadatos["worker_en_segundo_plano"])

    def test_11_excepcion_aislada(self):
        def explota(p):
            raise RuntimeError("boom")
        self.registrar("fallo", explota)
        self.registrar("bueno", lambda p: "ok")
        malo = em.SolicitudEjecucion("usuario", "fallo", {})
        bueno = em.SolicitudEjecucion("usuario", "bueno", {})
        self.motor.encolar(malo)
        self.motor.encolar(bueno)
        self.esperar_estado(malo.id_solicitud, (FALLIDA,), 1)
        self.esperar_estado(bueno.id_solicitud, (COMPLETADA,), 1)
        self.assertFalse(self.motor.obtener_resultado(malo.id_solicitud).exito)
        self.assertTrue(self.motor.obtener_resultado(bueno.id_solicitud).exito)

    def test_12_maquina_estados(self):
        token = TokenCancelacion()
        self.assertFalse(token.esta_cancelado())
        token.cancelar("stop")
        self.assertTrue(token.esta_cancelado())
        ficha = FichaTareaEjecucion(
            em.SolicitudEjecucion("usuario", "demo", {})
        )
        self.assertFalse(ficha.transicionar(EJECUTANDO))
        self.assertTrue(ficha.transicionar(VALIDANDO))
        self.assertFalse(ficha.transicionar(COMPLETADA))
        self.assertTrue(ficha.transicionar(EN_COLA))

    def test_13_solicitudes_duplicadas(self):
        self.registrar("duplicado", lambda p: "ok")
        sol = em.SolicitudEjecucion("usuario", "duplicado", {})
        self.motor.encolar(sol)
        duplicada = self.motor.encolar(sol)
        self.assertFalse(duplicada.exito)
        self.assertEqual(duplicada.error["codigo"], "SOLICITUD_DUPLICADA")

    def test_14_detener_con_cola_y_activa(self):
        bloqueo = threading.Event()
        def bloqueante(p):
            bloqueo.wait(0.1)
            return "ok"
        self.registrar("detener", bloqueante)
        for i in range(4):
            self.motor.encolar(
                em.SolicitudEjecucion("usuario", "detener", {"valor": i})
            )
        time.sleep(0.02)
        self.motor.detener(esperar=True, timeout=0.2)
        bloqueo.set()
        self.assertTrue(self.motor.estadisticas()["detenido"])

    def test_15_eventos_callback_y_app_cola(self):
        eventos = []
        cola = __import__("queue").Queue()
        motor = MotorEjecucionTareas(
            self.registro, self.permisos, max_workers=1, app_cola=cola
        )
        motor.suscribir_eventos(lambda payload: eventos.append(payload))
        self.registrar("eventos", lambda p: "ok")
        sol = em.SolicitudEjecucion("usuario", "eventos", {})
        motor.encolar(sol)
        time.sleep(0.1)
        self.assertGreater(len(eventos), 0)
        item = cola.get_nowait()
        self.assertEqual(item[0], "ejecucion_evento")
        motor.detener(False)

    def test_16_sin_bloqueos_no_efectos_reales(self):
        self.registrar("puro", lambda p: p)
        sol = em.SolicitudEjecucion("usuario", "puro", {"valor": 7})
        inicio = time.time()
        res = self.motor.encolar(sol)
        self.assertLess(time.time() - inicio, 0.5)
        self.assertNotIn("subprocess", res.a_dict())
        self.esperar_estado(sol.id_solicitud, (COMPLETADA,), 1)

    def test_17_regresion_nucleo_integrado(self):
        self.registrar("nucleo", lambda p: {"nucleo": True})
        sol = em.SolicitudEjecucion("planificador", "nucleo", {})
        sol.id_plan = "plan_1"
        sol.id_tarea = "tarea_1"
        self.motor.encolar(sol)
        estado = self.esperar_estado(sol.id_solicitud, (COMPLETADA,), 1)
        self.assertEqual(estado["estado"], COMPLETADA)


if __name__ == "__main__":
    unittest.main()
