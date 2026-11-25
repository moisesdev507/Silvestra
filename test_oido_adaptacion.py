"""Pruebas unitarias para oido_adaptacion, tolerancia fonética y respaldo Whisper."""
import unittest
from unittest.mock import MagicMock, patch

import oido_adaptacion
import oido_filtro


class TestOidoAdaptacion(unittest.TestCase):
    def test_reparaciones_foneticas_reales(self):
        """Verifica que deformaciones por habla rápida se adapten a la intención real."""
        casos = [
            ("revisa estoy en mi computador", "revisa el estado de mi computador"),
            ("puedes revisar estoy en mi compu", "puedes revisar el estado de mi compu"),
            ("¿Me puedes revisar? Estoy en mi computador, por favor", "¿Puedes revisar el estado de mi computador, por favor"),
            ("mira que estoy en mi laptop", "mira el estado de mi laptop"),
            ("chequea en mi pc", "chequea el estado de mi pc"),
        ]
        for entrada, esperada in casos:
            adaptada = oido_adaptacion.adaptar_texto_fonetico(entrada)
            self.assertEqual(adaptada.lower(), esperada.lower())

    def test_preservacion_frases_casuales_normales(self):
        """Verifica que el habla normal y declaraciones de actividad NO se alteren indebidamente."""
        normales = [
            "estoy en mi computador programando",
            "estoy en mi compu viendo un video",
            "yo estoy en mi laptop descansando",
            "revisa el archivo notas.txt",
            "Kaya qué hora es",
        ]
        for frase in normales:
            adaptada = oido_adaptacion.adaptar_texto_fonetico(frase)
            self.assertEqual(adaptada, frase)

    def test_normalizar_transcripcion_integra_adaptacion(self):
        """Verifica que oido_filtro.normalizar_transcripcion ejecute la capa fonética."""
        entrada = "Kaya revisa estoy en mi compu"
        salida = oido_filtro.normalizar_transcripcion(entrada)
        self.assertIn("el estado de mi compu", salida.lower())

    def test_deteccion_transcripcion_sospechosa_y_respaldo_whisper(self):
        """Verifica que es_transcripcion_sospechosa detecte baja confianza, audio largo con pocas palabras o cortes."""
        # 1. Confianza numérica baja (< 0.62)
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("revisa esto", confidence=0.45))
        self.assertFalse(oido_adaptacion.es_transcripcion_sospechosa("revisa esto", confidence=0.92))

        # 2. Audio largo (> 3.5s) con solo 1-2 palabras (incoherente)
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("hola", confidence=0.88, duracion_seg=4.2))
        self.assertFalse(oido_adaptacion.es_transcripcion_sospechosa("hola qué tal", confidence=0.88, duracion_seg=1.0))

        # 3. Frase terminada en preposición o posesivo colgante
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("revisa cómo está mi", confidence=0.95))
        self.assertTrue(oido_adaptacion.es_transcripcion_sospechosa("estoy en", confidence=0.95))
        self.assertFalse(oido_adaptacion.es_transcripcion_sospechosa("revisa mi computador", confidence=0.95))


if __name__ == "__main__":
    unittest.main()
