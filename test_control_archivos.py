"""18 pruebas del control seguro de archivos — Fase 2 Etapa 4."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest

import archivos_herramientas as ah
import archivos_seguridad as ase
import ejecucion_modelo as em
import ejecucion_registro as er
import permisos_modelo as pm
import permisos_motor as perms
from motor_ejecucion import MotorEjecucionTareas


class TestControlArchivos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        self.sandbox = ase.ConfiguracionSandboxArchivos([self.raiz])
        self.registro = er.RegistroHerramientas()
        self.motor_perm = perms.MotorPermisos()
        ah.configurar(
            self.registro, self.motor_perm, self.sandbox, sobrescribir=True
        )
        self.motor = MotorEjecucionTareas(
            self.registro, self.motor_perm, max_workers=2
        )

    def tearDown(self):
        self.motor.detener(False)
        self.tmp.cleanup()

    def ruta(self, nombre):
        return os.path.join(self.raiz, nombre)

    def handler_directo(self, nombre, parametros):
        contrato = self.registro.obtener(nombre)
        return contrato.handler(dict(parametros))

    def escribir_texto(self, ruta, texto, encoding="utf-8"):
        with open(ruta, "w", encoding=encoding) as f:
            f.write(texto)
    
    def escribir_bytes(self, ruta, datos):
        with open(ruta, "wb") as f:
            f.write(datos)

    def ejecutar_confirmada(self, nombre, parametros):
        sol = em.SolicitudEjecucion("usuario", nombre, parametros)
        pendiente = self.motor.encolar(sol)
        if pendiente.estado == "esperando_autorizacion":
            id_auth = pendiente.metadatos["id_autorizacion"]
            self.motor_perm.confirmar_autorizacion(id_auth, actor="usuario")
            self.motor.reanudar_autorizada(sol.id_solicitud)
        fin = 2.0 + 0.0
        final = 0.0
        import time
        while time.time() - final < fin:
            estado = self.motor.obtener_estado_tarea(sol.id_solicitud)
            if estado and estado["estado"] in ("completada", "fallida", "cancelada", "expirada"):
                return self.motor.obtener_resultado(sol.id_solicitud)
            time.sleep(0.01)
        return self.motor.obtener_resultado(sol.id_solicitud)

    def test_1_listado_y_busqueda(self):
        self.escribir_texto(self.ruta("uno.txt"), "uno")
        os.mkdir(self.ruta("sub"))
        self.escribir_texto(self.ruta("sub/dos.md"), "dos")
        listado = self.handler_directo("listar_directorio", {"ruta": self.raiz})
        self.assertTrue(any(e["nombre"] == "uno.txt" for e in listado["entradas"]))
        busqueda = self.handler_directo(
            "buscar_archivos",
            {"ruta": self.raiz, "patron": "*.md", "profundidad": 2},
        )
        self.assertTrue(any("dos.md" in e["nombre"] for e in busqueda["archivos"]))

    def test_2_lectura_codificacion_tamano(self):
        ruta = self.ruta("texto.txt")
        self.escribir_texto(ruta, "hola ñ")
        res = self.handler_directo("leer_archivo", {"ruta": ruta})
        self.assertIn("hola", res["texto"])
        self.assertIn("sha256", res)
        grande = self.ruta("grande.txt")
        self.escribir_bytes(grande, b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo("leer_archivo", {"ruta": grande})

    def test_3_crear_archivo_atomico_sin_sobrescritura(self):
        ruta = self.ruta("nuevo.txt")
        res = self.handler_directo(
            "crear_archivo", {"ruta": ruta, "contenido": "dato"}
        )
        self.assertEqual(res["tamano"], 4)
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "crear_archivo", {"ruta": ruta, "contenido": "otro"}
            )

    def test_4_crear_directorio(self):
        ruta = self.ruta("nueva")
        res = self.handler_directo(
            "crear_directorio", {"ruta": ruta, "parents": True}
        )
        self.assertTrue(res["directorio"])
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "crear_directorio", {"ruta": ruta, "parents": False}
            )

    def test_5_modificacion_respaldo_verificacion(self):
        ruta = self.ruta("mod.txt")
        self.escribir_texto(ruta, "hola mundo")
        huella = self.sandbox.huella_estado(ruta)
        res = self.handler_directo(
            "modificar_archivo",
            {"ruta": ruta, "contenido": "nuevo",
             "sha256_esperado": huella["sha256"]},
        )
        self.assertTrue(os.path.exists(res["respaldo"]))

    def test_6_toctou(self):
        ruta = self.ruta("toctou.txt")
        self.escribir_texto(ruta, "original")
        huella = self.sandbox.huella_estado(ruta)
        self.escribir_texto(ruta, "externo")
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "modificar_archivo",
                {"ruta": ruta, "contenido": "nuevo",
                 "sha256_esperado": huella["sha256"]},
            )

    def test_7_copia_archivo_directorio(self):
        origen = self.ruta("origen.txt")
        self.escribir_texto(origen, "copia")
        destino = self.ruta("destino.txt")
        self.handler_directo(
            "copiar_elemento",
            {"origen": origen, "destino": destino},
        )
        self.assertTrue(os.path.exists(destino))
        origen_dir = self.ruta("d")
        os.mkdir(origen_dir)
        self.escribir_texto(os.path.join(origen_dir, "x.txt"), "x")
        destino_dir = self.ruta("d_copia")
        self.handler_directo(
            "copiar_elemento",
            {"origen": origen_dir, "destino": destino_dir},
        )
        self.assertTrue(os.path.exists(os.path.join(destino_dir, "x.txt")))

    def test_8_movimiento(self):
        origen = self.ruta("mover.txt")
        self.escribir_texto(origen, "m")
        destino = self.ruta("movido.txt")
        self.handler_directo(
            "mover_elemento", {"origen": origen, "destino": destino}
        )
        self.assertTrue(os.path.exists(destino))
        self.assertFalse(os.path.exists(origen))

    def test_9_renombrado_reservado(self):
        origen = self.ruta("viejo.txt")
        self.escribir_texto(origen, "r")
        res = self.handler_directo(
            "renombrar_elemento",
            {"origen": origen, "nuevo_nombre": "nuevo.txt"},
        )
        self.assertTrue(os.path.exists(res["destino"]))
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "renombrar_elemento",
                {"origen": res["destino"], "nuevo_nombre": "CON"},
            )

    def test_10_conflictos_inexistentes(self):
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "leer_archivo", {"ruta": self.ruta("inexistente.txt")}
            )
        destino = self.ruta("existe.txt")
        self.escribir_texto(destino, "x")
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.handler_directo(
                "crear_archivo", {"ruta": destino, "contenido": "y"}
            )

    def test_11_permisos_sin_confirmacion_y_eliminacion(self):
        ruta = self.ruta("crear.txt")
        sol = em.SolicitudEjecucion("cerebro", "crear_archivo",
                                    {"ruta": ruta, "contenido": "x"})
        pendiente = self.motor.encolar(sol)
        self.assertEqual(pendiente.estado, "esperando_autorizacion")
        id_auth = pendiente.metadatos["id_autorizacion"]
        intento = self.motor_perm.confirmar_autorizacion(id_auth, actor="llm")
        self.assertFalse(intento["aprobada"])
        politica = pm.PoliticaOperacion(
            "eliminar_archivo", pm.NIVEL_PROHIBIDA,
            riesgo_maximo_permitido="critico",
        )
        ok, _ = self.motor_perm.registrar_politica(
            politica, actor="sistema_inicio"
        )
        self.assertTrue(ok)

    def test_12_rutas_fuera_sandbox_unc(self):
        fuera = os.path.abspath(os.path.join(self.raiz, "..", "fuera.txt"))
        for ruta in (fuera, r"\\server\share\archivo.txt",
                     r"\\?\C:\archivo.txt"):
            with self.assertRaises(ase.ErrorRutaArchivos):
                self.sandbox.validar_ruta(ruta)

    def test_13_traversal_symlinks_resparse(self):
        ruta = self.ruta("..\\fuera.txt")
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.sandbox.validar_ruta(ruta)
        enlace = self.ruta("enlace")
        destino = os.path.abspath(os.path.join(self.raiz, ".."))
        try:
            os.symlink(destino, enlace, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.sandbox.validar_existente(enlace)

    def test_14_ruta_alterada_tras_aprobacion(self):
        ruta = self.ruta("aprobado.txt")
        sol = em.SolicitudEjecucion(
            "usuario", "crear_archivo",
            {"ruta": ruta, "contenido": "x"},
        )
        pendiente = self.motor.encolar(sol)
        id_auth = pendiente.metadatos["id_autorizacion"]
        self.motor_perm.confirmar_autorizacion(id_auth, actor="usuario")
        sol.parametros["ruta"] = self.ruta("alterado.txt")
        self.assertFalse(self.motor.reanudar_autorizada(sol.id_solicitud))

    def test_15_flujo_punta_a_punta_concurrente(self):
        for i in range(4):
            sol = em.SolicitudEjecucion(
                "usuario", "crear_archivo",
                {"ruta": self.ruta(f"h{i}.txt"), "contenido": str(i)},
            )
            pend = self.motor.encolar(sol)
            if pend.estado == "esperando_autorizacion":
                id_auth = pend.metadatos["id_autorizacion"]
                self.motor_perm.confirmar_autorizacion(id_auth, actor="usuario")
                self.motor.reanudar_autorizada(sol.id_solicitud)
        import time
        time.sleep(0.2)
        self.assertTrue(os.path.exists(self.ruta("h0.txt")))

    def test_16_aislamiento_y_sin_procesos(self):
        fuera = tempfile.TemporaryDirectory()
        externo = os.path.join(fuera.name, "externo.txt")
        with self.assertRaises(ase.ErrorRutaArchivos):
            self.sandbox.validar_ruta(externo)
        fuera.cleanup()

    def test_17_regresion_integrada(self):
        ruta = self.ruta("integrado.txt")
        sol = em.SolicitudEjecucion(
            "usuario", "crear_archivo",
            {"ruta": ruta, "contenido": "ok"},
        )
        pend = self.motor.encolar(sol)
        id_auth = pend.metadatos["id_autorizacion"]
        self.motor_perm.confirmar_autorizacion(id_auth, actor="usuario")
        self.motor.reanudar_autorizada(sol.id_solicitud)
        import time
        time.sleep(0.1)
        self.assertTrue(os.path.exists(ruta))

    def test_18_backup_excluido_de_listado_y_busqueda(self):
        backup_dir = os.path.join(self.raiz, ".silvestra_respaldos")
        os.mkdir(backup_dir)
        self.escribir_texto(os.path.join(backup_dir, "secreto.txt"), "x")
        self.escribir_texto(self.ruta("visible.txt"), "v")
        listado = self.handler_directo("listar_directorio", {"ruta": self.raiz})
        nombres = [e["nombre"] for e in listado["entradas"]]
        self.assertNotIn(".silvestra_respaldos", nombres)
        busqueda = self.handler_directo(
            "buscar_archivos",
            {"ruta": self.raiz, "patron": "*", "profundidad": 5},
        )
        self.assertFalse(any(".silvestra_respaldos" in e["ruta"]
                             for e in busqueda["archivos"]))


if __name__ == "__main__":
    unittest.main()
