"""Pruebas del nucleo arquitectonico de ejecucion — Fase 2 Etapa 1."""
from __future__ import annotations

import threading
import unittest

import ejecucion_acciones
import ejecucion_modelo as em
import ejecucion_registro as er
import planificador_modelo as pm


class TestEjecucionArquitectura(unittest.TestCase):
    def setUp(self) -> None:
        self.registro = er.RegistroHerramientas()
        self.sistema = er.SistemaEjecucion(self.registro)

    def contrato(self, nombre="consulta_estado", habilitada=True, handler=None):
        return em.ContratoHerramienta(
            nombre=nombre,
            categoria="consulta",
            descripcion="Consulta segura de estado",
            parametros_esquema={
                "requeridos": ["texto"],
                "opcionales": ["limite"],
                "tipos": {"texto": "str", "limite": "int"},
            },
            handler=handler,
            nivel_riesgo="medio",
            requiere_confirmacion=True,
            permisos_requeridos=("lectura.estado",),
            cancelable=True,
            asincrona=True,
            timeout_seg=12.5,
            habilitada=habilitada,
        )

    def test_registro_consulta_listado_y_duplicados(self) -> None:
        primero = self.contrato()
        self.assertTrue(self.registro.registrar(primero))
        self.assertTrue(self.registro.existe("consulta_estado"))
        self.assertEqual(self.registro.obtener("consulta_estado").nombre, "consulta_estado")
        self.assertEqual(len(self.registro.listar(categoria="consulta")), 1)
        with self.assertRaises(ValueError):
            self.registro.registrar(self.contrato())
        self.assertTrue(self.registro.registrar(self.contrato("consulta_estado"), sobrescribir=True))
        self.assertFalse(self.registro.existe("fantasma"))

    def test_contrato_invalido_rechazado(self) -> None:
        invalido = em.ContratoHerramienta(
            nombre="nombre con espacios", categoria="consulta", descripcion="x"
        )
        with self.assertRaises(ValueError):
            self.registro.registrar(invalido)
        with self.assertRaises(ValueError):
            em.ContratoHerramienta(
                "riesgo", "consulta", "x", nivel_riesgo="desconocido"
            )

    def test_solicitud_uuid_params_requeridos_y_tipos(self) -> None:
        self.registro.registrar(self.contrato())
        sol1 = em.SolicitudEjecucion("usuario", "consulta_estado", {"texto": "hola", "limite": 3})
        sol2 = em.SolicitudEjecucion("cerebro", "consulta_estado", {"texto": "adios"})
        self.assertNotEqual(sol1.id_solicitud, sol2.id_solicitud)
        valido, motivo, _ = self.registro.validar_solicitud(sol1)
        self.assertTrue(valido, motivo)
        res = self.sistema.procesar(sol1)
        self.assertTrue(res.exito)
        self.assertEqual(res.estado, em.ESTADO_COMPLETADA)

        faltante = em.SolicitudEjecucion("usuario", "consulta_estado", {})
        valido, _, _ = self.registro.validar_solicitud(faltante)
        self.assertFalse(valido)
        invalido = em.SolicitudEjecucion("usuario", "consulta_estado", {"texto": 123})
        valido, motivo, _ = self.registro.validar_solicitud(invalido)
        self.assertFalse(valido)
        self.assertIn("Tipo", motivo)

    def test_resultados_inexistente_deshabilitada_parametros(self) -> None:
        inexistente = em.SolicitudEjecucion("cerebro", "no_existe", {})
        res = self.sistema.procesar(inexistente)
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "HERRAMIENTA_INEXISTENTE")

        self.registro.registrar(self.contrato("apagada", habilitada=False))
        res = self.sistema.procesar(em.SolicitudEjecucion("usuario", "apagada", {"texto": "x"}))
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "HERRAMIENTA_DESHABILITADA")

        self.registro.registrar(self.contrato())
        res = self.sistema.procesar(em.SolicitudEjecucion("usuario", "consulta_estado", {"texto": True}))
        self.assertFalse(res.exito)
        self.assertEqual(res.error["codigo"], "PARAMETROS_INVALIDOS")

    def test_handler_seguro_excepcion_y_hooks(self) -> None:
        def seguro(params):
            return {"eco": params["texto"]}

        def fallo(params):
            raise RuntimeError("fallo interno simulado")

        vistos = []
        hooks = (
            lambda s, c: vistos.append(("pre", s.herramienta)),
            lambda s, c, r: vistos.append(("post", r.estado)),
        )
        self.sistema.post_ejecucion = hooks[1]
        self.sistema.pre_validacion = hooks[0]
        self.registro.registrar(self.contrato("safe_handler", handler=seguro))
        contrato = self.registro.obtener("safe_handler")
        contrato.parametros_esquema = {
            "requeridos": ["texto"], "opcionales": [], "tipos": {"texto": "str"}
        }
        res = self.sistema.procesar(em.SolicitudEjecucion("usuario", "safe_handler", {"texto": "ok"}))
        self.assertTrue(res.exito)
        self.assertEqual(res.datos["eco"], "ok")
        self.assertIn(("pre", "safe_handler"), vistos)
        self.assertIn(("post", "completada"), vistos)

        self.registro.registrar(self.contrato("handler_fallo", handler=fallo))
        contrato = self.registro.obtener("handler_fallo")
        contrato.parametros_esquema = {
            "requeridos": ["texto"], "opcionales": [], "tipos": {"texto": "str"}
        }
        res = self.sistema.procesar(em.SolicitudEjecucion("sistema", "handler_fallo", {"texto": "x"}))
        self.assertFalse(res.exito)
        self.assertEqual(res.estado, em.ESTADO_FALLIDA)
        self.assertEqual(res.error["codigo"], "ERROR_INTERNO_HANDLER")

    def test_resolucion_desde_tarea_y_metadatos(self) -> None:
        contrato = em.ContratoHerramienta(
            nombre="buscar",
            categoria="consulta",
            descripcion="Busqueda controlada",
            parametros_esquema={"requeridos": [], "opcionales": ["texto"], "tipos": {"texto": "str"}},
            handler=None,
            nivel_riesgo="critico",
            requiere_confirmacion=True,
            permisos_requeridos=("usuario.confirmar",),
            cancelable=True,
            asincrona=True,
            timeout_seg=7.0,
            habilitada=True,
        )
        self.registro.registrar(contrato)
        tarea = pm.Tarea("tb1", "Buscar informacion", "Ejecutar consulta buscar", "f1")
        solicitud = self.sistema.resolver_desde_tarea(tarea, id_plan="plan_1")
        self.assertEqual(solicitud.herramienta, "buscar")
        self.assertEqual(solicitud.id_plan, "plan_1")
        self.assertEqual(solicitud.id_tarea, "tb1")
        res = self.sistema.procesar(solicitud)
        self.assertTrue(res.exito)
        self.assertEqual(res.metadatos["nivel_riesgo"], "critico")
        self.assertTrue(res.metadatos["requiere_confirmacion"])
        self.assertEqual(res.metadatos["permisos_requeridos"], ["usuario.confirmar"])
        self.assertTrue(res.metadatos["cancelable"])
        self.assertTrue(res.metadatos["asincrona"])

    def test_solicitud_directa_sin_handler_es_dry_run(self) -> None:
        self.registro.registrar(self.contrato("inventario", handler=None))
        contrato = self.registro.obtener("inventario")
        contrato.parametros_esquema = {"requeridos": ["texto"], "opcionales": [], "tipos": {"texto": "str"}}
        res = self.sistema.procesar(em.SolicitudEjecucion("usuario", "inventario", {"texto": "x"}))
        self.assertTrue(res.exito)
        self.assertEqual(res.datos["modo"], "informativo")
        self.assertTrue(res.datos["simulado"])

    def test_adaptador_acciones_sin_handlers_reales(self) -> None:
        contratos = ejecucion_acciones.inventariar_acciones()
        self.assertGreater(len(contratos), 0)
        for contrato in contratos:
            self.assertIsNone(contrato.handler)
            self.assertFalse(contrato.habilitada)
        self.assertGreater(self.registro.inventariar_acciones(), 0)
        self.assertFalse(self.registro.obtener("abrir_calculadora").habilitada)

    def test_concurrencia_rlock(self) -> None:
        errores = []
        def trabajador(indice):
            try:
                nombre = f"hilo_{indice}"
                contrato = em.ContratoHerramienta(
                    nombre, "consulta", "Prueba concurrente",
                    {"requeridos": [], "opcionales": [], "tipos": {}},
                    handler=lambda params={"indice": indice}: params,
                )
                self.registro.registrar(contrato)
                for _ in range(30):
                    self.assertIsNotNone(self.registro.obtener(nombre))
                    self.assertFalse(self.sistema.procesar(
                        em.SolicitudEjecucion("sistema", "herramienta_fantasma")
                    ).exito)
            except Exception as exc:
                errores.append(exc)

        hilos = [threading.Thread(target=trabajador, args=(i,)) for i in range(8)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=5)
        self.assertEqual(errores, [])
        self.assertEqual(len(self.registro.listar(solo_habilitadas=False)), 8)

    def test_a_dict_serializable(self) -> None:
        solicitud = em.SolicitudEjecucion("usuario", "consulta_estado", {"texto": "x"})
        copia = em.SolicitudEjecucion.de_dict(solicitud.a_dict())
        self.assertEqual(copia.id_solicitud, solicitud.id_solicitud)
        self.assertEqual(copia.parametros, solicitud.parametros)


if __name__ == "__main__":
    unittest.main()
