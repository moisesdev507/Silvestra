"""Pruebas unitarias para identidad_kaya, wake-word, habla espontánea y voz Kaya."""
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import habla_espontanea
import identidad_kaya
import oido
import oido_deepgram
import voz_rapida


class TestIdentidadKaya(unittest.TestCase):
    def test_keyterm_deepgram_y_prompt_whisper(self):
        """Verifica que oido_deepgram y oido tengan configurado Kaya y no Lyris."""
        self.assertIn("Kaya", oido_deepgram.KEYTERM)
        self.assertNotIn("Lyris", oido_deepgram.KEYTERM)
        self.assertIn("Kaya", oido.PROMPT_WHISPER)
        self.assertNotIn("Lyris", oido.PROMPT_WHISPER)

    def test_deteccion_positiva_variantes_kaya(self):
        """Verifica que 'Kaya', 'Kaia', 'Caya' y 'Oye calla/calle' se detecten como invocación."""
        positivas = [
            ("Kaya qué hora es", "kaya"),
            ("Hola kaia, cómo estás", "kaia"),
            ("Caya abre la ventana", "caya"),
            ("Oye calla, qué hora es", "calla"),
            ("Calla, dime el clima", "calla"),
            ("Hey calla", "calla"),
            ("kalla, detente", "kalla"),
            ("Calle, ¿puedes revisar mi pantalla?", "calle"),
            ("Oye calle, qué hora es", "calle"),
            ("calle revisa esto", "calle"),
        ]
        for texto, alias_esperado in positivas:
            detectado, alias, orden = identidad_kaya.detectar_invocacion(texto)
            self.assertTrue(detectado, f"Fallo al detectar: {texto}")
            self.assertEqual(alias, alias_esperado, f"Alias incorrecto en: {texto}")

    def test_deteccion_frase_truncada(self):
        """Verifica que es_frase_truncada detecte palabras colgantes finales."""
        self.assertTrue(identidad_kaya.es_frase_truncada("Kaya, revisa cómo está mi."))
        self.assertTrue(identidad_kaya.es_frase_truncada("revisa el"))
        self.assertTrue(identidad_kaya.es_frase_truncada("puedes abrir la"))
        self.assertTrue(identidad_kaya.es_frase_truncada("esto es para"))
        self.assertFalse(identidad_kaya.es_frase_truncada("Kaya qué hora es"))
        self.assertFalse(identidad_kaya.es_frase_truncada("revisa cómo está mi computador"))

    def test_rechazo_falsos_positivos_calla_verbal(self):
        """Verifica que el uso verbal o sustantivo de 'calla' / 'calle' sea rechazado."""
        negativas = [
            "él no se calla nunca",
            "no calla esa música",
            "se calla la boca",
            "te calla de inmediato",
            "quédate callada por favor",
            "ni calla ni deja hablar",
            "estoy en la calle",
            "cruzó la calle corriendo",
            "por la calle principal",
            "de la calle",
            "una calle oscura",
        ]
        for texto in negativas:
            detectado, alias, orden = identidad_kaya.detectar_invocacion(texto)
            self.assertFalse(detectado, f"Falso positivo en: {texto} (detectó {alias})")

    def test_habla_espontanea_sin_bloquear_y_sin_cliches(self):
        """Verifica que habla_espontanea genere saludo sin bloquear y sin frases cliché."""
        app = SimpleNamespace(
            cola=queue.Queue(),
            memoria=SimpleNamespace(creador="Moisés"),
            cerebro=SimpleNamespace(_pedir=lambda *a, **k: "Qué xopa Moisés, buenas tardes por acá.")
        )
        t0 = time.perf_counter()
        habla_espontanea.generar_saludo_espontaneo(app)
        t_enlace = time.perf_counter() - t0
        self.assertLess(t_enlace, 0.1, "La función no debe bloquear el hilo")

        # Esperar que la tarea en segundo plano ponga en cola
        evento = app.cola.get(timeout=2.0)
        self.assertEqual(evento[0], "saludo_inicial")
        saludo, emocion = evento[1]
        self.assertTrue(len(saludo) >= 10)

        # Verificar ausencia de clichés robóticos
        cliches = ["sistemas en línea", "lista para servirte", "en qué te ayudo", "cómo puedo asistirte"]
        for c in cliches:
            self.assertNotIn(c, saludo.lower())

        # Probar fallback offline
        saludo_off = habla_espontanea.fallback_saludo_offline("Moisés")
        for c in cliches:
            self.assertNotIn(c, saludo_off.lower())

    def test_voz_prioriza_deepgram_aura_kaya(self):
        """Verifica que sintetizar_cadena priorice Deepgram Aura-2 antes que Edge-TTS."""
        with patch.object(voz_rapida, "sintetizar_deepgram", return_value=b"AUDIO_AURA_KAYA") as mock_dg, \
             patch.object(voz_rapida, "sintetizar_edge", return_value=b"AUDIO_SALOME") as mock_edge, \
             patch.object(voz_rapida.voz_cache, "obtener_audio_cache", return_value=None), \
             patch.object(voz_rapida.voz_local, "debe_ir_local_primero", return_value=False):
            audio = voz_rapida.sintetizar_cadena("Hola mundo")
            self.assertEqual(audio, b"AUDIO_AURA_KAYA")
            mock_dg.assert_called_once()
            mock_edge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
