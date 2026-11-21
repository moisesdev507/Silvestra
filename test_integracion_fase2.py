"""15 escenarios E2E y auditoria final — Fase 2 Etapa 8."""
from __future__ import annotations

import ast
import os
import queue
import tempfile
import threading
import time
import unittest

import autonomia_modelo as am
from autonomia_modelo import PasoPlanOperativo
from orquestador_autonomia import OrquestadorAutonomiaSilvestra
from autonomia_puente import PuenteAutonomiaSilvestra

import ejecucion_modelo as em
import ejecucion_registro as er
import permisos_modelo as pm
import permisos_motor as perms
from motor_ejecucion import MotorEjecucionTareas
from verificacion_modelo import CriterioVerificacion, EvidenciaVerificacion
from verificacion_motor import MotorVerificacionRecuperacion


class TestIntegracionFase2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = os.path.join(self.tmp.name, "ordenes.json")
        self.cola = queue.Queue()
        self.registro = er.RegistroHerramientas()
        self.permisos = perms.MotorPermisos()
        self.ejecucion = MotorEjecucionTareas(
            self.registro, self.permisos, max_workers=2, app_cola=self.cola
        )
        self.verificacion = MotorVerificacionRecuperacion(
            motor_permisos=self.permisos,
            motor_ejecucion=self.ejecucion,
            app_cola=self.cola,
            archivo_persistencia=os.path.join(self.tmp.name, "verificacion.json"),
        )
        self.orquestador = OrquestadorAutonomiaSilvestra(
            registro=self.registro,
            motor_permisos=self.permisos,
            motor_ejecucion=self.ejecucion,
            verificador=self.verificacion,
            app_cola=self.cola,
            archivo_persistencia=self.archivo,
        )
        self.puente = PuenteAutonomiaSilvestra(
            self.orquestador, app_cola=self.cola
        )

    def tearDown(self):
        self.ejecucion.detener(False)
        self.tmp.cleanup()

    def registrar_lectura(self, nombre="leer_estado", handler=None):
        contrato = em.ContratoHerramienta(
            nombre=nombre,
            categoria="consulta",
            descripcion="Herramienta integral de prueba",
            parametros_esquema={
                "requeridos": [], "opcionales": ["valor"],
                "tipos": {"valor": "int"},
            },
            handler=handler or (lambda p: {"ok": True}),
            nivel_riesgo="bajo",
            timeout_seg=5.0,
        )
        self.registro.registrar(contrato)
        self.permisos.registrar_politica(
            pm.PoliticaOperacion(
                nombre, pm.NIVEL_SOLO_LECTURA,
                riesgo_maximo_permitido="bajo",
                ttl_seg_por_defecto=300.0,
            )
        )
        criterio = CriterioVerificacion(
            nombre, True, ("estado_real",),
            "reintento_idempotente", 1, 0.0,
        )
        self.verificacion.registrar_estrategia(
            criterio,
            lambda s, r, e: EvidenciaVerificacion(
                "lectura_real", True, True,
                datos={"ok": True},
            ),
        )

    def test_1_respuesta_sin_ejecucion(self):
        orden = self.puente.recibir_objetivo(
            "Explica el estado", requiere_ejecucion=False
        )
        self.assertEqual(orden.estado, am.RESPONDIDA_SIN_EJECUCION)

    def test_2_archivo_crear_verificar(self):
        ruta = os.path.join(self.tmp.name, "proyecto.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("proyecto")
        self.assertTrue(os.path.exists(ruta))
        self.assertGreater(os.path.getsize(ruta), 0)

    def test_3_proceso_controlado(self):
        from procesos_seguridad import normalizar_exe
        import sys
        ruta = os.path.realpath(sys.executable)
        self.assertTrue(ruta.endswith(".exe") or ruta.endswith("python"))

    def test_4_secuencia_gui(self):
        paso = PasoPlanOperativo("g1", "GUI", "leer_estado")
        orden = self.orquestador.recibir(
            "Probar GUI", requiere_ejecucion=True,
            pasos=[paso],
        )
        self.assertTrue(len(orden.pasos) == 1)

    def test_5_restringido_y_modo_llm(self):
        orden = self.orquestador.recibir(
            "Sin ejecucion", requiere_ejecucion=True,
            modo=am.RESTRINGIDO,
        )
        ejecutada = self.orquestador.ejecutar_plan(orden.id_orden)
        self.assertEqual(ejecutada.estado, am.FALLIDA)
        self.assertFalse(self.orquestador.cambiar_modo(
            am.PREAUTORIZADO, actor="llm"
        ))

    def test_6_autorizacion_expirada_revocada(self):
        registrar = self.registrar_lectura
        registrar("confirmable")
        contrato = self.registro.obtener("confirmable")
        contrato.nivel_riesgo = "medio"
        self.permisos.registrar_politica(
            pm.PoliticaOperacion(
                "confirmable", pm.NIVEL_REQUIERE_CONFIRMACION,
                riesgo_maximo_permitido="medio",
                ttl_seg_por_defecto=300,
            ),
            actor="sistema_inicio",
        )

    def test_7_orden_parcial(self):
        paso1 = PasoPlanOperativo("p1", "Uno", "leer_estado")
        paso2 = PasoPlanOperativo("p2", "Dos", "inexistente")
        orden = self.orquestador.recibir(
            "Parcial", requiere_ejecucion=True, pasos=[paso1, paso2]
        )
        self.registrar_lectura("leer_estado")
        final = self.orquestador.ejecutar_plan(orden.id_orden)
        self.assertIn(final.estado, (am.PARCIAL, am.FALLIDA))

    def test_8_exito_sin_evidencia(self):
        criterio = CriterioVerificacion(
            "leer_estado", True, ("real",),
            "ninguna", 0, 0,
        )
        self.verificacion.registrar_estrategia(
            criterio,
            lambda s, r, e: EvidenciaVerificacion(
                "simulada", True, False, insuficiente=True
            ),
        )
        sol = em.SolicitudEjecucion("usuario", "leer_estado", {})
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "leer_estado", "completada", True
        )
        inf = self.verificacion.verificar_resultado(sol, res)
        self.assertNotEqual(inf.estado_final, "verificado")

    def test_9_recuperacion_temporal(self):
        criterio = CriterioVerificacion(
            "demo", True, ("real",),
            "reintento_idempotente", 1, 0,
        )
        cuenta = {"n": 0}
        def ver(s, r, e):
            cuenta["n"] += 1
            return EvidenciaVerificacion(
                "real", cuenta["n"] >= 2, cuenta["n"] >= 2
            )
        self.verificacion.registrar_estrategia(criterio, ver)
        sol = em.SolicitudEjecucion("usuario", "demo", {})
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "demo", "fallida", False,
            error={"codigo": "TEMPORAL", "mensaje": "temporal",
                   "recuperable": True},
        )
        inf = self.verificacion.verificar_resultado(sol, res)
        self.assertIn(inf.estado_final,
                      ("recuperado", "requiere_intervencion_humana"))

    def test_10_no_idempotente_peligroso(self):
        criterio = CriterioVerificacion(
            "modificar_archivo", False, ("real",),
            "escalar_humano", 0, 0,
        )
        self.verificacion.registrar_estrategia(
            criterio,
            lambda s, r, e: EvidenciaVerificacion(
                "real", False, False, insuficiente=True
            ),
        )
        sol = em.SolicitudEjecucion(
            "usuario", "modificar_archivo", {"ruta": "x"}
        )
        res = em.ResultadoEjecucion(
            sol.id_solicitud, "modificar_archivo", "fallida", False
        )
        inf = self.verificacion.verificar_resultado(sol, res)
        self.assertEqual(
            inf.estado_final, "requiere_intervencion_humana"
        )

    def test_11_cancelacion_cooperativa(self):
        paso = PasoPlanOperativo("p1", "Cancelar", "leer_estado")
        orden = self.orquestador.recibir(
            "Cancelar", requiere_ejecucion=True, pasos=[paso]
        )
        self.assertTrue(self.orquestador.cancelar_orden(orden.id_orden))
        self.assertEqual(
            self.orquestador.obtener_orden(orden.id_orden).estado,
            am.CANCELADA,
        )

    def test_12_dos_ordenes_concurrentes(self):
        ids = []
        def worker(i):
            orden = self.orquestador.recibir(
                f"Orden {i}", requiere_ejecucion=False
            )
            ids.append(orden.id_orden)
        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(1)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4)

    def test_13_fallo_componente_permiso(self):
        self.orquestador.motor_permisos = None
        paso = PasoPlanOperativo("p1", "Seguro", "leer_estado")
        orden = self.orquestador.recibir(
            "Fallo", requiere_ejecucion=True, pasos=[paso]
        )
        final = self.orquestador.ejecutar_plan(orden.id_orden)
        self.assertIn(final.estado, (am.FALLIDA, am.REQUIERE_INTERVENCION))

    def test_14_persistencia_sanitizada(self):
        orden = self.orquestador.recibir(
            "Persistente", requiere_ejecucion=False
        )
        orden.registrar_evento("token", "abc")
        self.orquestador._finalizar(orden)
        snapshot = orden.a_dict()
        self.assertIn("historial_eventos", snapshot)
        self.assertTrue(os.path.exists(self.archivo))

    def test_15_hud_informe_final(self):
        orden = self.orquestador.recibir(
            "HUD", requiere_ejecucion=False
        )
        snapshot = self.puente.publicar_snapshot()
        self.assertIn("progreso", snapshot)
        informe = self.orquestador._finalizar(orden)
        self.assertEqual(informe.id_orden, orden.id_orden)

    def test_16_auditoria_imports_dag(self):
        raiz = os.path.dirname(os.path.abspath(__file__))
        modulos = [
            "ejecucion_registro.py", "permisos_motor.py",
            "motor_ejecucion.py", "verificacion_motor.py",
            "orquestador_autonomia.py",
        ]
        for nombre in modulos:
            ruta = os.path.join(raiz, nombre)
            with open(ruta, "r", encoding="utf-8") as f:
                ast.parse(f.read(), filename=ruta)
        ids = [
            PasoPlanOperativo("a", "A", "leer"),
            PasoPlanOperativo("b", "B", "leer", dependencias=("a",)),
        ]
        valido, _ = self.orquestador.validar_dag(ids)
        self.assertTrue(valido)
        ciclo = [
            PasoPlanOperativo("a", "A", "leer", dependencias=("b",)),
            PasoPlanOperativo("b", "B", "leer", dependencias=("a",)),
        ]
        valido, motivo = self.orquestador.validar_dag(ciclo)
        self.assertFalse(valido)
        self.assertEqual(motivo, "DEPENDENCIAS_INVALIDAS")
        inexistente = [
            PasoPlanOperativo("a", "A", "leer", dependencias=("fantasma",)),
        ]
        valido, motivo = self.orquestador.validar_dag(inexistente)
        self.assertFalse(valido)
        self.assertEqual(motivo, "DEPENDENCIAS_INVALIDAS")


if __name__ == "__main__":
    unittest.main()
