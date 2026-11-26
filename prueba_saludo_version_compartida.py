"""Regresión: el saludo inicial siempre incluye la nota de versión compartida."""
import queue
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import habla_espontanea
import identidad_origen
import nacimiento
import saludo_dinamico


class TestSaludoVersionCompartida(unittest.TestCase):
    def test_nota_se_anade_una_sola_vez_y_conserva_el_saludo(self):
        base = "Buenos días, Alex. Qué xopa; todo listo por acá."
        final = saludo_dinamico.con_nota_version(base)
        self.assertTrue(final.startswith(base))
        self.assertIn("versión compartida con amigos", final.lower())
        self.assertEqual(final.count("versión compartida con amigos"), 1)
        self.assertEqual(saludo_dinamico.con_nota_version(final), final)

    def test_generar_saludo_dinamico_incluye_nota_sin_red(self):
        with patch.object(saludo_dinamico.config, "CLAVE", ""), \
             patch.object(saludo_dinamico.config, "CLAVE_CLOUDFLARE", ""), \
             patch.dict("os.environ", {}, clear=True), \
             patch.object(saludo_dinamico.bp, "recopilar_briefing_arranque", lambda **_: {}), \
             patch.object(saludo_dinamico.estado, "cargar", lambda: {}), \
             patch.object(saludo_dinamico.estado, "guardar", lambda _: None), \
             patch.object(saludo_dinamico.httpx, "post",
                          side_effect=AssertionError("El saludo no debe usar red")):
            saludo = saludo_dinamico.generar_saludo_dinamico("Moisés")
        self.assertIn("Moisés", saludo)
        self.assertIn("versión compartida con amigos", saludo.lower())
        self.assertNotIn("Lyris", saludo)

    def test_nota_respeta_la_franja_horaria(self):
        with patch.object(saludo_dinamico.random, "choice", lambda opciones: opciones[0]):
            saludo = saludo_dinamico.con_nota_version(
                saludo_dinamico.fallback_natural_memoria(
                    "Moisés", {}, [], franja="madrugada"))
        self.assertIn("madrugada", saludo)
        self.assertIn("versión compartida con amigos", saludo.lower())
        self.assertTrue(saludo_dinamico._es_coherente_con_franja(saludo, "madrugada"))

    def test_primer_despertar_incluye_nota_y_identidad(self):
        base = tempfile.mkdtemp(prefix="kaya_saludo_")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        ruta = f"{base}/perfil_usuario.json"
        with patch.object(identidad_origen, "ruta_perfil", return_value=ruta):
            identidad_origen.preparar_perfil_usuario("Alex")
            app = MagicMock()
            app.cola = queue.Queue()
            app.coordinador_live = MagicMock()
            app.coordinador_live.esta_live_activo.return_value = False
            app.coordinador_live.es_modo_principal.return_value = False
            with patch.object(nacimiento, "_guardar_ultimo_saludo", lambda _: None):
                nacimiento.saludar(app)
            evento = app.cola.get_nowait()
        saludo = evento[1][0]
        self.assertEqual(evento[0], "saludo_inicial")
        for esperado in ("Alex", identidad_origen.CREADOR,
                         identidad_origen.FECHA_INICIO, "versión compartida con amigos"):
            self.assertIn(esperado, saludo)

    def test_habla_espontanea_incluye_nota_con_cerebro_ausente(self):
        app = MagicMock()
        app.cola = queue.Queue()
        app.cerebro = None
        app.memoria = None
        app.coordinador_live = None
        habla_espontanea.generar_saludo_espontaneo(app)
        saludo = app.cola.get(timeout=3)[1][0]
        self.assertIn("versión compartida con amigos", saludo.lower())
        self.assertEqual(saludo.count("versión compartida con amigos"), 1)


if __name__ == "__main__":
    unittest.main()
