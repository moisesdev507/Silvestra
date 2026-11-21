"""22 pruebas de verificacion independiente y recuperacion — Fase 2 Etapa 7."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

import ejecucion_modelo as em
from verificacion_modelo import (
    CriterioVerificacion, EvidenciaVerificacion,
    CategoriaError, VERIFICADO, RECUPERADO, FALLIDO,
    REQUIERE_INTERVENCION, RESULTADO_PARCIAL,
)
from verificacion_motor import MotorVerificacionRecuperacion


class PermisosMock:
    def __init__(self, permitida=True):
        self.permitida = permitida
        self.fallo = False
    def validar_antes_de_ejecutar(self, solicitud, contrato):
        if self.fallo:
            raise RuntimeError("fallo")
        return {"permitida": self.permitida, "codigo": "REVOCADA"}


class TestVerificacionRecuperacion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = os.path.join(self.tmp.name, "informes.json")
        self.permisos = PermisosMock(True)
        self.motor = MotorVerificacionRecuperacion(
            motor_permisos=self.permisos,
            archivo_persistencia=self.archivo,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def criterio(self, nombre, idempotente=False, estrategia="ninguna",
                 intentos=0, backoff=0.0):
        return CriterioVerificacion(
            nombre, idempotente, ("estado_real",),
            estrategia, intentos, backoff,
        )

    def solicitud(self, nombre="simulada", parametros=None):
        return em.SolicitudEjecucion(
            "usuario", nombre,
            dict(parametros or {}),
        )

    def resultado(self, exito=True, codigo="", mensaje=""):
        error = None if exito else {
            "codigo": codigo, "mensaje": mensaje, "recuperable": True,
        }
        return em.ResultadoEjecucion(
            "id", "simulada", "completada" if exito else "fallida",
            exito, datos={"ok": True}, error=error,
        )

    def test_1_verificado_evidencia_independiente(self):
        c = self.criterio("demo")
        def ver(s, r, e):
            return EvidenciaVerificacion("lectura_real", True, True, datos={"ok": True})
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res, {"ok": True})
        self.assertEqual(inf.estado_final, VERIFICADO)

    def test_2_aparentemente_exitoso_sin_efecto(self):
        c = self.criterio("demo")
        def ver(s, r, e):
            return EvidenciaVerificacion("archivo", True, False, datos={"existe": False})
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)
        self.assertNotEqual(inf.estado_final, VERIFICADO)

    def test_3_resultado_parcial(self):
        c = self.criterio("demo", True, "reanudar_punto_seguro", 1)
        def ver(s, r, e):
            return EvidenciaVerificacion(
                "archivo", True, False, es_parcial=True,
                datos={"punto_seguro": "01"},
            )
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(inf.estado_final, (RECUPERADO, REQUIERE_INTERVENCION))

    def test_4_sin_verificador_insuficiente(self):
        sol = self.solicitud("sin_verificador")
        res = em.ResultadoEjecucion(sol.id_solicitud, "sin_verificador", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)
        self.assertTrue(inf.evidencia.insuficiente)

    def test_5_error_temporal(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("x", False, False, insuficiente=True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TEMPORAL_REINTENTABLE", "mensaje": "temporal",
                   "recuperable": True},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(CategoriaError.TEMPORAL, inf.errores_detectados)

    def test_6_error_permanente(self):
        sol = self.solicitud("demo")
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("x", False, False, insuficiente=True))
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "ERROR_PERMANENTE", "mensaje": "permanente",
                   "recuperable": False},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(CategoriaError.PERMANENTE, inf.errores_detectados)

    def test_7_timeout(self):
        sol = self.solicitud("demo")
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("x", False, False))
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TIMEOUT_EJECUCION", "mensaje": "timeout",
                   "recuperable": True},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(CategoriaError.TIMEOUT, inf.errores_detectados)

    def test_8_cancelada(self):
        sol = self.solicitud("demo")
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("x", False, False))
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "cancelada", False,
            error={"codigo": "CANCELADA", "mensaje": "cancelada",
                   "recuperable": True},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(CategoriaError.CANCELADA, inf.errores_detectados)

    def test_9_reintento_idempotente_recuperado(self):
        c = self.criterio("demo", True, "reintento_idempotente", 2)
        cuenta = {"n": 0}
        def ver(s, r, e):
            cuenta["n"] += 1
            return EvidenciaVerificacion(
                "real", cuenta["n"] >= 2, cuenta["n"] >= 2,
            )
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TEMPORAL", "mensaje": "temporal",
                   "recuperable": True},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(inf.estado_final, (RECUPERADO, REQUIERE_INTERVENCION))

    def test_10_no_idempotente_humano(self):
        c = self.criterio("crear_archivo", False, "reintento_idempotente", 2)
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", False, False, insuficiente=True))
        sol = self.solicitud("crear_archivo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "crear_archivo", "fallida", False)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)

    def test_11_limite_maximo(self):
        c = self.criterio("demo", True, "reintento_idempotente", 3)
        self.assertLessEqual(c.max_reintentos, 3)
        c2 = CriterioVerificacion("demo", True, ("x",), "reintento_idempotente", 99)
        self.assertEqual(c2.max_reintentos, 3)

    def test_12_solicitudes_duplicadas(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", True, True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        uno = self.motor.verificar_resultado(sol, res)
        dos = self.motor.verificar_resultado(sol, res)
        self.assertIs(uno, dos)
        self.assertEqual(len(self.motor.listar_informes()), 1)

    def test_13_punto_seguro_reanudado(self):
        c = self.criterio("copiar", True, "reanudar_punto_seguro", 2)
        llamadas = {"n": 0}
        def ver(s, r, e):
            llamadas["n"] += 1
            return EvidenciaVerificacion(
                "archivo", llamadas["n"] >= 2, llamadas["n"] >= 2,
                es_parcial=llamadas["n"] == 1,
                datos={"punto_seguro": True},
            )
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("copiar")
        res = em.ResultadoEjecucion(sol.id_solicitud, "copiar", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertIn(inf.estado_final, (RECUPERADO, REQUIERE_INTERVENCION))

    def test_14_recuperacion_agotada(self):
        c = self.criterio("demo", True, "reintento_idempotente", 1)
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", False, False, insuficiente=True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TEMPORAL", "mensaje": "temporal",
                   "recuperable": True},
        )
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)

    def test_15_escalar_sin_compensacion(self):
        c = self.criterio("mover", False, "escalar_humano", 0)
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", False, False, insuficiente=True))
        sol = self.solicitud("mover")
        res = em.ResultadoEjecucion(sol.id_solicitud, "mover", "fallida", False)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)
        self.assertEqual(inf.acciones_recuperacion, [])

    def test_16_duplicados_motor_verificacion(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", True, True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        self.motor.verificar_resultado(sol, res)
        antes = len(self.motor.listar_informes())
        self.motor.verificar_resultado(sol, res)
        self.assertEqual(len(self.motor.listar_informes()), antes)

    def test_17_permiso_revocado_falla(self):
        c = self.criterio("demo", True, "reintento_idempotente", 2)
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", False, False, insuficiente=True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TEMPORAL", "mensaje": "temporal",
                   "recuperable": True},
        )
        self.permisos.permitida = False
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, REQUIERE_INTERVENCION)

    def test_18_concurrencia_rlock(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", True, True))
        errores = []
        def worker(i):
            try:
                sol = self.solicitud("demo", {"i": i})
                res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
                self.motor.verificar_resultado(sol, res)
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(2)
        self.assertEqual(errores, [])
        self.assertEqual(len(self.motor.listar_informes()), 8)

    def test_19_persistencia_sanitizada(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", True, True,
                                  datos={"token": "secreto", "texto": "dato"}))
        sol = self.solicitud("demo", {
            "password": "123", "api_key": "abc",
            "texto": "contenido", "valor": 1,
        })
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        serial = inf.a_dict()
        texto = str(serial)
        self.assertNotIn("123", texto)
        self.assertIn("'api_key': '***'", texto)
        self.assertIn("'password': '***'", texto)
        self.assertIn("'texto': '***'", texto)

    def test_20_integracion_plataformas(self):
        c = self.criterio("archivo")
        def ver(s, r, e):
            return EvidenciaVerificacion("archivo", True, True)
        self.motor.registrar_estrategia(c, ver)
        sol = self.solicitud("archivo")
        sol.id_plan = "plan_1"
        sol.id_tarea = "t1"
        res = em.ResultadoEjecucion(sol.id_solicitud, "archivo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertEqual(inf.estado_final, VERIFICADO)

    def test_21_sin_bloqueo_app_cola(self):
        import queue
        cola = queue.Queue()
        motor = MotorVerificacionRecuperacion(app_cola=cola)
        c = self.criterio("demo")
        motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("real", True, True))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        motor.verificar_resultado(sol, res)
        item = cola.get_nowait()
        self.assertEqual(item[0], "verificacion_evento")

    def test_22_evidencia_real_en_todas(self):
        c = self.criterio("demo")
        self.motor.registrar_estrategia(c, lambda s, r, e:
            EvidenciaVerificacion("lectura", True, True,
                                  datos={"valor": "real"}))
        sol = self.solicitud("demo")
        res = em.ResultadoEjecucion(sol.id_solicitud, "demo", "completada", True)
        inf = self.motor.verificar_resultado(sol, res)
        self.assertTrue(inf.evidencia.positiva())


if __name__ == "__main__":
    unittest.main()
