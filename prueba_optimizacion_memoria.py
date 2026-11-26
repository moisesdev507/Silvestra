"""Verificación de las optimizaciones de memoria, prompt Live y almacenamiento."""
import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro_unico
import ciclo_sueno_kaya
import estado_emocional_kaya
import live_audio
import live_turno
import memoria
import memoria_consolidacion
import memoria_consolidacion_validacion
import memoria_contexto
import memoria_semantica
import memoria_sueno

RAIZ = os.path.dirname(os.path.abspath(__file__))
DB_CANONICA = os.path.join(RAIZ, "silvestra_memoria.db")


class PruebaOptimizacionMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.memoria_anterior = memoria._memoria_instancia
        self.mem = memoria.Memoria(
            ruta_db=os.path.join(self.tmp.name, "memoria.db"),
            ruta_json=os.path.join(self.tmp.name, "memoria.json"),
        )

    def tearDown(self):
        memoria._memoria_instancia = self.memoria_anterior
        self.tmp.cleanup()

    def test_a_hechos_reales_sin_preguntas_de_kaya(self):
        filas = [
            {"id": 1, "estado": "activo", "origen": "migrado", "confianza": 0.8,
             "contenido": "reconocer gestos e integrar IoT en la interfaz"},
            {"id": 2, "estado": "activo", "origen": "explicito", "confianza": 1.0,
             "contenido": "A Ana le gusta la comida italiana"},
            {"id": 3, "estado": "activo", "origen": "migrado", "confianza": 0.8,
             "contenido": "¿Qué otras funciones te interesan?"},
            {"id": 4, "estado": "activo", "origen": "migrado", "confianza": 0.8,
             "contenido": "cómo va tu avance con la programación esta semana"},
            {"id": 5, "estado": "activo", "origen": "inferido", "confianza": 1.0,
             "contenido": "A Ana le encanta el café de la esquina"},
            {"id": 6, "estado": "obsoleto", "origen": "explicito", "confianza": 1.0,
             "contenido": "Dato viejo que ya no aplica"},
        ]
        mem = SimpleNamespace(
            usuario_id="local",
            almacen=SimpleNamespace(listar_recuerdos=lambda *a, **k: filas),
        )
        obtenidos = memoria_contexto.hechos_verificados(mem, limite=10)
        self.assertTrue(any("reconocer gestos" in h for h in obtenidos))
        self.assertTrue(any("comida italiana" in h for h in obtenidos))
        self.assertFalse(any("funciones te interesan" in h for h in obtenidos))
        self.assertFalse(any("avance con la programación" in h for h in obtenidos))
        self.assertFalse(any("café de la esquina" in h for h in obtenidos))
        self.assertTrue(memoria_contexto.es_pregunta_kaya("¿Qué haces?"))
        self.assertTrue(memoria_contexto.es_pregunta_kaya("cómo te fue con la sesión"))
        self.assertFalse(memoria_contexto.es_pregunta_kaya("reconocer gestos e integrar IoT"))

    def test_b_db_canonica_acepta_estado_consolidado(self):
        self.assertTrue(os.path.exists(DB_CANONICA))
        con = sqlite3.connect(DB_CANONICA, timeout=5.0)
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='recuerdos'"
        ).fetchone()[0]
        self.assertIn("'consolidado'", ddl)
        self.assertGreaterEqual(con.execute(
            "SELECT COUNT(*) FROM recuerdos WHERE origen='migrado' AND estado='obsoleto'"
        ).fetchone()[0], 59)
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM recuerdos WHERE estado='activo' AND contenido LIKE '%?'"
        ).fetchone()[0], 0)
        con.execute("SAVEPOINT optimizacion")
        con.execute(
            "INSERT INTO recuerdos(tipo_memoria,contenido,contenido_norm,origen,"
            "confianza,estado,creado_en,actualizado_en) "
            "VALUES('semantica','consolidado temporal de prueba','consolidado temporal de prueba',"
            "'sistema',1.0,'consolidado','2026-11-26','2026-11-26')"
        )
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM recuerdos WHERE estado='consolidado' "
            "AND contenido='consolidado temporal de prueba'"
        ).fetchone()[0], 1)
        con.execute("ROLLBACK TO optimizacion")
        con.execute("RELEASE optimizacion")
        con.close()

    def test_c_resumen_para_prompt_no_escribe_estado(self):
        with patch.object(memoria_contexto.estado, "guardar") as guardar:
            primero = memoria_contexto.resumen_para_prompt(self.mem)
            segundo = memoria_contexto.resumen_para_prompt(self.mem)
        guardar.assert_not_called()
        self.assertIn("[Lo que ya sé de ti", primero)
        self.assertTrue(segundo)

    def test_d_config_live_sin_duplicados_y_mas_corta(self):
        bloque = (
            "[Ficha y recuerdos del usuario]\n"
            + ("Ana estudia Ingeniería Industrial en Panamá y le gusta la comida italiana. " * 8)
            + "\n\n[Conversación reciente en curso]\nUsuario: Hablemos de Supabase"
        )
        with patch.object(cerebro_unico, "compilar_contexto_unico", return_value=bloque), \
             patch.object(live_turno.live_herramientas,
                          "declarar_declaraciones_herramientas", return_value=[]):
            cfg = live_turno.construir_config("Kaya", False, False, "Ana")
            texto = cfg.system_instruction.parts[0].text
        self.assertEqual(texto.count("[Ficha y recuerdos del usuario]"), 1)
        self.assertEqual(texto.count("[Conversación reciente en curso]"), 1)
        self.assertEqual(texto.count("Fecha y hora local actual del usuario"), 1)
        self.assertNotIn("[Fecha y hora actual]", texto)

        # Con el bloque cognitivo real: una sola compilación frente a la vieja base + bloque.
        with patch.object(live_turno.live_herramientas,
                          "declarar_declaraciones_herramientas", return_value=[]):
            real = live_turno.construir_config("Kaya", False, False, "Ana")
            texto_real = real.system_instruction.parts[0].text
            base_antigua = live_audio.construir_instruccion_sistema(nombre_usuario="Ana")
            bloque_antiguo = live_turno.bloque_memoria()
        self.assertLess(len(texto_real), len(base_antigua) + len(bloque_antiguo))

    def test_e_una_sola_db_canonica_activa(self):
        esperado = os.path.normcase(os.path.abspath(DB_CANONICA))
        for modulo in (ciclo_sueno_kaya, estado_emocional_kaya, memoria_semantica):
            self.assertEqual(os.path.normcase(os.path.abspath(modulo.RUTA_DB)), esperado)
        self.assertFalse(os.path.exists(os.path.join(RAIZ, "datos", "silvestra_memoria.db")))
        con = sqlite3.connect(DB_CANONICA)
        tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        self.assertTrue({"kaya_estado_emocional", "kaya_sueno", "kaya_seguimientos",
                         "kaya_embeddings"} <= tablas)

    def test_f_dedup_compartido_y_linaje_sin_repetir(self):
        comun = memoria_consolidacion_validacion.es_duplicado
        self.assertIs(memoria_sueno.es_duplicado, comun)
        self.assertIs(memoria_consolidacion.es_duplicado, comun)
        texto = ("Mi proyecto Atlas usa Python para crear notas y organizar tareas "
                 "personales desde mi computadora principal todos los dias")
        self.assertTrue(comun(texto, texto.replace("notas", "apuntes")))
        self.assertFalse(comun("Vivo en David", "Compro pan integral cada mañana"))
        uid = "prueba_opt"
        self.mem.almacen.guardar_recuerdo(
            texto, "semantica", "general", "explicito", 0.9, usuario_id=uid)
        self.mem.almacen.guardar_recuerdo(
            texto.replace("notas", "apuntes"), "semantica", "general", "explicito", 0.9,
            usuario_id=uid)
        resultado = memoria_consolidacion.consolidar(self.mem.almacen, uid)
        self.assertTrue(resultado["consolidados"])
        pares = [(f[0], f[1]) for f in self.mem.almacen.conexion.execute(
            "SELECT recuerdo_id,origen_id FROM recuerdos_linaje WHERE usuario_id=?", (uid,))]
        self.assertTrue(pares)
        self.assertEqual(len(pares), len(set(pares)))
        self.assertTrue(all(recuerdo != origen for recuerdo, origen in pares))


if __name__ == "__main__":
    unittest.main()
