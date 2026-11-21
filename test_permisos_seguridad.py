"""Pruebas de permisos, confirmacion, anti-replay y auditoria — Fase 2 Etapa 2."""
from __future__ import annotations

import threading
import time
import unittest

import permisos_modelo as pm
import permisos_motor as motor
import ejecucion_modelo as em
import ejecucion_registro as er
import planificador_modelo as plan


class TestPermisosSeguridad(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = motor.MotorPermisos()
        self.registro = er.RegistroHerramientas()
        self.sistema = er.SistemaEjecucion(self.registro, motor_permisos=self.motor)

    def contrato(self, nombre="consulta_segura", categoria="consulta", riesgo="bajo", handler=None):
        return em.ContratoHerramienta(
            nombre=nombre,
            categoria=categoria,
            descripcion="Operacion segura de prueba",
            parametros_esquema={
                "requeridos": [],
                "opcionales": ["texto", "token"],
                "tipos": {"texto": "str", "token": "str"},
            },
            handler=handler or (lambda p: {"ok": True}),
            nivel_riesgo=riesgo,
        )

    def politica(self, nombre, nivel, riesgo="bajo", ttl=300.0, doble=False):
        return pm.PoliticaOperacion(
            herramienta=nombre,
            nivel_autorizacion=nivel,
            riesgo_maximo_permitido=riesgo,
            permisos_requeridos=("usuario.confirmar",),
            ttl_seg_por_defecto=ttl,
            requiere_doble_confirmacion=doble,
            habilitada=True,
        )

    def test_lectura_permitida_y_prohibida_sin_politica(self) -> None:
        lectura = self.contrato("leer_estado")
        self.registro.registrar(lectura)
        self.motor.registrar_politica(
            self.politica("leer_estado", pm.NIVEL_SOLO_LECTURA)
        )
        res = self.sistema.procesar(
            em.SolicitudEjecucion("usuario", "leer_estado", {})
        )
        self.assertTrue(res.exito)

        prohibida = self.contrato("borrar_todo")
        self.registro.registrar(prohibida)
        self.motor.registrar_politica(
            self.politica("borrar_todo", pm.NIVEL_PROHIBIDA, "critico")
        )
        res = self.sistema.procesar(
            em.SolicitudEjecucion("cerebro", "borrar_todo", {})
        )
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "OPERACION_PROHIBIDA")

        desconocida = self.contrato("desconocida")
        self.registro.registrar(desconocida)
        res = self.sistema.procesar(
            em.SolicitudEjecucion("usuario", "desconocida", {})
        )
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "SIN_POLITICA")

    def test_requiere_confirmacion_usuario(self) -> None:
        contrato = self.contrato("buscar_dato")
        self.registro.registrar(contrato)
        ok, _ = self.motor.registrar_politica(
            self.politica("buscar_dato", pm.NIVEL_REQUIERE_CONFIRMACION)
        )
        self.assertTrue(ok)
        sol = em.SolicitudEjecucion("cerebro", "buscar_dato", {"texto": "hola"})
        res = self.sistema.procesar(sol)
        self.assertFalse(res.exito)
        self.assertEqual(res.estado, "pendiente_autorizacion")
        id_auth = res.metadatos["id_autorizacion"]
        conf = self.motor.confirmar_autorizacion(id_auth, actor="usuario")
        self.assertTrue(conf["aprobada"])
        res2 = self.sistema.procesar(sol)
        self.assertTrue(res2.exito)

    def test_sensible_reforzada(self) -> None:
        contrato = self.contrato("accion_sensible", riesgo="alto")
        self.registro.registrar(contrato)
        politica = self.politica(
            "accion_sensible", pm.NIVEL_SENSIBLE_REFORZADA, "alto", 60.0, True
        )
        self.motor.registrar_politica(politica)
        sol = em.SolicitudEjecucion("planificador", "accion_sensible", {})
        primera = self.sistema.procesar(sol)
        id_auth = primera.metadatos["id_autorizacion"]
        rechazada = self.motor.confirmar_autorizacion(id_auth, actor="usuario")
        self.assertFalse(rechazada["aprobada"])
        aprobada = self.motor.confirmar_autorizacion(
            id_auth, actor="usuario", codigo_refuerzo="codigo-explicito"
        )
        self.assertTrue(aprobada["aprobada"])
        self.assertTrue(self.sistema.procesar(sol).exito)

    def test_autoaprobacion_y_modificacion_politica_bloqueadas(self) -> None:
        contrato = self.contrato("confirmable")
        self.registro.registrar(contrato)
        self.motor.registrar_politica(
            self.politica("confirmable", pm.NIVEL_REQUIERE_CONFIRMACION)
        )
        sol = em.SolicitudEjecucion("cerebro", "confirmable", {})
        pendiente = self.sistema.procesar(sol)
        id_auth = pendiente.metadatos["id_autorizacion"]
        for actor in ("cerebro", "llm", "planificador", "automatico"):
            conf = self.motor.confirmar_autorizacion(id_auth, actor=actor)
            self.assertFalse(conf["aprobada"])
        modificacion = self.motor.registrar_politica(
            self.politica("confirmable", pm.NIVEL_SOLO_LECTURA),
            actor="llm",
        )
        self.assertFalse(modificacion[0])
        denegadas = self.motor.obtener_auditoria(limite=100, solo_denegadas=True)
        motivos = " ".join(e["motivo"] for e in denegadas)
        self.assertIn("autoaprobar", motivos)
        self.assertIn("no humano", motivos)

    def test_ttl_revocacion_parametros_reutilizacion(self) -> None:
        contrato = self.contrato("temporal")
        self.registro.registrar(contrato)
        self.motor.registrar_politica(
            self.politica("temporal", pm.NIVEL_REQUIERE_CONFIRMACION, ttl=0.02)
        )
        sol = em.SolicitudEjecucion("usuario", "temporal", {"texto": "uno"})
        pendiente = self.sistema.procesar(sol)
        id_auth = pendiente.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id_auth, actor="usuario", ttl_seg=0.02)
        time.sleep(0.03)
        res = self.sistema.procesar(sol)
        self.assertEqual(res.error["codigo"], "AUTORIZACION_CADUCADA")

        sol2 = em.SolicitudEjecucion("usuario", "temporal", {"texto": "dos"})
        pending2 = self.sistema.procesar(sol2)
        id2 = pending2.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id2, actor="usuario", ttl_seg=300)
        sol2.parametros["texto"] = "modificado"
        mod = self.sistema.procesar(sol2)
        self.assertEqual(mod.error["codigo"], "PARAMETROS_MODIFICADOS")

        sol3 = em.SolicitudEjecucion("usuario", "temporal", {"texto": "tres"})
        pending3 = self.sistema.procesar(sol3)
        id3 = pending3.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id3, actor="usuario", ttl_seg=300)
        self.assertTrue(self.sistema.procesar(sol3).exito)
        replay = self.sistema.procesar(sol3)
        self.assertEqual(replay.error["codigo"], "AUTORIZACION_REUTILIZADA")

        sol4 = em.SolicitudEjecucion("usuario", "temporal", {"texto": "cuatro"})
        pending4 = self.sistema.procesar(sol4)
        id4 = pending4.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id4, actor="usuario", ttl_seg=300)
        self.assertGreater(self.motor.revocar_autorizacion(id_autorizacion=id4), 0)
        revocado = self.sistema.procesar(sol4)
        self.assertEqual(revocado.error["codigo"], "AUTORIZACION_REVOCADA")

    def test_fail_closed_con_excepcion_interna(self) -> None:
        class MotorRoto:
            def evaluar_solicitud(self, solicitud, contrato):
                raise RuntimeError("fallo interno")

        contrato = self.contrato("seguro")
        self.registro.registrar(contrato)
        sistema = er.SistemaEjecucion(
            self.registro,
            motor_permisos=MotorRoto(),
        )
        res = sistema.procesar(em.SolicitudEjecucion("usuario", "seguro", {}))
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "ERROR_INTERNO_PERMISOS")

    def test_concurrencia_consumir_revocar(self) -> None:
        contrato = self.contrato("concurrente")
        self.registro.registrar(contrato)
        self.motor.registrar_politica(
            self.politica("concurrente", pm.NIVEL_REQUIERE_CONFIRMACION)
        )
        sol = em.SolicitudEjecucion("usuario", "concurrente", {})
        pendiente = self.sistema.procesar(sol)
        id_auth = pendiente.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id_auth, actor="usuario", ttl_seg=300)
        resultados = []

        def consumir():
            resultados.append(self.sistema.procesar(sol).exito)

        def revocar():
            self.motor.revocar_autorizacion(id_autorizacion=id_auth)

        hilos = [threading.Thread(target=consumir) for _ in range(5)]
        hilos.extend(threading.Thread(target=revocar) for _ in range(5))
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=5)
        self.assertIn(True, resultados)
        self.assertLessEqual(sum(resultados), 1)

    def test_auditoria_sanitiza_secretos(self) -> None:
        params = {
            "texto": "visible",
            "token": "secreto-token",
            "password": "secreto-password",
            "secret": "secreto-secret",
            "api_key": "secreto-api",
        }
        sol = em.SolicitudEjecucion("cerebro", "sin_politica", params)
        contrato = self.contrato("sin_politica")
        self.motor.evaluar_solicitud(sol, contrato)
        eventos = self.motor.obtener_auditoria(limite=10)
        punto = next(e for e in eventos if e["tipo_evento"] == "SIN_POLITICA")
        sanit = punto["parametros_sanitizados"]
        self.assertEqual(sanit["token"], "***")
        self.assertEqual(sanit["password"], "***")
        self.assertEqual(sanit["secret"], "***")
        self.assertEqual(sanit["api_key"], "***")
        self.assertEqual(sanit["texto"], "visible")

    def test_integracion_tarea_planificador(self) -> None:
        contrato = self.contrato("buscar", categoria="consulta")
        self.registro.registrar(contrato)
        self.motor.registrar_politica(
            self.politica("buscar", pm.NIVEL_REQUIERE_CONFIRMACION)
        )
        tarea = plan.Tarea("tb1", "Buscar informacion", "Ejecutar herramienta buscar")
        sol = self.sistema.resolver_desde_tarea(tarea, id_plan="plan_test")
        sol.parametros = {"texto": "x"}
        pendiente = self.sistema.procesar(sol)
        self.assertEqual(pendiente.estado, "pendiente_autorizacion")
        id_auth = pendiente.metadatos["id_autorizacion"]
        self.motor.confirmar_autorizacion(id_auth, actor="usuario")
        self.assertTrue(self.sistema.procesar(sol).exito)

    def test_huella_serializacion_y_niveles(self) -> None:
        sol = em.SolicitudEjecucion("usuario", "leer", {"b": 2, "a": 1})
        h1 = pm.huella_operacion("leer", {"b": 2, "a": 1}, sol.id_solicitud)
        h2 = pm.huella_operacion("leer", {"a": 1, "b": 2}, sol.id_solicitud)
        self.assertEqual(h1, h2)
        politica = self.politica("leer", pm.NIVEL_SOLO_LECTURA)
        datos = politica.a_dict()
        self.assertEqual(pm.PoliticaOperacion.de_dict(datos).herramienta, "leer")


if __name__ == "__main__":
    unittest.main()
