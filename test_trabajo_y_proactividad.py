"""Pruebas unitarias para memoria de trabajo corta y motor proactivo situacional."""
import os
import queue
import time
import unittest

import cerebro_proactivo as cp
import cerebro_trabajo as ct


class DummyApp:
    def __init__(self):
        self.modo_privado = False
        self.modo_activo = "normal"
        self.hablando = False
        self.escuchando = False
        self.conversacion = False
        self.flujo = None
        self.cola = queue.Queue()
        self.memoria = type("DummyMemoria", (), {"creador": "Moisés", "nombre": "Lyris"})()


class TestCerebroTrabajo(unittest.TestCase):
    def setUp(self):
        ct.limpiar_memoria_trabajo()
        self.test_archivo = "nota_trabajo_test.txt"
        self.test_ruta = os.path.join("workspace_lyris", self.test_archivo)
        if os.path.exists(self.test_ruta):
            os.remove(self.test_ruta)

    def tearDown(self):
        ct.limpiar_memoria_trabajo()
        if os.path.exists(self.test_ruta):
            os.remove(self.test_ruta)

    def test_actualizaciones_y_limpieza(self):
        ct.actualizar_archivo("workspace_lyris/ideas.txt")
        ct.actualizar_carpeta("workspace_lyris")
        ct.actualizar_ventana({"ejecutable": "Code.exe", "titulo": "Proyecto Silvestra"})
        ct.actualizar_recordatorio("revisar correo", "10:00 a. m.")
        ct.actualizar_habilidad("generar_contrasenas_seguras")

        mem = ct.obtener_memoria_trabajo()
        self.assertEqual(mem["ultimo_archivo"], "workspace_lyris/ideas.txt")
        self.assertEqual(mem["ultima_carpeta"], "workspace_lyris")
        self.assertEqual(mem["ultima_ventana"]["ejecutable"], "Code.exe")
        self.assertEqual(mem["ultimo_recordatorio"]["texto"], "revisar correo")
        self.assertEqual(mem["ultima_habilidad"], "generar_contrasenas_seguras")

        ct.limpiar_memoria_trabajo()
        mem_vacia = ct.obtener_memoria_trabajo()
        self.assertIsNone(mem_vacia["ultimo_archivo"])
        self.assertIsNone(mem_vacia["ultima_habilidad"])

    def test_resolver_referencias_leelo(self):
        ct.actualizar_archivo(self.test_ruta)

        self.assertEqual(ct.resolver_referencias("léelo"), f"lee el archivo {self.test_archivo}")
        self.assertEqual(ct.resolver_referencias("lee el archivo que acabas de crear"), f"lee el archivo {self.test_archivo}")
        self.assertEqual(ct.resolver_referencias("lee el documento"), f"lee el archivo {self.test_archivo}")

    def test_resolver_referencias_agregale(self):
        os.makedirs("workspace_lyris", exist_ok=True)
        with open(self.test_ruta, "w", encoding="utf-8") as f:
            f.write("# Título inicial\n- punto uno")

        ct.actualizar_archivo(self.test_ruta)
        res = ct.resolver_referencias("agrégale punto dos")
        self.assertTrue(res.startswith(f"escribir_archivo {self.test_archivo} |"))
        self.assertIn("punto uno", res)
        self.assertIn("- punto dos", res)

    def test_resolver_referencias_ejecutala(self):
        ct.actualizar_habilidad("generar_hash_sha256")
        self.assertEqual(ct.resolver_referencias("vuelve a ejecutarla"), "ejecuta la habilidad generar_hash_sha256")
        self.assertEqual(ct.resolver_referencias("ejecútala"), "ejecuta la habilidad generar_hash_sha256")

    def test_resumen_contexto_trabajo(self):
        ct.actualizar_archivo("workspace_lyris/tareas.txt")
        ct.actualizar_habilidad("resumen_web")
        res = ct.resumen_contexto_trabajo()
        self.assertIn("[TRABAJO:", res)
        self.assertIn("archivo=tareas.txt", res)
        self.assertIn("habilidad=resumen_web", res)
        self.assertLessEqual(len(res), 140)


