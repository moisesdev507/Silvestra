"""Regresión: la nota de versión compartida solo aparece en el .exe compilado."""
import queue
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import habla_espontanea
import identidad_origen
import modo_compartido
import nacimiento
import saludo_dinamico


def _sin_red():
    """Devuelve parches para generar el saludo sin consultar ninguna API."""
    return (
        patch.object(saludo_dinamico.config, "CLAVE", ""),
        patch.object(saludo_dinamico.config, "CLAVE_CLOUDFLARE", ""),
        patch.dict("os.environ", {}, clear=True),
        patch.object(saludo_dinamico.bp, "recopilar_briefing_arranque", lambda **_: {}),
        patch.object(saludo_dinamico.estado, "cargar", lambda: {}),
        patch.object(saludo_dinamico.estado, "guardar", lambda _: None),
        patch.object(saludo_dinamico.httpx, "post",
                     side_effect=AssertionError("El saludo no debe usar red")),
    )


class TestSaludoVersionCompartida(unittest.TestCase):
    def test_desarrollo_no_anade_nota(self):
        base = "Buenos días, Alex. Qué xopa; todo listo por acá."
        with patch.object(modo_compartido, "es_version_compartida", return_value=False):
            self.assertEqual(saludo_dinamico.con_nota_version(base), base)

    def test_nota_se_anade_una_sola_vez_y_conserva_el_saludo(self):
        base = "Buenos días, Alex. Qué xopa; todo listo por acá."
        with patch.object(modo_compartido, "es_version_compartida", return_value=True):
            final = saludo_dinamico.con_nota_version(base)
            self.assertEqual(saludo_dinamico.con_nota_version(final), final)
        self.assertTrue(final.startswith(base))
        self.assertIn("versión compartida con amigos", final.lower())
        self.assertEqual(final.count("versión compartida con amigos"), 1)

    def test_generar_saludo_dinamico_incluye_nota_sin_red_en_compartida(self):
        parches = _sin_red()
        with patch.object(modo_compartido, "es_version_compartida", return_value=True):
            for parche in parches:
                parche.start()
            try:
                saludo = saludo_dinamico.generar_saludo_dinamico("Moisés")
            finally:
                for parche in reversed(parches):
                    parche.stop()
        self.assertIn("Moisés", saludo)
        self.assertIn("versión compartida con amigos", saludo.lower())
        self.assertNotIn("Lyris", saludo)

    def test_generar_saludo_dinamico_sin_nota_en_desarrollo(self):
        parches = _sin_red()
        with patch.object(modo_compartido, "es_version_compartida", return_value=False):
            for parche in parches:
                parche.start()
            try:
                saludo = saludo_dinamico.generar_saludo_dinamico("Moisés")
            finally:
                for parche in reversed(parches):
                    parche.stop()
        self.assertIn("Moisés", saludo)
        self.assertNotIn("versión compartida con amigos", saludo.lower())

    def test_nota_respeta_la_franja_horaria(self):
        with patch.object(modo_compartido, "es_version_compartida", return_value=True), \
             patch.object(saludo_dinamico.random, "choice", lambda opciones: opciones[0]):
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
        with patch.object(identidad_origen, "ruta_perfil", return_value=ruta), \
             patch.object(modo_compartido, "es_version_compartida", return_value=True):
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

    def test_primer_despertar_sin_nota_en_desarrollo(self):
        base = tempfile.mkdtemp(prefix="kaya_saludo_")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        ruta = f"{base}/perfil_usuario.json"
        with patch.object(identidad_origen, "ruta_perfil", return_value=ruta), \
             patch.object(modo_compartido, "es_version_compartida", return_value=False):
            identidad_origen.preparar_perfil_usuario("Alex")
            app = MagicMock()
            app.cola = queue.Queue()
            app.coordinador_live = MagicMock()
            app.coordinador_live.esta_live_activo.return_value = False
            app.coordinador_live.es_modo_principal.return_value = False
            with patch.object(nacimiento, "_guardar_ultimo_saludo", lambda _: None):
                nacimiento.saludar(app)
            saludo = app.cola.get_nowait()[1][0]
        self.assertIn("Alex", saludo)
        self.assertNotIn("versión compartida con amigos", saludo.lower())

    def _saludo_espontaneo(self, compartida):
        app = MagicMock()
        app.cola = queue.Queue()
        app.cerebro = None
        app.memoria = None
        app.coordinador_live = None
        with patch.object(modo_compartido, "es_version_compartida",
                          return_value=compartida):
            habla_espontanea.generar_saludo_espontaneo(app)
            saludo = app.cola.get(timeout=3)[1][0]
        return saludo

    def test_habla_espontanea_incluye_nota_en_compartida(self):
        saludo = self._saludo_espontaneo(True)
        self.assertIn("versión compartida con amigos", saludo.lower())
        self.assertEqual(saludo.count("versión compartida con amigos"), 1)

    def test_habla_espontanea_sin_nota_en_desarrollo(self):
        saludo = self._saludo_espontaneo(False)
        self.assertNotIn("versión compartida con amigos", saludo.lower())


if __name__ == "__main__":
    unittest.main()
