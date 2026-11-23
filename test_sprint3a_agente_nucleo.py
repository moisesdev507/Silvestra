"""Pruebas del núcleo agéntico: bucle, permisos, observación y traza."""
import threading
import unittest
from types import SimpleNamespace

import agente_bucle as ab
import agente_herramientas as ah
import agente_observacion as ao
import agente_permisos as ap
import agente_traza as at


def _herramienta(nombre="leer_archivo", riesgo="bajo"):
    return ah.Herramienta(
        nombre=nombre,
        descripcion="lee un archivo de texto autorizado" if riesgo == "bajo"
        else "borra archivos del sistema",
        parametros=("texto",),
        riesgo=riesgo,
    )


class TestCatalogo(unittest.TestCase):
    def test_deriva_de_acciones_y_filtra_por_relevancia(self):
        catalogo = ah.catalogo()
        self.assertTrue(any(h.nombre == "buscar_youtube" for h in catalogo))
        relevantes = ah.consultar("quiero buscar videos en youtube", limite=3)
        self.assertTrue(relevantes)
        self.assertIn("buscar_youtube", [h.nombre for h in relevantes])

    def test_riesgo_clasificado(self):
        self.assertEqual(ah.clasificar_riesgo("leer_archivo", "lee un archivo"), "bajo")
        self.assertEqual(ah.clasificar_riesgo("escribir_archivo", "escribe notas"), "medio")
        self.assertEqual(ah.clasificar_riesgo("borrar_archivo", "borra datos"), "alto")


class TestPermisos(unittest.TestCase):
    def test_bajo_y_medio_se_permiten_sin_confirmacion(self):
        compuerta = ap.CompuertaPermisos()
        self.assertTrue(compuerta.evaluar(_herramienta()).permitido)
        media = _herramienta("escribir_archivo", "medio")
        self.assertTrue(compuerta.evaluar(media).permitido)

    def test_alto_bloquea_si_falta_confirmacion(self):
        decision = ap.CompuertaPermisos().evaluar(_herramienta("borrar_archivo", "alto"))
        self.assertFalse(decision.permitido)
        self.assertEqual(decision.motivo, "confirmacion_no_disponible")

    def test_alto_rechazado_y_aprobado(self):
        rechazo = ap.CompuertaPermisos(confirmar=lambda *args: False).evaluar(
            _herramienta("borrar_archivo", "alto"))
        self.assertFalse(rechazo.permitido)
        self.assertEqual(rechazo.motivo, "confirmacion_rechazada")

        aprobado = []
        decision = ap.CompuertaPermisos(
            confirmar=lambda nombre, desc, datos: aprobado.append(nombre) or True
        ).evaluar(_herramienta("borrar_archivo", "alto"), parametros={"password": "x"})
        self.assertTrue(decision.permitido)
        self.assertTrue(decision.confirmado)
        self.assertEqual(aprobado, ["borrar_archivo"])


class TestObservacion(unittest.TestCase):
    def test_formateo_sanitizado(self):
        obs = ao.Observacion(
            exito=False, salida="Bearer sk-abcdefghijklmnop",
            error="clave sk-abcdefghijklmnop rechazada", duracion_ms=12,
            herramienta="buscar", datos={"password": "secreto"},
        )
        texto = obs.formatear()
        self.assertIn("ÉXITO: no", texto)
        self.assertIn("[CLAVE REDACTADA]", texto)
        self.assertNotIn("abcdefghijklmnop", texto)
        self.assertEqual(obs.a_dict()["datos"]["password"], "***")

    def test_desde_resultado_tupla_y_verificador(self):
        vista = []
        verificador = lambda nombre, obs, esperado: vista.append(nombre) or True
        obs = ao.desde_resultado("leer_archivo", (True, "Contenido"), inicio=0,
                                 verificador=verificador)
        self.assertTrue(obs.exito)
        self.assertTrue(obs.verificado)
        self.assertEqual(vista, ["leer_archivo"])
        fallo = ao.desde_resultado("buscar", (False, "falló"), verificador=None)
        self.assertFalse(fallo.verificado)
        self.assertEqual(fallo.error, "falló")

    def test_adaptador_a_motor_de_verificacion(self):
        class MotorFalso:
            def verificar_resultado(self, solicitud, resultado, esperado):
                self.visto = (solicitud.herramienta, resultado.exito)
                return SimpleNamespace(estado_final="verificado")

        motor = MotorFalso()
        obs = ao.Observacion(exito=True, salida="ok", herramienta="leer_archivo")
        self.assertTrue(ao.verificar(motor, "leer_archivo", obs))
        self.assertEqual(motor.visto, ("leer_archivo", True))


class TestTraza(unittest.TestCase):
    def test_cancelacion_y_sanitizacion(self):
        traza = at.Traza()
        self.assertFalse(traza.cancelada)
        traza.registrar(1, intencion="leer", herramienta="leer_archivo",
                        argumentos={"password": "secreto", "texto": "Bearer sk-abcdefghijklmnop"},
                        resultado="ok", verificado=True, duracion_ms=5)
        evento = traza.ultimo()
        self.assertEqual(evento["argumentos"]["password"], "***")
        self.assertNotIn("abcdefghijklmnop", str(evento["argumentos"]))
        traza.cancelar()
        self.assertTrue(traza.cancelada)
        self.assertTrue(traza.evento.is_set())
        self.assertEqual(len(traza.a_lista()), 1)


