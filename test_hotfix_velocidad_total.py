"""Pruebas de regresión: reducción de latencia total y corrección de bugs.

1. dev_copiloto.descubrir_proyectos() sin TypeError con argumentos inválidos.
2. Limpieza de prefijo 'Datos reales: <herramienta>:' antes de la salida vocal.
3. Priorización de modelos Llama rápidos en Groq sin bloques <think>.
4. Voz rápida con Kokoro local, fallback a Salomé y ejecución de al_terminar.
5. Oído streaming WebSocket con fallback transparente a HTTP POST.
"""
import unittest
from unittest.mock import MagicMock, patch

import agente_herramientas as ag
import dev_copiloto as dev
import oido_stream
import proveedores_cadenas as pc
import voz
import voz_rapida


class TestHotfixVelocidadTotal(unittest.TestCase):
    def test_descubrir_proyectos_sin_type_error(self):
        """Verifica que descubrir_proyectos tolere strings vacíos o None sin TypeError."""
        res_vacio = dev.descubrir_proyectos("")
        self.assertIsInstance(res_vacio, list)

        res_none = dev.descubrir_proyectos(None)
        self.assertIsInstance(res_none, list)

        res_str = dev.descubrir_proyectos("1")
        self.assertIsInstance(res_str, list)

        salida = ag.ejecutar("descubrir_proyectos", "")
        self.assertNotIn("TypeError", salida)
        self.assertNotIn("Error en descubrir_proyectos", salida)

    def test_limpieza_prefijo_datos_reales(self):
        """Verifica que el prefijo técnico nunca se reproduzca en voz alta."""
        caso_1 = "Datos reales: descubrir_proyectos: Proyecto_Silvestra (python)"
        limpio_1 = ag.limpiar_para_voz(caso_1)
        self.assertNotIn("Datos reales:", limpio_1)
        self.assertNotIn("descubrir_proyectos:", limpio_1)
        self.assertEqual(limpio_1, "Proyecto_Silvestra (python)")

        caso_2 = "Datos reales: agenda_hoy: Google Workspace aún no está autorizado."
        limpio_2 = ag.limpiar_para_voz(caso_2)
        self.assertNotIn("Datos reales:", limpio_2)
        self.assertNotIn("agenda_hoy:", limpio_2)
        self.assertEqual(limpio_2, "Google Workspace aún no está autorizado.")

        caso_3 = "Datos reales: estado_git: Lyris | rama master"
        limpio_3 = ag.limpiar_para_voz(caso_3)
        self.assertNotIn("Datos reales:", limpio_3)
        self.assertEqual(limpio_3, "Lyris | rama master")

    def test_cerebro_rapido_sin_think(self):
        """Groq debe priorizar llama-3.1-8b-instant y llama-3.3-70b-versatile sin <think>."""
        cands_charla = pc.obtener_candidatos_tarea("charla", {})
        groq_charla = next((c for c in cands_charla if c["nombre"] == "Groq"), None)
        self.assertIsNotNone(groq_charla)
        activos_charla = groq_charla["modelos_activos"]
        self.assertEqual(activos_charla[0], "llama-3.1-8b-instant")
        self.assertIn("llama-3.3-70b-versatile", activos_charla)
        if "qwen/qwen3.8-27b" in activos_charla:
            idx_qwen = activos_charla.index("qwen/qwen3.8-27b")
            self.assertGreater(idx_qwen, 1)

        cands_raz = pc.obtener_candidatos_tarea("razonamiento", {})
        groq_raz = next((c for c in cands_raz if c["nombre"] == "Groq"), None)
        self.assertIsNotNone(groq_raz)
        activos_raz = groq_raz["modelos_activos"]
        self.assertEqual(activos_raz[0], "llama-3.1-8b-instant")
        self.assertIn("llama-3.3-70b-versatile", activos_raz)

    def test_voz_rapida_y_fallback(self):
        """Verifica edge-tts por defecto, fallback a local/Aura si falla y callback al_terminar."""
        # 1. Edge-TTS (Salomé) por defecto como motor principal
        with patch("voz_rapida.sintetizar_edge", return_value=b"AUDIO_SALOME_DEFECTO"):
            audio = voz_rapida.sintetizar_cadena("Mensaje de prueba")
            self.assertEqual(audio, b"AUDIO_SALOME_DEFECTO")

        # 2. Si edge-tts falla (retorna None), fallback al motor rápido (Kokoro/Aura)
        with patch("voz_rapida.sintetizar_edge", return_value=None):
            with patch("voz_rapida.sintetizar_rapido", return_value=b"AUDIO_RAPIDO_RESPALDO"):
                audio = voz_rapida.sintetizar_cadena("Mensaje con fallback")
                self.assertEqual(audio, b"AUDIO_RAPIDO_RESPALDO")

        # 3. Síntesis rápida directa funcional
        audio_rapido = voz_rapida.sintetizar_rapido("Hola, todo listo.", "alegre")
        self.assertIsNotNone(audio_rapido)
        self.assertGreater(len(audio_rapido), 100)

        # 4. Callback al_terminar siempre garantizado
        llamado = []
        instancia_voz = voz.Voz()
        instancia_voz.reproductor = MagicMock()
        instancia_voz.reproductor.reproducir.return_value = True

        with patch.object(instancia_voz, "_audio", return_value=b"AUDIO_TEST"):
            instancia_voz.hablar("Fin del turno", al_terminar=lambda: llamado.append(True))
            import time
            t0 = time.time()
            while not llamado and (time.time() - t0 < 2.0):
                time.sleep(0.05)

        self.assertTrue(llamado, "El callback al_terminar() debe ejecutarse siempre.")

    def test_oido_stream_y_fallback(self):
        """Verifica streamer WebSocket y fallback transparente a HTTP POST."""
        streamer = oido_stream.DeepgramStreamer()
        # Sin clave o con fallo de conexión no debe lanzar excepción
        streamer.error = True
        self.assertIsNone(streamer.finalizar(timeout=0.1))

        # Alimentar audio no debe fallar incluso con error marcado
        streamer.alimentar(b"\x00" * 320)

        # Mock de conexión exitosa
        with patch.object(streamer, "finalizar", return_value=("hola lyris", 1.2)):
            res = streamer.finalizar()
            self.assertEqual(res, ("hola lyris", 1.2))

    def test_saludo_dinamico_con_groq_y_fallback(self):
        """Verifica saludo inicial espontáneo con hora real y fallback ante fallo/timeout."""
        import datetime
        import nacimiento

        # 1. Fallback formatea con la hora real
        ahora = datetime.datetime(2026, 11, 24, 8, 30)
        fb_manana = nacimiento.fallback_saludo_hora("Moisés", "8:30 AM", ahora)
        self.assertIn("Buenos días, Moisés.", fb_manana)
        self.assertIn("8:30 AM", fb_manana)

        ahora_tarde = datetime.datetime(2026, 11, 24, 15, 10)
        fb_tarde = nacimiento.fallback_saludo_hora("Moisés", "3:10 PM", ahora_tarde)
        self.assertIn("Buenas tardes, Moisés.", fb_tarde)
        self.assertIn("3:10 PM", fb_tarde)

        # 2. Generación dinámica exitosa con Groq (mock 200)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hola Moisés, son las 8:30 y el día recién empieza."}}]
        }
        with patch("httpx.post", return_value=mock_resp):
            saludo = nacimiento.generar_saludo_dinamico(creador="Moisés", timeout=2.0)
            self.assertEqual(saludo, "Hola Moisés, son las 8:30 y el día recién empieza.")
            for muletilla in nacimiento.MULETILLAS_PROHIBIDAS:
                self.assertNotIn(muletilla, saludo.lower())

        # 3. Fallback automático ante fallo HTTP o timeout
        with patch("httpx.post", side_effect=RuntimeError("Timeout Groq")):
            saludo_fallo = nacimiento.generar_saludo_dinamico(creador="Moisés", timeout=2.0)
            self.assertIn("Moisés", saludo_fallo)
            self.assertTrue(any(x in saludo_fallo for x in ("Buenos días", "Buenas tardes", "Buenas noches")))


if __name__ == "__main__":
    unittest.main()
