"""Pruebas unitarias para recordatorios sin falso bloqueo, habilidades de archivos y aprendiz de habilidades."""
import os
import unittest

import acciones
import aprendiz_habilidades
import habilidades_archivos
import memoria_formacion
import recordatorios
from respuesta_flujo import responder_flujo


class DummyCerebro:
    def __init__(self):
        self.app = None
        self.historial = []


class TestRecordatoriosSinFalsoBloqueo(unittest.TestCase):
    def test_deteccion_recordatorio_temporal(self):
        t1 = "Recuerdame tomar agua en un minuto por favor"
        t2 = "Recuerda me tomar agua en un minuto"
        t3 = "Avisame en 10 minutos de la reunión"
        self.assertTrue(recordatorios.es_recordatorio_temporal(t1))
        self.assertTrue(recordatorios.es_recordatorio_temporal(t2))
        self.assertTrue(recordatorios.es_recordatorio_temporal(t3))

    def test_memoria_no_captura_recordatorio_temporal(self):
        d1 = memoria_formacion.detectar_directiva("Recuerdame tomar agua en un minuto por favor")
        d2 = memoria_formacion.detectar_directiva("Recuerda me tomar agua en un minuto")
        self.assertEqual(d1.get("accion"), "ninguna")
        self.assertEqual(d2.get("accion"), "ninguna")

    def test_parsear_tiempo_con_palabras(self):
        ts, hora_str, texto = recordatorios.parsear_tiempo("Recuerdame tomar agua en un minuto por favor")
        self.assertIsNotNone(ts)
        self.assertIn("tomar agua", texto)
        self.assertTrue("a. m." in hora_str or "p. m." in hora_str)

    def test_flujo_respuesta_recordatorio_inmediato(self):
        cerebro = DummyCerebro()
        msg, accion, emocion = responder_flujo(cerebro, "Recuerdame tomar agua en un minuto por favor", None)
        self.assertEqual(accion, "poner_recordatorio")
        self.assertNotIn("No puedo guardar ese dato de forma segura", msg)
        self.assertIn("tomar agua", msg.lower())


class TestHabilidadesArchivos(unittest.TestCase):
    def setUp(self):
        self.test_file = "archivo_prueba_unit.txt"
        self.test_path = os.path.join(habilidades_archivos.DIR_WORKSPACE, self.test_file)
        if os.path.exists(self.test_path):
            os.remove(self.test_path)

    def tearDown(self):
        if os.path.exists(self.test_path):
            os.remove(self.test_path)

    def test_escritura_y_lectura_segura(self):
        ok, msg = habilidades_archivos.escribir_archivo(f"{self.test_file} | Contenido de prueba unitaria")
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(self.test_path))

        ok_l, contenido = habilidades_archivos.leer_archivo(self.test_file)
        self.assertTrue(ok_l)
        self.assertIn("Contenido de prueba unitaria", contenido)

    def test_listar_archivos_workspace(self):
        habilidades_archivos.escribir_archivo(f"{self.test_file} | Datos")
        ok, listado = habilidades_archivos.listar_archivos()
        self.assertTrue(ok)
        self.assertIn(self.test_file, listado)

    def test_bloqueo_extensiones_peligrosas(self):
        ok, msg = habilidades_archivos.escribir_archivo("script_peligroso.exe | binario")
        self.assertFalse(ok)
        self.assertIn("prohibida", msg.lower())

    def test_bloqueo_path_traversal_al_nucleo(self):
        ok, msg = habilidades_archivos.escribir_archivo("../config.py | hack")
        self.assertFalse(ok)
        self.assertIn("denegado", msg.lower())


class TestAprendizHabilidades(unittest.TestCase):
    def test_auditoria_ast_segura(self):
        codigo_valido = '"""Modulo seguro."""\ndef ejecutar(arg=None, app=None):\n    return f"Hola {arg}"\n'
        ok, motivo = aprendiz_habilidades.auditar_codigo(codigo_valido)
        self.assertTrue(ok)

    def test_auditoria_ast_rechaza_peligros(self):
        # 1. Sin función ejecutar
        ok, _ = aprendiz_habilidades.auditar_codigo("x = 10")
        self.assertFalse(ok)

        # 2. Con subprocess
        ok, m = aprendiz_habilidades.auditar_codigo("import subprocess\ndef ejecutar(arg=None, app=None):\n    pass")
        self.assertFalse(ok)
        self.assertIn("prohibida", m.lower())

        # 3. Con eval / exec
        ok, m = aprendiz_habilidades.auditar_codigo("def ejecutar(arg=None, app=None):\n    eval('2+2')")
        self.assertFalse(ok)
        self.assertIn("prohibida", m.lower())

        # 4. Con os.system
        ok, m = aprendiz_habilidades.auditar_codigo("import os\ndef ejecutar(arg=None, app=None):\n    os.system('dir')")
        self.assertFalse(ok)
        self.assertIn("restringido", m.lower())

    def test_ciclo_aprender_y_confirmar_habilidad(self):
        nom = "calculadora_suma_test"
        ok_p, msg_p = aprendiz_habilidades.aprender_habilidad(f"{nom} | Suma numeros")
        self.assertTrue(ok_p)
        self.assertIn("He preparado la nueva habilidad", msg_p)

        ok_c, msg_c = aprendiz_habilidades.confirmar_habilidad(nom)
        self.assertTrue(ok_c)
        self.assertIn("aprobada", msg_c.lower())

        # Probar ejecución a través de acciones
        ok_e, res_e = acciones.ejecutar(nom, "arg_prueba")
        self.assertTrue(ok_e)
        self.assertIn("arg_prueba", res_e)


if __name__ == "__main__":
    unittest.main()
