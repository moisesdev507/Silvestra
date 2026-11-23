"""Pruebas del Sprint 1B: carril Pro, memoria única, prompt, RAG, PII y splits."""
import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import cerebro_dificultad as cd
import cerebro_prompt
import cerebro_rag
import memoria_filtro
from memoria_almacen import AlmacenMemoriaCognitiva

LIMITE_BYTES = 15_360


class TestBloque0CarrilPro(unittest.TestCase):
    CASOS_REALES = (
        "Explicame paso a paso como disenar un sistema de autenticacion segura con refresh tokens y que errores evitar",
        "Explicame paso a paso cómo diseñar un sistema de autenticación segura con refresh tokens y qué errores evitar",
    )

    def test_casos_reales_con_y_sin_tildes_van_a_pro(self):
        for texto in self.CASOS_REALES:
            with self.subTest(texto=texto[:40]):
                self.assertEqual(
                    cd.decidir_carril(texto, pro_disponible=True),
                    ("pro", "consulta_compleja_tecnica"),
                )

    def test_analisis_corto_tambien_va_a_pro(self):
        for texto in (
            "Analiza la arquitectura de mi proyecto en Python y compara pros y contras",
            "analiza la arquitectura de mi proyecto en Python y compara pros y contras",
            "¿cuáles son los pros y contras de usar SQL?",
            "ayúdame a depurar este traceback",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(cd.decidir_carril(texto, pro_disponible=True)[0], "pro")

    def test_regresiones_cotidiano_siguen_rapido(self):
        for texto in (
            "hola", "¿qué hora es?", "abre chrome",
            "recuérdame en 5 minutos sacar la comida", "cómo está el clima",
            "hola, ¿qué tal tu día?",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(
                    cd.decidir_carril(texto, pro_disponible=True),
                    ("rapido", "cotidiano_o_comando"),
                )

    def test_normalizar_quita_tildes(self):
        self.assertEqual(cd.normalizar_texto("ANÁLISIS DISEÑÓ"), "analisis diseno")


class TestBloque1MemoriaUnica(unittest.TestCase):
    def test_no_recupera_dos_veces_si_ya_hay_paquete(self):
        llamadas = []

        class Memoria:
            hechos = []
            datos = {}
            nombre = "Lyris"
            creador = "Moisés"
            proposito = "asistente"

            def recuperar(self, *args, **kwargs):
                llamadas.append(1)
                raise AssertionError("No debe recuperar memoria dos veces por turno")

        paquete = {"resultados": [], "contradicciones": [], "relaciones": []}
        texto, n = cerebro_prompt.recuerdos_relevantes(
            Memoria(), "tema", paquete=paquete
        )
        self.assertEqual(llamadas, [])
        self.assertEqual(n, 0)
        self.assertIsInstance(texto, str)

    def test_sin_paquete_si_recupera_una_vez(self):
        class Memoria:
            hechos = []
            datos = {}

            def recuperar(self, *args, **kwargs):
                return {"resultados": [], "contradicciones": [], "relaciones": []}

        memoria = Memoria()
        with patch.object(memoria, "recuperar", wraps=memoria.recuperar) as espia:
            cerebro_prompt.recuerdos_relevantes(memoria, "tema")
        self.assertEqual(espia.call_count, 1)


class TestBloque2PromptRecortado(unittest.TestCase):
    def test_prompt_conserva_estilo_y_tokens_reales(self):
        memoria = SimpleNamespace(
            hechos=[], datos={"resumenes_tematicos": {}},
            nombre="Lyris", creador="Moisés", proposito="asistente personal",
        )
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            prompt = cerebro_prompt.construir_prompt(memoria, texto_actual="hola")
        for clave in (
            "1 a 2 frases", "PROHIBIDO terminar con preguntas de relleno",
            "español panameño", "ÚNICAMENTE",
        ):
            self.assertIn(clave, prompt, clave)
        coincidencia = re.search(r"prompt_tokens=(\d+)", salida.getvalue())
        self.assertIsNotNone(coincidencia)
        self.assertEqual(int(coincidencia.group(1)), max(1, int(len(prompt) / 3.6)))

    def test_sin_metricas_inventadas_en_codigo(self):
        with open("cerebro_prompt.py", encoding="utf-8") as f:
            fuente = f.read()
        for inventado in ("tokens_base", "anterior=", "ahorro="):
            self.assertNotIn(inventado, fuente)


class TestBloque3CacheDDL(unittest.TestCase):
    def test_ddl_solo_una_vez_por_ruta_y_forzar_lo_repite(self):
        ejecutados = []

        class Conexion:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql):
                ejecutados.append(sql)
                return self

            def commit(self):
                pass

        ruta_original = cerebro_rag.RUTA_DB
        try:
            with tempfile.TemporaryDirectory() as temporal:
                ruta_uno = os.path.join(temporal, "uno.db")
                ruta_dos = os.path.join(temporal, "dos.db")
                cerebro_rag.invalidar_cache_rag()
                with patch.object(cerebro_rag, "_obtener_conexion", return_value=Conexion()):
                    cerebro_rag.RUTA_DB = ruta_uno
                    cerebro_rag.inicializar_rag()
                    primero = len(ejecutados)
                    self.assertGreater(primero, 0)

                    cerebro_rag.inicializar_rag()
                    self.assertEqual(len(ejecutados), primero)

                    cerebro_rag.inicializar_rag(forzar=True)
                    self.assertGreater(len(ejecutados), primero)

                    cerebro_rag.RUTA_DB = ruta_dos
                    tras_cambio = len(ejecutados)
                    cerebro_rag.inicializar_rag()
                    self.assertGreater(len(ejecutados), tras_cambio)
        finally:
            cerebro_rag.RUTA_DB = ruta_original
            cerebro_rag.invalidar_cache_rag()


class TestBloque4PiiYDedup(unittest.TestCase):
    def test_detecta_mencion_de_secreto_y_no_confunde_tareas(self):
        self.assertTrue(memoria_filtro.contiene_pii("Enela 1 cuenta con la contraseña generada."))
        self.assertFalse(memoria_filtro.es_recuerdo_valido(
            "Enela 1 cuenta con la contraseña generada.")[0])
        for sano in ("Cambiar contraseña mañana", "La autenticación puede usar JWT"):
            with self.subTest(sano=sano):
                self.assertFalse(memoria_filtro.contiene_pii(sano))
                self.assertTrue(memoria_filtro.es_recuerdo_valido(sano)[0])

    def test_dedup_proporcional_no_descarta_frases_largas(self):
        self.assertFalse(memoria_filtro.es_duplicado(
            "Me gusta programar en Python por las tardes con café",
            ["Me gusta programar en Python por las mañanas con té y pan integral"],
        ))

    def test_depurar_pii_con_bd_temporal(self):
        with tempfile.TemporaryDirectory() as temporal:
            almacen = AlmacenMemoriaCognitiva(os.path.join(temporal, "mem.db"), "ana")
            try:
                almacen.guardar_recuerdo("Enela 1 cuenta con la contraseña generada.", usuario_id="ana")
                almacen.guardar_recuerdo("A Moisés le gusta el café panameño.", usuario_id="ana")
                inspeccion = memoria_filtro.depurar_recuerdos_pii(almacen, "ana", aplicar=False)
                self.assertEqual(inspeccion["sospechosos"], 1)
                self.assertEqual(inspeccion["eliminados"], 0)
                aplicado = memoria_filtro.depurar_recuerdos_pii(almacen, "ana", aplicar=True)
                self.assertEqual(aplicado["eliminados"], 1)
                self.assertEqual(len(memoria_filtro.recuerdos_con_pii(almacen, "ana")), 0)
            finally:
                almacen.cerrar()


class TestBloque5Splits(unittest.TestCase):
    def test_fachadas_y_mixin_disponibles(self):
        import eventos
        import eventos_dialogo
        import aprendizaje
        import aprendizaje_io

        self.assertTrue(callable(eventos.atender_evento))
        self.assertTrue(callable(eventos.es_confirmacion_rutinaria))
        self.assertTrue(callable(eventos_dialogo.atender_resto))
        self.assertTrue(callable(aprendizaje.instalar))
        self.assertTrue(issubclass(aprendizaje.GestorAprendizaje,
                                   aprendizaje_io.AccionesPerfilMixin))
        for nombre in ("accion_que_has_aprendido", "accion_olvidar_aprendizaje",
                       "accion_borrar_perfil"):
            self.assertTrue(callable(getattr(aprendizaje.GestorAprendizaje, nombre)))

    def test_cadena_qt_permanece_en_eventos(self):
        with open("eventos.py", encoding="utf-8") as f:
            self.assertIn("puede_actualizar_ui()", f.read())

    def test_todos_los_py_modificados_respetan_limite(self):
        archivos = (
            "cerebro_dificultad.py", "cerebro.py", "cerebro_prompt.py",
            "cerebro_rag.py", "memoria_filtro.py", "eventos.py",
            "eventos_dialogo.py", "aprendizaje.py", "aprendizaje_io.py",
        )
        for nombre in archivos:
            with self.subTest(archivo=nombre):
                self.assertLessEqual(os.path.getsize(nombre), LIMITE_BYTES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
