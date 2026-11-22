"""Pruebas unitarias para recordatorios sin falso bloqueo, habilidades de archivos y aprendiz de habilidades."""
import json
import os
import unittest

import acciones
import aprendiz_habilidades
import calidad_respuesta
import habilidades_archivos
import memoria_formacion
import recordatorios
from respuesta_flujo import responder_flujo


class DummyCerebro:
    def __init__(self):
        self.app = None
        self.memoria = None
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
        self.assertIsNone(accion)
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

    def test_rechazo_solo_nombre_sin_contenido(self):
        ok, msg = habilidades_archivos.escribir_archivo("ideas-web.txt")
        self.assertFalse(ok)
        self.assertIn("Faltó el texto a escribir", msg)

    def test_escritura_formatos_json_y_multilinea(self):
        # JSON
        dato_json = json.dumps({"ruta": self.test_file, "contenido": "Texto via JSON"})
        ok, msg = habilidades_archivos.escribir_archivo(dato_json)
        self.assertTrue(ok)
        _, c1 = habilidades_archivos.leer_archivo(self.test_file)
        self.assertIn("Texto via JSON", c1)

        # Multilínea
        dato_multi = f"{self.test_file}\nLinea uno de ideas\nLinea dos de ideas"
        ok2, msg2 = habilidades_archivos.escribir_archivo(dato_multi)
        self.assertTrue(ok2)
        _, c2 = habilidades_archivos.leer_archivo(self.test_file)
        self.assertIn("Linea uno de ideas", c2)

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


class TestFiltroCalidadContrasenas(unittest.TestCase):
    def test_no_falso_positivo_token_corrupto_en_contrasena(self):
        f1 = "Aquí tienes una contraseña segura de 16 caracteres: V9k!"
        valido, motivo = calidad_respuesta.analizar_calidad_texto(f1)
        self.assertTrue(valido, f"Frase válida rechazada: {motivo}")

    def test_token_alfanumerico_no_es_corrupto(self):
        self.assertFalse(calidad_respuesta.es_token_corrupto("V9k"))
        self.assertFalse(calidad_respuesta.es_token_corrupto("p4ssw0rd"))
        self.assertFalse(calidad_respuesta.es_token_corrupto("token123"))


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

    def test_flujo_voz_aprender_aprobar_y_ejecutar_con_errata_whisper(self):
        reg_bak = aprendiz_habilidades._cargar_registro()
        vivas_bak = dict(acciones.VIVAS)
        aprendiz_habilidades._guardar_registro({"habilidades": {}, "pendientes": {}})
        acciones.VIVAS.clear()

        def _limpiar():
            ruta_hab = os.path.join(aprendiz_habilidades.DIR_HABILIDADES, "habilidad_generar_contrasenas_seguras.py")
            if os.path.exists(ruta_hab):
                try:
                    os.remove(ruta_hab)
                except Exception:
                    pass
            reg = aprendiz_habilidades._cargar_registro()
            if "generar_contrasenas_seguras" in reg.get("habilidades", {}):
                del reg["habilidades"]["generar_contrasenas_seguras"]
                aprendiz_habilidades._guardar_registro(reg)
            if "generar_contrasenas_seguras" in acciones.VIVAS:
                del acciones.VIVAS["generar_contrasenas_seguras"]

        _limpiar()
        try:
            cerebro = DummyCerebro()

            # 1. Aprender habilidad
            texto_aprender = "Aprende a generar contraseñas seguras"
            msg_a, acc_a, emo_a = responder_flujo(cerebro, texto_aprender, None)
            self.assertEqual(acc_a, "aprender_habilidad")
            self.assertIn("He preparado la nueva habilidad", msg_a)

            # 2. Confirmar habilidad
            texto_conf = "Aprueba la habilidad de generar contraseñas"
            msg_c, acc_c, emo_c = responder_flujo(cerebro, texto_conf, None)
            self.assertEqual(acc_c, "confirmar_habilidad")
            self.assertIn("aprobada con éxito", msg_c)

            # 3. Ejecutar con errata común de Whisper ("contrasiña")
            texto_ejec = "Genera una contrasiña"
            msg_e, acc_e, emo_e = responder_flujo(cerebro, texto_ejec, None)
            self.assertIn("generar_contrasenas", acc_e)
            self.assertIn("ejecutada", msg_e)
        finally:
            _limpiar()
            aprendiz_habilidades._guardar_registro(reg_bak)
            acciones.VIVAS.clear()
            acciones.VIVAS.update(vivas_bak)


if __name__ == "__main__":
    unittest.main()
