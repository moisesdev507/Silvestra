"""Pruebas unitarias para las 3 optimizaciones de voz y oído:
1. Limpieza de correos para TTS en google_workspace.py (sin \u034f, \u200b, tags ni <...>).
2. Evitar doble respuesta en atajos de acciones locales (atajo_multimedia_directo en acciones.py / respuesta_flujo.py).
3. Limpieza de invocaciones repetidas/deformadas en identidad_kaya / invocacion_lyris y umbral de Deepgram en oido_adaptacion.
"""
import unittest
import google_workspace
import acciones
import respuesta_flujo
import identidad_kaya
import invocacion_lyris
import oido_adaptacion


class TestOptimizacionesVoz(unittest.TestCase):

    def test_limpieza_correos_tts(self):
        # Texto con caracteres invisibles Unicode (\u034f, \u200b, \ufeff, etc.) y tags
        sucio = "Factura\u034f de compra \u200ben línea <b>Supermercados</b> &nbsp; <noreply@xtra.com>"
        limpio = google_workspace._limpiar_texto_tts(sucio)
        self.assertNotIn("\u034f", limpio)
        self.assertNotIn("\u200b", limpio)
        self.assertNotIn("\ufeff", limpio)
        self.assertNotIn("<b>", limpio)
        self.assertNotIn("&nbsp;", limpio)
        self.assertNotIn("<noreply@xtra.com>", limpio)
        self.assertEqual(limpio, "Factura de compra en línea Supermercados")

        # Limpieza de remitente
        rem = google_workspace._limpiar_remitente("Supermercados Xtra <facturas@xtra.com>")
        self.assertEqual(rem, "Supermercados Xtra")
        rem2 = google_workspace._limpiar_remitente("<ventas@tienda.com>")
        self.assertEqual(rem2, "ventas")

        # Formato de frase de correo
        frase_correo = google_workspace._formatear_frase_correo("Supermercados Xtra <facturas@xtra.com>", "Tu factura electrónica\u034f")
        self.assertEqual(frase_correo, "Tienes un correo de Supermercados Xtra sobre Tu factura electrónica.")
        self.assertNotIn("\u034f", frase_correo)
        self.assertNotIn("<", frase_correo)

    def test_atajo_multimedia_directo(self):
        # Órdenes de volumen y silencio
        r1 = acciones.atajo_multimedia_directo("baja el volumen")
        self.assertIsNotNone(r1)
        self.assertEqual(r1[0], "Bajando volumen.")
        self.assertEqual(r1[1], "bajar_volumen")

        r2 = acciones.atajo_multimedia_directo("sube volumen")
        self.assertIsNotNone(r2)
        self.assertEqual(r2[0], "Subiendo volumen.")
        self.assertEqual(r2[1], "subir_volumen")

        r3 = acciones.atajo_multimedia_directo("silencia")
        self.assertIsNotNone(r3)
        self.assertEqual(r3[0], "Sonido silenciado o reactivado.")
        self.assertEqual(r3[1], "silenciar")

        # Órdenes de música
        r4 = acciones.atajo_multimedia_directo("pon musica de queen")
        self.assertIsNotNone(r4)
        self.assertIn("queen", r4[0].lower())
        self.assertIn("musica_youtube", r4[1])

        # Asegurar que ejecutar(tecla) no devuelva "Listo."
        ok, msg = acciones.ejecutar("bajar_volumen")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_limpieza_invocaciones_repetidas_y_deformadas(self):
        # Deformaciones fonéticas iniciales pegadas a la orden
        ok, alias, orden = invocacion_lyris.detectar("kaya araya baja volumen")
        self.assertTrue(ok)
        self.assertEqual(orden, "baja volumen")

        ok2, alias2, orden2 = invocacion_lyris.detectar("kaya aya que tengo que hacer hoy")
        self.assertTrue(ok2)
        self.assertEqual(orden2, "que tengo que hacer hoy")

        ok3, alias3, orden3 = invocacion_lyris.detectar("kaya kaya pon musica")
        self.assertTrue(ok3)
        self.assertEqual(orden3, "pon musica")

        # Identidad directa
        ok4, _, ord4 = identidad_kaya.detectar_invocacion("oye kaya alla revisa mi correo")
        self.assertTrue(ok4)
        self.assertEqual(ord4, "revisa mi correo")

    def test_umbral_deepgram_audio_largo_alta_confianza(self):
        # Audio de 4.2s con 2 palabras pero confianza >= 0.92 y palabras normales: NO es sospechoso
        self.assertFalse(oido_adaptacion.es_transcripcion_sospechosa("baja volumen", confidence=0.95, duracion_seg=4.2))

        # Audio de 4.2s con baja confianza (< 0.92) y apenas 1 palabra: sí sospechoso
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("hola", confidence=0.88, duracion_seg=4.2))

        # Frase rota que termina en preposición: sí sospechoso siempre
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("revisa cómo está mi", confidence=0.95, duracion_seg=4.2))


if __name__ == "__main__":
    unittest.main()
