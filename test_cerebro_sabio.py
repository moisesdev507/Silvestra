"""Pruebas unitarias para la arquitectura de cerebro sabio y auto-entrenable."""
import os
import unittest

import acciones
import aprendiz_habilidades
import cerebro_entrenamiento as ce
import cerebro_grafo as cg
import cerebro_parser as cp
import cerebro_planificador as cplan
from respuesta_flujo import responder_flujo


class DummyMemoria:
    def __init__(self):
        self.creador = "Moisés"
        self.nombre = "Lyris"
        self.proposito = "Asistente inteligente"
        self.hechos = ["Moisés es creador de Silvestra"]


class DummyCerebro:
    def __init__(self):
        self.app = None
        self.memoria = DummyMemoria()
        self.historial = []


class TestCerebroGrafo(unittest.TestCase):
    def test_registro_y_sobreescritura_de_hechos(self):
        # 1. Registrar hecho inicial
        ok1 = cg.registrar_hecho("Moisés", "trabaja_en", "Proyecto Silvestra")
        self.assertTrue(ok1)

        # 2. Registrar hecho que luego se actualiza
        cg.registrar_hecho("Moisés", "estudia", "Derecho")
        cg.registrar_hecho("Moisés", "estudia", "Ingeniería de Software")

        rel = cg.consultar_relaciones("Moisés", limite=10)
        self.assertTrue(any(r["relacion"] == "estudia" and r["objeto"] == "Ingeniería de Software" for r in rel))
        # Verificar que la relación previa quedó inactiva
        self.assertFalse(any(r["relacion"] == "estudia" and r["objeto"] == "Derecho" for r in rel))

    def test_consultar_contexto_grafo(self):
        cg.registrar_hecho("Moisés", "lenguaje_favorito", "Python 3")
        ctx = cg.consultar_contexto_grafo("¿Cuál es el lenguaje favorito de Moisés?")
        self.assertIn("CONOCIMIENTO VIVO DEL GRAFO", ctx)
        self.assertIn("lenguaje_favorito", ctx)
        self.assertIn("Python 3", ctx)

    def test_extractor_conversacional(self):
        n = cg.extraer_y_guardar_hechos("Me gusta mucho la inteligencia artificial modular", creador="Moisés")
        self.assertGreaterEqual(n, 1)
        rel = cg.consultar_relaciones("Moisés")
        self.assertTrue(any(r["relacion"] == "le_gusta" for r in rel))


class TestCerebroPlanificador(unittest.TestCase):
    def setUp(self):
        self.test_archivo = "ideas_planificador_test.txt"
        self.path_archivo = os.path.join("workspace_lyris", self.test_archivo)
        if os.path.exists(self.path_archivo):
            os.remove(self.path_archivo)

    def tearDown(self):
        if os.path.exists(self.path_archivo):
            os.remove(self.path_archivo)

    def test_deteccion_y_descomposicion_multipaso(self):
        texto = f"Crea el archivo {self.test_archivo} con ideas de diseño y luego recuerda revisar el correo en 20 minutos"
        self.assertTrue(cplan.detectar_intencion_multipaso(texto))
        pasos = cplan.descomponer_en_pasos(texto)
        self.assertGreaterEqual(len(pasos), 2)
        self.assertEqual(pasos[0][0], "escribir_archivo")

    def test_ejecucion_y_autocritica_multipaso(self):
        # Paso 1 real (escribir archivo) + Paso 2 inexistente para probar auto-crítica
        pasos = [
            ("escribir_archivo", f"{self.test_archivo} | Contenido generado por planificador"),
            ("accion_totalmente_falsa_xyz", "argumento"),
        ]
        resultados = cplan.ejecutar_plan_multipaso(pasos)
        self.assertEqual(len(resultados), 2)
        self.assertTrue(resultados[0][1])  # Paso 1 exitoso
        self.assertFalse(resultados[1][1])  # Paso 2 falló limpiamente

        sintesis = cplan.verificar_coherencia_y_sintetizar(pasos, resultados)
        self.assertIn("Pude completar 1 de 2 pasos", sintesis)
        self.assertIn("accion_totalmente_falsa_xyz", sintesis)

    def test_orden_compuesta_whisper_y_respuesta_flujo(self):
        orden = "Llea un archivo llamado TareasGioHoi.tgit con tres pendientes de programación y recuérdame revisarlo en cinco minutos"
        self.assertTrue(cplan.detectar_intencion_multipaso(orden))

        target_path = os.path.join("workspace_lyris", "tareasgiohoi.txt")
        if os.path.exists(target_path):
            os.remove(target_path)

        try:
            cerebro = DummyCerebro()
            msg, accion, emocion = responder_flujo(cerebro, orden, al_frase=None)

            # 1. No debe disparar accion para evitar re-ejecucion doble en eventos.py
            self.assertIsNone(accion)
            # 2. Mensaje unificado de confirmacion
            self.assertIn("guardé 'tareasgiohoi.txt'", msg)
            self.assertIn("programé tu recordatorio", msg)
            # 3. Archivo creado en workspace_lyris con contenido real
            self.assertTrue(os.path.exists(target_path))
            with open(target_path, "r", encoding="utf-8") as f:
                contenido = f.read()
            self.assertGreater(len(contenido.strip()), 10)
            self.assertIn("pendientes de programación", contenido.lower())
        finally:
            if os.path.exists(target_path):
                os.remove(target_path)


