"""Pruebas unitarias para kaya_live_puente.py."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import kaya_live_puente


class TestKayaLivePuente(unittest.TestCase):

    def test_adaptador_voz_muda_captura_sin_reproducir(self):
        """Verifica que AdaptadorVozMuda capture texto en memoria sin usar PortAudio ni TTS."""
        voz = kaya_live_puente.AdaptadorVozMuda()
        llamado_callback = False

        def cb():
            nonlocal llamado_callback
            llamado_callback = True

        voz.hablar("Mensaje silencioso de prueba", callback=cb)
        self.assertTrue(llamado_callback)
        self.assertIn("Mensaje silencioso", voz.obtener_captura())

    def test_adaptador_app_muda_recibe_cola(self):
        """Verifica que AdaptadorAppMuda almacene mensajes de app.cola."""
        voz = kaya_live_puente.AdaptadorVozMuda()
        app = kaya_live_puente.AdaptadorAppMuda(voz)
        app.cola.put(("frase", ("Abriendo bloc de notas", "neutral")))
        app.cola.put("Mensaje directo")

        self.assertIn("Abriendo bloc de notas", app.cola_mensajes)
        self.assertIn("Mensaje directo", app.cola_mensajes)

    def test_ejecutar_accion_local_vacia(self):
        """Verifica que una acción vacía no falle."""
        res = kaya_live_puente.ejecutar_accion_local("")
        self.assertIn("No se especificó", res)

    def test_ejecutar_accion_local_telemetria(self):
        """Verifica que comandos de telemetría devuelvan reporte de batería/CPU."""
        with patch("acciones.telemetria_local", return_value="Batería al 80%"):
            res = kaya_live_puente.ejecutar_accion_local("cuanta batería tengo")
            self.assertEqual(res, "Batería al 80%")

    def test_ejecutar_accion_diario(self):
        """Verifica que la consulta del diario devuelva la última entrada sin hablar por voz."""
        with patch("diario.Diario.obtener_ultima_entrada", return_value="Reflexionando con Moisés"):
            res = kaya_live_puente.ejecutar_accion_local("qué dice tu diario")
            self.assertIn("Reflexionando con Moisés", res)

    def test_ejecutar_accion_ideas_y_pendientes(self):
        """Verifica que consultas de ideas o hilos pendientes devuelvan el resumen."""
        with patch("ideas.resumen", return_value="integrar IoT (pedida 3 veces)"):
            res = kaya_live_puente.ejecutar_accion_local("cuáles son mis ideas pendientes")
            self.assertIn("integrar IoT", res)

    def test_cargar_contexto_memoria_live(self):
        """Verifica que cargar_contexto_memoria_live retorne formato adecuado."""
        ctx = kaya_live_puente.cargar_contexto_memoria_live()
        self.assertTrue(isinstance(ctx, str))
        if ctx:
            self.assertIn("Memoria y contexto persistente", ctx)

    def test_guardar_turno_memoria_seguro(self):
        """Verifica que guardar_turno_o_resumen_memoria se ejecute sin excepciones."""
        turnos = [
            {"role": "user", "content": "Estoy avanzando con el proyecto de tesis de software"},
            {"role": "assistant", "content": "¡Qué bien! Cuéntame qué llevas hecho."},
        ]
        kaya_live_puente.guardar_turno_o_resumen_memoria(turnos)


if __name__ == "__main__":
    unittest.main()