class TestCerebroProactivo(unittest.TestCase):
    def setUp(self):
        self.app = DummyApp()
        self.motor = cp.obtener_motor_proactivo()
        self.motor.reiniciar()

    def tearDown(self):
        self.motor.reiniciar()

    def test_guardarail_modo_privado(self):
        self.app.modo_privado = True
        puede, razon = self.motor.puede_intervenir(self.app, forzar_cooldown=True)
        self.assertFalse(puede)
        self.assertEqual(razon, "modo_privado")
        self.assertIsNone(self.motor.evaluar_oportunidad(self.app, forzar_cooldown=True))

    def test_guardarail_turno_activo(self):
        self.app.hablando = True
        puede, razon = self.motor.puede_intervenir(self.app, forzar_cooldown=True)
        self.assertFalse(puede)
        self.assertEqual(razon, "turno_activo")

        self.app.hablando = False
        self.app.escuchando = True
        puede, _ = self.motor.puede_intervenir(self.app, forzar_cooldown=True)
        self.assertFalse(puede)

    def test_guardarail_gracia_inicial_arranque(self):
        self.motor.arranque_ts = time.time()
        puede, razon = self.motor.puede_intervenir(self.app, motivo="ventana")
        self.assertFalse(puede)
        self.assertEqual(razon, "gracia_inicial")

    def test_bloqueo_si_cola_tiene_audio_pendiente(self):
        self.app.cola.put(("hablar", ("Audio previo pendiente", "neutral")))
        puede, razon = self.motor.puede_intervenir(self.app, forzar_cooldown=True)
        self.assertFalse(puede)
        self.assertEqual(razon, "audio_encolado")

    def test_guardarail_cooldown(self):
        self.motor.ultimo_aviso = time.time()
        puede, razon = self.motor.puede_intervenir(self.app, forzar_cooldown=False)
        self.assertFalse(puede)
        self.assertEqual(razon, "cooldown_activo")

    def test_briefing_diario_unico_y_tamano(self):
        res = self.motor.evaluar_briefing_diario(self.app, forzar=True)
        self.assertIsNotNone(res)
        msg, emocion = res
        self.assertEqual(emocion, "alegre")
        palabras = msg.split()
        self.assertLessEqual(len(palabras), 25)
        self.assertIn("Moisés", msg)

        # Segundo llamado sin forzar debe ser None (máx 1 vez al día)
        self.assertIsNone(self.motor.evaluar_briefing_diario(self.app, forzar=False))

    def test_contexto_proyecto_cambio_ventana(self):
        ventana_code = {"ejecutable": "Code.exe", "titulo": "C:\\Proyecto_Silvestra - Visual Studio Code"}
        res = self.motor.evaluar_cambio_ventana(self.app, ventana_code, forzar=True)
        self.assertIsNotNone(res)
        msg, emocion = res
        self.assertEqual(emocion, "atenta")
        self.assertIn("entorno de desarrollo", msg.lower())

        # No repite el mismo proyecto en la misma sesión
        self.assertIsNone(self.motor.evaluar_cambio_ventana(self.app, ventana_code, forzar=False))

    def test_cuidado_nocturno(self):
        res = self.motor.evaluar_cuidado_nocturno(self.app, forzar=True)
        self.assertIsNotNone(res)
        msg, emocion = res
        self.assertEqual(emocion, "calida")
        self.assertIn("descansar", msg.lower())

        # Segundo llamado sin forzar debe ser None
        self.assertIsNone(self.motor.evaluar_cuidado_nocturno(self.app, forzar=False))

    def test_emision_segura_por_cola(self):
        ok, msg = cp.evaluar_proactividad(self.app, motivo="periodico", forzar_cooldown=True)
        self.assertTrue(ok)
        self.assertFalse(self.app.cola.empty())
        tipo, payload = self.app.cola.get()
        self.assertEqual(tipo, "hablar")
        self.assertIsInstance(payload, tuple)
        self.assertEqual(payload[0], msg)


class TestEjecucionLocalArchivos(unittest.TestCase):
    def setUp(self):
        ct.limpiar_memoria_trabajo()
        self.archivo_test = "doc_prueba_rapida.txt"
        self.ruta_test = os.path.join("workspace_lyris", self.archivo_test)
        os.makedirs("workspace_lyris", exist_ok=True)
        with open(self.ruta_test, "w", encoding="utf-8") as f:
            f.write("Punto inicial sobre arquitectura.")
        ct.actualizar_archivo(self.ruta_test)

        self.cerebro = type("DummyCerebro", (), {
            "app": DummyApp(),
            "historial": [],
            "_podar_historial": lambda self: None,
        })()

    def tearDown(self):
        ct.limpiar_memoria_trabajo()
        if os.path.exists(self.ruta_test):
            os.remove(self.ruta_test)

    def test_agregale_y_leelo_local_instantaneo(self):
        from respuesta_flujo import responder_flujo

        frases = []
        def al_frase(txt):
            frases.append(txt)

        # 1. Ejecución local de 'agrégale...' sin invocar LLM
        t_inicio = time.time()
        resp_add, acc_add, emo_add = responder_flujo(self.cerebro, "agrégale punto dos sobre base de datos", al_frase=al_frase)
        duracion_add = time.time() - t_inicio

        self.assertLess(duracion_add, 0.200)
        self.assertIn("guardé los cambios", resp_add.lower())
        self.assertIsNone(acc_add)

        # Verificar que el archivo realmente contiene el texto agregado
        with open(self.ruta_test, "r", encoding="utf-8") as f:
            contenido = f.read()
        self.assertIn("Punto inicial sobre arquitectura.", contenido)
        self.assertIn("punto dos sobre base de datos", contenido)

        # 2. Ejecución local de 'léelo' devolviendo el contenido real
        t_inicio2 = time.time()
        resp_leer, acc_leer, emo_leer = responder_flujo(self.cerebro, "léelo", al_frase=al_frase)
        duracion_leer = time.time() - t_inicio2

        self.assertLess(duracion_leer, 0.200)
        self.assertIn("Punto inicial sobre arquitectura.", resp_leer)
        self.assertIn("punto dos sobre base de datos", resp_leer)
        self.assertIn(self.archivo_test, resp_leer)


if __name__ == "__main__":
    unittest.main()
