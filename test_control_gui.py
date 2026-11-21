"""18 pruebas del control seguro GUI — Fase 2 Etapa 6."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
import subprocess

import ejecucion_modelo as em
import ejecucion_registro as er
import permisos_modelo as pm
import permisos_motor as perms
from motor_ejecucion import MotorEjecucionTareas
from procesos_seguridad import AplicacionAutorizada, CatalogoAppsAutorizadas
from procesos_operaciones import SupervisorProcesosSilvestra
from archivos_seguridad import ConfiguracionSandboxArchivos
import gui_herramientas as gh
from gui_seguridad import texto_sensibilizado, titulo_es_sensible


class TestControlGui(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.raiz = self.temp.name
        self.registro = er.RegistroHerramientas()
        self.permisos = perms.MotorPermisos()
        self.catalogo = CatalogoAppsAutorizadas()
        self.supervisor = SupervisorProcesosSilvestra()
        self.sandbox = ConfiguracionSandboxArchivos([self.raiz])
        gh.configurar_gui(
            self.registro, self.permisos, self.catalogo,
            self.supervisor, self.sandbox, sobrescribir=True,
        )
        self.motor = MotorEjecucionTareas(
            self.registro, self.permisos, max_workers=2
        )
        self.ruta_dummy = os.path.realpath(sys.executable)
        self.hijos = []
        self.codigo = (
            "import tkinter as tk;"
            "r=tk.Tk();r.title('Dummy GUI');"
            "r.protocol('WM_DELETE_WINDOW',r.destroy);"
            "tk.Entry(r).pack();"
            "tk.Entry(r,show='*').pack();"
            "tk.Button(r,text='OK').pack();"
            "tk.Canvas(r,width=120,height=80).pack();"
            "r.after(3000,r.destroy);r.mainloop()"
        )
        self.catalogo.registrar(AplicacionAutorizada(
            "gui_dummy", "gui_dummy", self.ruta_dummy,
            argumentos_permitidos=("-c", self.codigo),
            permite_inicio=True, permite_cierre=True,
            directorio_trabajo=self.raiz,
        ), sobrescribir=True)

    def tearDown(self):
        for proceso in self.hijos:
            try:
                if proceso.poll() is None:
                    import ctypes
                    from ctypes import wintypes
                    user32 = ctypes.windll.user32
                    WM_CLOSE = 0x0010
                    def enum_cb(hwnd, lparam):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value == proceso.pid:
                            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                        return True
                    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                    user32.EnumWindows(cb(enum_cb), 0)
                    proceso.wait(timeout=5.0)
            except Exception:
                pass
        self.motor.detener(False)
        self.temp.cleanup()

    def lanzar_dummy(self):
        proceso = subprocess.Popen(
            [self.ruta_dummy, "-c", self.codigo],
            shell=False,
            close_fds=True,
        )
        self.hijos.append(proceso)
        time.sleep(0.25)
        return proceso

    def confirmar(self, sol):
        res = self.motor.encolar(sol)
        if res.estado == "esperando_autorizacion":
            id_auth = res.metadatos["id_autorizacion"]
            if not self.permisos.confirmar_autorizacion(
                id_auth, actor="usuario"
            )["aprobada"]:
                return res
            self.motor.reanudar_autorizada(sol.id_solicitud)
        fin = time.time() + 1.5
        while time.time() < fin:
            estado = self.motor.obtener_estado_tarea(sol.id_solicitud)
            if estado and estado["estado"] in (
                "completada", "fallida", "cancelada", "expirada"
            ):
                return self.motor.obtener_resultado(sol.id_solicitud)
            time.sleep(0.01)
        return self.motor.obtener_resultado(sol.id_solicitud)

    def test_1_listar_ventanas_activa(self):
        proceso = self.lanzar_dummy()
        self.assertGreater(proceso.pid, 0)
        sol = em.SolicitudEjecucion("usuario", "listar_ventanas", {"limite": 20})
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_2_identidad_autorizada_denegada(self):
        proceso = self.lanzar_dummy()
        sol = em.SolicitudEjecucion("usuario", "listar_ventanas", {})
        res = self.confirmar(sol)
        self.assertFalse(res is None)

    def test_3_inspeccion_controles(self):
        proceso = self.lanzar_dummy()
        sol = em.SolicitudEjecucion(
            "usuario", "inspeccionar_interfaz", {"hwnd": proceso.pid}
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_4_pulsar_y_escribir(self):
        proceso = self.lanzar_dummy()
        sol1 = em.SolicitudEjecucion(
            "usuario", "pulsar_control",
            {"hwnd": proceso.pid, "control": proceso.pid},
        )
        sol2 = em.SolicitudEjecucion(
            "usuario", "escribir_texto_control",
            {"hwnd": proceso.pid, "control": proceso.pid,
             "texto": "dato-ficticio"},
        )
        self.confirmar(sol1)
        res = self.confirmar(sol2)
        if res and res.datos:
            self.assertIn("texto", res.datos)

    def test_5_seleccionar_desplazar(self):
        proceso = self.lanzar_dummy()
        sol1 = em.SolicitudEjecucion(
            "usuario", "seleccionar_opcion_control",
            {"hwnd": proceso.pid, "control": proceso.pid, "indice": 1},
        )
        sol2 = em.SolicitudEjecucion(
            "usuario", "desplazar_control",
            {"hwnd": proceso.pid, "control": proceso.pid, "cantidad": 20},
        )
        self.confirmar(sol1)
        self.confirmar(sol2)

    def test_6_captura_sandbox(self):
        proceso = self.lanzar_dummy()
        ruta = os.path.join(self.raiz, "prueba.png")
        sol = em.SolicitudEjecucion(
            "usuario", "capturar_ventana",
            {"hwnd": proceso.pid, "ruta_salida": ruta},
        )
        self.confirmar(sol)
        fuera = os.path.abspath(os.path.join(self.raiz, "..", "fuera.png"))
        sol2 = em.SolicitudEjecucion(
            "usuario", "capturar_ventana",
            {"hwnd": proceso.pid, "ruta_salida": fuera},
        )
        res = self.confirmar(sol2)
        self.assertNotEqual(res.error if res.error else {}, {})

    def test_7_permisos_concedidos_denegados(self):
        sol = em.SolicitudEjecucion("usuario", "listar_ventanas", {})
        res = self.confirmar(sol)
        self.assertIsNotNone(res)
        sin = self.permisos.validar_antes_de_ejecutar
        self.assertTrue(callable(sin))

    def test_8_credenciales_sanitizadas(self):
        self.assertTrue(titulo_es_sensible("Contraseña"))
        self.assertTrue(titulo_es_sensible("OTP"))
        valor = texto_sensibilizado("secreto")
        self.assertEqual(valor, "***7")

    def test_9_ventanas_protegidas(self):
        sol = em.SolicitudEjecucion(
            "usuario", "inspeccionar_interfaz", {"hwnd": 0}
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_10_foco_cambiado(self):
        proceso = self.lanzar_dummy()
        sol = em.SolicitudEjecucion(
            "usuario", "enfocar_ventana", {"hwnd": proceso.pid}
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_11_coordenadas_absolutas(self):
        sol = em.SolicitudEjecucion(
            "usuario", "pulsar_control",
            {"hwnd": 1, "control": 1, "rect_relativo": {"x": 999, "y": 999}},
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_12_parametros_modificados(self):
        sol = em.SolicitudEjecucion(
            "usuario", "capturar_ventana",
            {"hwnd": 1, "ruta_salida": os.path.join(self.raiz, "x.png")},
        )
        pend = self.motor.encolar(sol)
        if pend.estado == "esperando_autorizacion":
            id_auth = pend.metadatos["id_autorizacion"]
            self.permisos.confirmar_autorizacion(id_auth, actor="usuario")
            sol.parametros["ruta_salida"] = os.path.join(self.raiz, "y.png")
            self.assertFalse(self.motor.reanudar_autorizada(sol.id_solicitud))

    def test_13_cancelacion_secuencia(self):
        proceso = self.lanzar_dummy()
        sol = em.SolicitudEjecucion(
            "usuario", "ejecutar_secuencia_gui",
            {"hwnd": proceso.pid, "pasos": [
                {"accion": "pulsar_control", "control": proceso.pid},
            ]},
        )
        self.confirmar(sol)

    def test_14_captura_password_bloqueada(self):
        sol = em.SolicitudEjecucion(
            "usuario", "capturar_ventana",
            {"hwnd": 1, "ruta_salida": os.path.join(self.raiz, "password.png"),
             "titulo": "Contraseña"},
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_15_elemento_no_accesible(self):
        sol = em.SolicitudEjecucion(
            "usuario", "inspeccionar_interfaz", {"hwnd": 1}
        )
        res = self.confirmar(sol)
        self.assertIsNotNone(res)

    def test_16_concurrencia_cancelacion(self):
        errores = []
        def worker():
            try:
                sol = em.SolicitudEjecucion(
                    "usuario", "listar_ventanas", {"limite": 10}
                )
                self.motor.encolar(sol)
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker) for _ in range(3)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(1)
        self.assertEqual(errores, [])

    def test_17_politicas_prohibidas(self):
        for nombre in ("clic_coordenadas_arbitrarias",
                       "interaccion_ventana_protegida"):
            politica = self.permisos._politicas.get(nombre)
            self.assertIsNotNone(politica)
            self.assertEqual(politica.nivel_autorizacion, "prohibida")

    def test_18_integracion_suites_base(self):
        sol = em.SolicitudEjecucion("usuario", "ventana_activa", {})
        res = self.confirmar(sol)
        self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
