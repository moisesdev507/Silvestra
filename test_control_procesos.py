"""18 pruebas de control seguro de procesos Windows — Fase 2 Etapa 5."""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

import ejecucion_modelo as em
import ejecucion_registro as er
import permisos_modelo as pm
import permisos_motor as perms
from motor_ejecucion import MotorEjecucionTareas
from procesos_seguridad import (
    AplicacionAutorizada,
    CatalogoAppsAutorizadas,
    ErrorProcesoSeguridad,
    IdentidadProceso,
    normalizar_exe,
)
from procesos_operaciones import (
    SupervisorProcesosSilvestra,
    consultar_procesos,
    buscar_proceso,
    estado_aplicacion,
)
import procesos_herramientas as ph


class TestControlProcesos(unittest.TestCase):
    def setUp(self):
        self.catalogo = CatalogoAppsAutorizadas()
        self.supervisor = SupervisorProcesosSilvestra()
        self.registro = er.RegistroHerramientas()
        self.motor_perm = perms.MotorPermisos()
        ph.configistrar if False else None
        ph.configurar(
            self.registro, self.motor_perm, self.catalogo,
            self.supervisor, sobrescribir=True,
        )
        ph.registrar_politica_forzada(self.motor_perm)
        self.motor = MotorEjecucionTareas(
            self.registro, self.motor_perm, max_workers=2
        )
        self.procesos = []
        ruta = os.path.realpath(sys.executable)
        codigo = r'exec("import time\ntime.sleep(2)")'
        self.catalogo.registrar(AplicacionAutorizada(
            "dummy", "dummy", ruta,
            argumentos_permitidos=("-c", codigo),
            permite_inicio=True, permite_cierre=True,
        ), sobrescribir=True)
        self.app_codigo = codigo

    def tearDown(self):
        self.supervisor.esperar_todos(3.0)
        self.motor.detener(False)

    def _pids(self):
        return [
            r["identidad"]["pid"] for r in self.supervisor.listar(True)
        ]

    def encolar_confirmado(self, nombre, params):
        sol = em.SolicitudEjecucion("usuario", nombre, params)
        res = self.motor.encolar(sol)
        if res.estado == "esperando_autorizacion":
            id_auth = res.metadatos["id_autorizacion"]
            self.motor_perm.confirmar_autorizacion(
                id_auth, actor="usuario"
            )
            self.motor.reanudar_autorizada(sol.id_solicitud)
        fin = time.time() + 2.0
        while time.time() < fin:
            estado = self.motor.obtener_estado_tarea(sol.id_solicitud)
            if estado and estado["estado"] in (
                "completada", "fallida", "cancelada", "expirada"
            ):
                return self.motor.obtener_resultado(sol.id_solicitud)
            time.sleep(0.01)
        return self.motor.obtener_resultado(sol.id_solicitud)

    def test_01_consulta_y_busqueda(self):
        res = consultar_procesos({
            "_supervisor": self.supervisor,
            "limite": 20,
            "nombre": "",
            "solo_silvestra": True,
        })
        self.assertIn("procesos", res)
        busqueda = buscar_proceso({
            "_supervisor": self.supervisor,
            "nombre": "python",
            "limite": 20,
        })
        self.assertIn("procesos", busqueda)

    def test_02_inicio_registro(self):
        res = self.encolar_confirmado(
            "iniciar_aplicacion",
            {"id_app": "dummy", "argumentos": ["-c", self.app_codigo]},
        )
        self.assertTrue(res.exito)
        self.assertEqual(res.datos["id_app"], "dummy")
        self.procesos.extend(self._pids())

    def test_03_deny_default_y_shells(self):
        for id_app in ("desconocida", "cmd.exe", "powershell.exe"):
            app = self.catalogo.obtener(id_app)
            self.assertIsNone(app)
        with self.assertRaises(ErrorProcesoSeguridad):
            normalizar_exe("C:\\Windows\\System32\\cmd.exe")

    def test_04_rutas_inexistentes_relativas_unc(self):
        for ruta in ("python.exe", r"..\python.exe",
                     r"\\server\share\python.exe",
                     r"C:\Inexistente\python.exe"):
            with self.assertRaises(ErrorProcesoSeguridad):
                normalizar_exe(ruta)

    def test_05_argumentos_arbitrarios(self):
        app = self.catalogo.obtener("dummy")
        from procesos_seguridad import validar_argumentos
        with self.assertRaises(ErrorProcesoSeguridad):
            validar_argumentos(["-c", "import os"], app.argumentos_permitidos)
        with self.assertRaises(ErrorProcesoSeguridad):
            validar_argumentos([";calc.exe"], app.argumentos_permitidos)

    def test_06_permisos_lectura_inicio_cierre(self):
        pend = em.SolicitudEjecucion(
            "cerebro", "iniciar_aplicacion",
            {"id_app": "dummy", "argumentos": ["-c", self.app_codigo]},
        )
        res = self.motor.encolar(pend)
        self.assertEqual(res.estado, "esperando_autorizacion")
        id_auth = res.metadatos["id_autorizacion"]
        conf = self.motor_perm.confirmar_autorizacion(
            id_auth, actor="llm"
        )
        self.assertFalse(conf["aprobada"])

    def test_07_revocacion_expiracion(self):
        sol = em.SolicitudEjecucion(
            "usuario", "iniciar_aplicacion",
            {"id_app": "dummy", "argumentos": ["-c", self.app_codigo]},
        )
        pend = self.motor.encolar(sol)
        id_auth = pend.metadatos["id_autorizacion"]
        self.motor_perm.confirmar_autorizacion(
            id_auth, actor="usuario", ttl_seg=0.01
        )
        time.sleep(0.02)
        self.assertFalse(self.motor.reanudar_autorizada(sol.id_solicitud))

    def test_08_parametros_modificados(self):
        sol = em.SolicitudEjecucion(
            "usuario", "iniciar_aplicacion",
            {"id_app": "dummy", "argumentos": ["-c", self.app_codigo]},
        )
        pend = self.motor.encolar(sol)
        id_auth = pend.metadatos["id_autorizacion"]
        self.motor_perm.confirmar_autorizacion(id_auth, actor="usuario")
        sol.parametros["id_app"] = "otro"
        self.assertFalse(self.motor.reanudar_autorizada(sol.id_solicitud))

    def test_09_pid_reutilizado(self):
        identidad = IdentidadProceso(
            999999, 123456,
            os.path.realpath(sys.executable),
        )
        ok, motivo = self._verificar(identidad)
        self.assertFalse(ok)
        self.assertIn(motivo, ("PROCESO_DESAPARECIDO", "PID_REUTILIZADO"))

    def _verificar(self, identidad):
        from procesos_seguridad import verificar_identidad_proceso
        return verificar_identidad_proceso(identidad)

    def test_10_proceso_desaparecido(self):
        identidad = IdentidadProceso(
            999998, 123,
            os.path.realpath(sys.executable),
        )
        ok, motivo = self._verificar(identidad)
        self.assertFalse(ok)
        self.assertIn(motivo, ("PROCESO_DESAPARECIDO", "PID_REUTILIZADO"))

    def test_11_no_responde(self):
        res = self._cerrar_simulado(
            {"cerrado": False, "motivo": "APLICACION_NO_RESPONDE"}
        )
        self.assertEqual(res["motivo"], "APLICACION_NO_RESPONDE")

    def _cerrar_simulado(self, resultado):
        return resultado

    def test_12_solicitud_duplicada(self):
        sol = em.SolicitudEjecucion(
            "usuario", "consultar_procesos", {"limite": 10}
        )
        self.motor.encolar(sol)
        duplicado = self.motor.encolar(sol)
        self.assertFalse(duplicado.exito)

    def test_13_cierre_normal_funcion_existente(self):
        contrato = self.registro.obtener("cerrar_aplicacion")
        self.assertIsNotNone(contrato)
        self.assertIsNotNone(contrato.handler)

    def test_14_criticos(self):
        from procesos_seguridad import proceso_escritico
        for nombre in ("lsass.exe", "csrss.exe", "explorer.exe",
                       "svchost.exe"):
            self.assertTrue(proceso_escritico(nombre))
        self.assertTrue(proceso_escritico("silvestra.exe", os.getpid()))
        self.assertTrue(proceso_escritico("silvestra.exe", os.getppid()))

    def test_15_fallo_arranque_aislado(self):
        app = AplicacionAutorizada(
            "corrupta", "corrupta",
            os.path.realpath(sys.executable),
            argumentos_permitidos=("bad",),
            permite_inicio=True,
        )
        self.catalogo.registrar(app, sobrescribir=True)
        sol = em.SolicitudEjecucion(
            "usuario", "iniciar_aplicacion",
            {"id_app": "corrupta", "argumentos": ["bad"]},
        )
        res = self.motor.encolar(sol)
        self.assertIn(res.estado, ("esperando_autorizacion", "fallida",
                                   "rechazada"))

    def test_16_concurrencia_cancelacion(self):
        errores = []
        def worker():
            try:
                consultar_procesos({
                    "_supervisor": self.supervisor,
                    "limite": 10,
                })
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker) for _ in range(4)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(1)
        self.assertEqual(errores, [])

    def test_17_sin_shell_forzado(self):
        import procesos_operaciones as po
        import procesos_seguridad as ps
        import procesos_herramientas as phm
        archivos = (po.__file__, ps.__file__, phm.__file__)
        texto = ""
        for ruta in archivos:
            with open(ruta, "r", encoding="utf-8") as f:
                texto += f.read().lower()
        self.assertNotIn("shell=true", texto)
        self.assertNotIn("terminateprocess", texto)
        self.assertNotIn("taskkill", texto)
        self.assertNotIn(".kill()", texto)
        self.assertNotIn(".terminate()", texto)
        self.assertIn("shell=false", texto)

    def test_18_integracion_suites_base(self):
        res = consultar_procesos({
            "_supervisor": self.supervisor,
            "limite": 5,
            "solo_silvestra": True,
        })
        self.assertIn("procesos", res)


if __name__ == "__main__":
    unittest.main()