class TestCerebroEntrenamiento(unittest.TestCase):
    def test_coincidencia_difusa_whisper(self):
        # Normalización fonética
        self.assertEqual(ce.normalizar_fonetico("Dame una Cotrasena"), "dame una contrasena")
        self.assertEqual(ce.normalizar_fonetico("Genera contrasiña"), "genera contrasena")

    def test_flujo_autoaprendizaje_proactivo(self):
        slug = "el_hash_sha256_de_un_texto"
        p = os.path.join("habilidades_aprendidas", f"habilidad_{slug}.py")

        def _limpiar():
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
            reg = aprendiz_habilidades._cargar_registro()
            if slug in reg.get("habilidades", {}):
                del reg["habilidades"][slug]
                aprendiz_habilidades._guardar_registro(reg)
            if slug in acciones.VIVAS:
                del acciones.VIVAS[slug]

        _limpiar()
        try:
            # 1. Petición de capacidad técnica no existente
            ok_prop, msg_prop = ce.gestionar_autoaprendizaje_proactivo("Calcula el hash sha256 de un texto")
            self.assertTrue(ok_prop)
            self.assertIn("Aún no tengo una acción", msg_prop)
            self.assertIn("¿quieres que la programe", msg_prop)

            # 2. Confirmación afirmativa del dueño
            ok_conf, msg_conf = ce.gestionar_autoaprendizaje_proactivo("Sí, hazlo por favor")
            self.assertTrue(ok_conf)
            self.assertIn("activado", msg_conf.lower())
        finally:
            _limpiar()

    def test_unicode_no_trunca_palabras_con_enie(self):
        pet = "genera una contraseña segura de 16 caracteres"
        candidato = ce.detectar_peticion_tecnica_nueva(pet)
        self.assertIsNotNone(candidato)
        self.assertIn("contraseña", candidato)
        self.assertNotIn("contrase ", candidato + " ")

    def test_propuesta_proactiva_confirmar_y_activar_inmediato(self):
        slug = "una_contrasena_personalizada_test"
        nom_hab = f"habilidad_{slug}.py"
        ruta_hab = os.path.join("habilidades_aprendidas", nom_hab)

        def _limpiar():
            if os.path.exists(ruta_hab):
                try:
                    os.remove(ruta_hab)
                except Exception:
                    pass
            reg = aprendiz_habilidades._cargar_registro()
            if slug in reg.get("habilidades", {}):
                del reg["habilidades"][slug]
                aprendiz_habilidades._guardar_registro(reg)
            if slug in acciones.VIVAS:
                del acciones.VIVAS[slug]

        _limpiar()
        try:
            # 1. Propuesta
            ok_prop, msg_prop = ce.gestionar_autoaprendizaje_proactivo(f"genera {slug.replace('_', ' ')}")
            self.assertTrue(ok_prop)
            self.assertIn("Aún no tengo una acción", msg_prop)

            # 2. Confirmación inmediata con activación en un solo paso
            ok_conf, msg_conf = ce.gestionar_autoaprendizaje_proactivo("Sí, hazlo por favor")
            self.assertTrue(ok_conf)
            self.assertIn("activado", msg_conf.lower())
            self.assertIn(slug, acciones.VIVAS)

            # 3. Búsqueda y ejecución directa con variantes fonéticas
            nom_match, _ = ce.buscar_habilidad_difusa(f"dame {slug.replace('_', ' ')}")
            self.assertEqual(nom_match, slug)
        finally:
            _limpiar()

    def test_deteccion_leccion_o_correccion(self):
        ok, msg = ce.detectar_y_guardar_leccion("No, mejor hazlo de forma más breve y sin rodeos", creador="Moisés")
        self.assertTrue(ok)
        self.assertIn("He guardado esa regla", msg)
        rel = cg.consultar_relaciones("Moisés")
        self.assertTrue(any(r["relacion"] == "regla_estilo" for r in rel))


class TestVozSinCortes(unittest.TestCase):
    def test_no_corta_en_contrasena_ni_codigo(self):
        # 1. Contraseña con ! y caracteres especiales
        t1 = "Aquí tienes una contraseña segura: V9k!x8# y guárdala en un lugar seguro."
        frases1, _ = cp._cortar(t1, 0, final=True)
        self.assertEqual(len(frases1), 1)

        # 2. Código o nombre de archivo con .py o .txt
        t2 = "Revisa el archivo script.py para comprobar que los datos.json cargaron bien."
        frases2, _ = cp._cortar(t2, 0, final=True)
        self.assertEqual(len(frases2), 1)

        # 3. Múltiples oraciones reales sí se cortan normalmente
        t3 = "Primera oración terminada. Segunda oración concluida."
        frases3, _ = cp._cortar(t3, 0, final=True)
        self.assertEqual(len(frases3), 2)


if __name__ == "__main__":
    unittest.main()
