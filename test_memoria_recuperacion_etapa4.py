"""Escenarios de recuperación cognitiva; todas las bases son :memory:."""
import datetime
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro_prompt
import iniciativa
import memoria_consulta
import memoria_recuperacion
from memoria import Memoria
import memoria_tiempo


class TestRecuperacionEtapa4(unittest.TestCase):
    def setUp(self):
        self.mem = Memoria(ruta_db=":memory:", usuario_id="recuperacion")

    def tearDown(self):
        self.mem.cerrar()

    def guardar(self, texto, tipo="semantica", origen="explicito", confianza=.9, fecha=None):
        return self.mem.gestor.guardar(texto, tipo_memoria=tipo, origen=origen,
            confianza=confianza, fecha_evento=fecha or datetime.date.today().isoformat(),
            usuario_id="recuperacion")

    def test_01_recuerdo_explicito(self):
        self.guardar("Mi color favorito es azul")
        p = self.mem.recuperar("¿Qué sabes de mi color favorito?")
        self.assertEqual(p["resultados"][0]["origen"], "explicito")
        self.assertIn("azul", p["resultados"][0]["contenido"])

    def test_02_sinonimos_segunda_pasada(self):
        self.guardar("Ayer reparamos la averia del servidor", "episodica")
        p = self.mem.recuperar("¿Cómo arreglamos ese error?")
        self.assertTrue(any("averia" in x["contenido"] for x in p["resultados"]))

    def test_03_consulta_temporal(self):
        ayer = memoria_tiempo.obtener_fecha_actual() - datetime.timedelta(days=1)
        hoy = memoria_tiempo.obtener_fecha_actual()
        self.guardar(f"[{ayer.isoformat()}] Ayer acordamos revisar el servidor", "episodica", fecha=hoy.isoformat())
        self.guardar(f"[{hoy.isoformat()}] Hoy cocinamos pasta", "episodica", fecha=hoy.isoformat())
        p = self.mem.recuperar("¿Qué acordamos ayer?")
        self.assertEqual(len(p["resultados"]), 1)
        self.assertIn("servidor", p["resultados"][0]["contenido"])

    def test_04_tipos_y_trabajo_ram(self):
        for tipo, texto in (("episodica", "Ayer visité el museo"),
                            ("semantica", "Prefiero café sin azúcar"),
                            ("procedimental", "Primero reinicia el equipo")):
            self.guardar(texto, tipo)
        self.mem.gestor.agregar_trabajo("paso", "Estamos depurando el proyecto", "recuperacion")
        self.assertEqual(self.mem.gestor.listar_trabajo("recuperacion")[0].contenido,
                         "Estamos depurando el proyecto")
        self.assertTrue(self.mem.recuperar("museo")["resultados"])
        self.assertTrue(self.mem.recuperar("café")["resultados"])
        self.assertTrue(self.mem.recuperar("cómo reiniciar equipo")["resultados"])

    def test_05_ambiguedad_y_resolucion_anafórica(self):
        p = self.mem.recuperar("¿Dónde lo dejamos?")
        self.assertTrue(p["ambigua"])
        self.assertTrue(p["consulta"]["contexto_insuficiente"])
        self.mem.gestor.agregar_trabajo("actual", "Proyecto Atlas: falta probar el buscador", "recuperacion")
        a = memoria_consulta.analizar("Continúa donde lo dejamos", "recuperacion",
            self.mem.gestor.listar_trabajo("recuperacion"))
        self.assertIn("Proyecto Atlas", a["resolucion"])
        self.assertFalse(a["ambigua"])

    def test_06_combina_recuerdos(self):
        self.guardar("El proyecto Atlas usa Python")
        self.guardar("El proyecto Atlas requiere pruebas automatizadas", "episodica")
        p = self.mem.recuperar("¿Qué sabemos del proyecto Atlas?", limite=5)
        self.assertGreaterEqual(len(p["resultados"]), 2)

    def test_07_contradicciones_exponen_fuentes(self):
        self.guardar("El proyecto Atlas usa Django", "semantica", "explicito", .95)
        self.guardar("El proyecto Atlas no usa Django", "semantica", "inferido", .55)
        p = self.mem.recuperar("proyecto Atlas Django")
        self.assertTrue(p["contradicciones"])
        c = p["contradicciones"][0]
        self.assertEqual({c["recuerdo_a"]["origen"], c["recuerdo_b"]["origen"]}, {"explicito", "inferido"})

    def test_08_irrelevante_antiguo_no_domina(self):
        viejo = (datetime.date.today() - datetime.timedelta(days=900)).isoformat()
        self.guardar(f"[{viejo}] Me gusta la música clásica", fecha=datetime.date.today().isoformat())
        self.guardar("Mi objetivo es aprender astronomía")
        p = self.mem.recuperar("objetivo aprender astronomía")
        self.assertIn("astronomía", p["resultados"][0]["contenido"])

    def test_09_sin_resultados_cobertura(self):
        p = self.mem.recuperar("¿Qué sabes de volcanes en Marte?")
        self.assertTrue(p["sin_resultados"])
        self.assertEqual(p["cobertura"], "insuficiente")

    def test_10_procedencia_fecha_confianza_formateadas(self):
        self.guardar("Estudio programación cada tarde", "semantica", "inferido", .63)
        p = self.mem.recuperar("programación")
        salida = memoria_recuperacion.formatear(p)
        self.assertIn("inferido", salida)
        self.assertIn("0.63", salida)
        self.assertIn(datetime.date.today().isoformat(), salida)

    def test_11_aislamiento_perfiles(self):
        self.guardar("El faro de pruebas se llama Aurora Norte")
        otro = Memoria(ruta_db=":memory:", usuario_id="otro")
        try:
            self.assertFalse(otro.recuperar("Aurora Norte")["resultados"])
            self.mem.gestor.agregar_trabajo("secreto", "Proyecto privado Atlas", "recuperacion")
            self.assertFalse(otro.gestor.listar_trabajo("otro"))
        finally:
            otro.cerrar()

    def test_12_integracion_prompt_iniciativa_error_y_latencia(self):
        self.guardar("El proyecto Atlas usa Python", "semantica", "explicito", .9)
        live = "[ESTADO ACTUAL EN VIVO DE WINDOWS] Aplicación: Editor"
        prompt = cerebro_prompt.construir_prompt(self.mem, "proyecto Atlas", contexto_adicional=live)
        self.assertIn("explicito", prompt)
        self.assertIn("ESTADO ACTUAL EN VIVO DE WINDOWS", prompt)
        self.assertLess(prompt.index("RECUERDOS HISTÓRICOS"), prompt.rindex("[ESTADO ACTUAL EN VIVO DE WINDOWS]"))
        self.assertIn("EXCLUSIVAMENTE usando [ESTADO ACTUAL EN VIVO DE WINDOWS]", prompt)

        app = SimpleNamespace(memoria=self.mem, cerebro=SimpleNamespace(_pedir=lambda *_: "Bien."), cola=queue.Queue())
        ini = iniciativa.Iniciativa(app)
        ini.motor = SimpleNamespace(revalidar_sugerencia=lambda *_: (True, "ok"),
            marcar_emitida=lambda *_: None)
        sug = SimpleNamespace(prompt_orientacion="proyecto Atlas", emocion_sugerida="neutral")
        ini._hablar(sug)
        self.assertEqual(app.cola.get_nowait()[0], "hablar")

        with patch.object(self.mem.gestor, "buscar", side_effect=RuntimeError("db")):
            fallo = self.mem.recuperar("proyecto Atlas")
        self.assertEqual(fallo["error_almacenamiento"], "RuntimeError")
        t = time.perf_counter()
        for _ in range(20):
            self.mem.recuperar("proyecto Atlas")
        self.assertGreater(time.perf_counter() - t, 0)


if __name__ == "__main__":
    unittest.main()