class TestBucle(unittest.TestCase):
    def test_flujo_multi_paso_exitoso(self):
        # verificado=False mantiene el bucle abierto hasta la decisión final.
        pasos = [
            {"exito": True, "salida": "archivo leído", "verificado": False},
            {"exito": True, "salida": "resumen listo", "verificado": False},
        ]
        ejecuciones = []

        def ejecutar(nombre, argumentos, paso):
            ejecuciones.append((nombre, argumentos))
            return pasos[paso - 1]

        decisiones = [
            {"herramienta": "leer_archivo", "argumentos": {"texto": "notas.txt"},
             "intencion": "leer"},
            {"herramienta": "leer_archivo", "argumentos": {"texto": "resumen.txt"},
             "intencion": "revisar"},
            {"final": True, "respuesta": "Ya tengo el resumen."},
        ]
        bucle = ab.BucleAgente(catalogo=[_herramienta()], ejecutar=ejecutar)
        resultado = bucle.ejecutar("resume mis notas", decidir=lambda *a: decisiones[a[3] - 1])
        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.pasos, 3)
        self.assertEqual(resultado.respuesta, "Ya tengo el resumen.")
        self.assertEqual(len(ejecuciones), 2)
        self.assertEqual(resultado.motivo, "objetivo_resuelto")
        self.assertEqual(len(resultado.traza), 2)

    def test_error_paso_uno_se_corregge_en_paso_dos(self):
        vistos = []

        def decidir(objetivo, observaciones, catalogo, paso):
            if observaciones:
                vistos.append(observaciones[-1].error)
            return {"herramienta": "buscar", "argumentos": {"texto": "consulta"},
                    "intencion": "buscar"}

        respuestas = [(False, "argumento inválido"), (True, "resultado corregido")]
        bucle = ab.BucleAgente(catalogo=[_herramienta("buscar")],
                               ejecutar=lambda n, a, p: respuestas[p - 1])
        resultado = bucle.ejecutar("buscar algo", decidir=decidir)
        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.pasos, 2)
        self.assertIn("argumento inválido", vistos[0])
        self.assertIn("argumento inválido", resultado.traza[0]["error"])

    def test_riesgo_alto_bloquea_y_luego_aprueba(self):
        peligrosa = _herramienta("borrar_archivo", "alto")
        llamadas = []
        bloqueado = ab.BucleAgente(
            catalogo=[peligrosa],
            compuerta=ap.CompuertaPermisos(confirmar=None),
            ejecutar=lambda n, a, p: llamadas.append(n) or (True, "hecho"),
        ).ejecutar("borra todo", decidir=lambda *a: {
            "herramienta": "borrar_archivo", "argumentos": {}})
        self.assertFalse(bloqueado.exito)
        self.assertEqual(bloqueado.motivo, "confirmacion_no_disponible")
        self.assertEqual(llamadas, [])

        aprobado = ab.BucleAgente(
            catalogo=[peligrosa],
            compuerta=ap.CompuertaPermisos(confirmar=lambda *a: True),
            ejecutar=lambda n, a, p: (True, "borrado seguro"),
        ).ejecutar("borra todo", decidir=lambda *a: {
            "herramienta": "borrar_archivo", "argumentos": {}})
        self.assertTrue(aprobado.exito)

    def test_cancelacion_inmediata_y_despues_de_actuar(self):
        traza = at.Traza()
        bucle = ab.BucleAgente(catalogo=[_herramienta()], traza=traza,
                               ejecutar=lambda n, a, p: (True, "hecho"))
        traza.cancelar()
        resultado = bucle.ejecutar("lee algo")
        self.assertTrue(resultado.cancelado)
        self.assertEqual(resultado.motivo, "cancelado")

        traza2 = at.Traza()
        bucle2 = ab.BucleAgente(catalogo=[_herramienta()], traza=traza2,
                                ejecutar=lambda n, a, p: traza2.cancelar() or (True, "hecho"))
        resultado2 = bucle2.ejecutar("lee algo")
        self.assertTrue(resultado2.cancelado)

        externo = threading.Event()
        externo.set()
        bucle3 = ab.BucleAgente(catalogo=[_herramienta()])
        self.assertTrue(bucle3.ejecutar("lee algo", cancelacion=externo).cancelado)

    def test_max_pasos_configurable_y_tope_seguro(self):
        self.assertEqual(ab.BucleAgente(max_pasos=99).max_pasos, ab.MAX_PASOS)
        self.assertEqual(ab.BucleAgente(max_pasos=2).max_pasos, 2)
        decision = lambda *a: {"herramienta": "buscar", "argumentos": {"texto": "x"}}
        bucle = ab.BucleAgente(catalogo=[_herramienta("buscar")], max_pasos=2,
                               ejecutar=lambda n, a, p: (False, "sigue fallando"))
        resultado = bucle.ejecutar("buscar", decidir=decision)
        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.pasos, 2)
        self.assertEqual(resultado.motivo, "max_pasos")

    def test_traza_sanitizada_en_el_bucle(self):
        bucle = ab.BucleAgente(
            catalogo=[_herramienta()],
            ejecutar=lambda n, a, p: (True, "Bearer sk-abcdefghijklmnop"),
        )
        resultado = bucle.ejecutar("lee algo", decidir=lambda *a: {
            "herramienta": "leer_archivo",
            "argumentos": {"password": "secreto", "texto": "Bearer sk-abcdefghijklmnop"},
        })
        self.assertTrue(resultado.exito)
        serializado = str(resultado.traza)
        self.assertNotIn("abcdefghijklmnop", serializado)
        self.assertIn("***", serializado)


if __name__ == "__main__":
    unittest.main()
