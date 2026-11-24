"""Pruebas unitarias para cerebro_perfil, cronómetro de texto y carril ultrarrápido."""
import io
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cerebro_perfil
import conversacion


class TestCerebroPerfil(unittest.TestCase):
    def test_deteccion_frases_ultrarrapidas(self):
        """Verifica que saludos, agradecimientos y confirmaciones cortas sean ultrarrápidas."""
        frases_positivas = [
            "ok", "gracias", "Ok, gracias.", "muchas gracias", "vale",
            "entendido", "hola", "Hola Lyris", "buenas tardes", "adios",
            "chao", "de acuerdo", "perfecto", "listo"
        ]
        for f in frases_positivas:
            self.assertTrue(cerebro_perfil.es_frase_ultrarrapida(f), f"Fallo al detectar positiva: {f}")

        frases_negativas = [
            "¿Cómo resolver el problema de red wifi?",
            "Recuerda que mañana tengo entrega de programación",
            "Abre el navegador y busca en Google",
            "Calcula la integral de x al cuadrado",
            "¿Qué tiempo hace hoy en Panamá?"
        ]
        for f in frases_negativas:
            self.assertFalse(cerebro_perfil.es_frase_ultrarrapida(f), f"Falso positivo en: {f}")

    def test_cronometro_texto_vs_microfono(self):
        """Verifica que el turno por texto reinicie t_fin_habla a None y t_texto al tiempo actual."""
        app = SimpleNamespace(
            origen_entrada_actual="chat",
            oido=SimpleNamespace(t_fin_habla=100.0, t_texto=100.0),
            t_fin_habla=100.0,
            metricas_turno={}
        )
        cerebro_perfil.inicializar_metricas_turno(app, "Hola")
        self.assertIsNone(app.t_fin_habla)
        self.assertIsNone(app.metricas_turno["t_fin_habla"])
        self.assertIsNotNone(app.t_inicio_texto)
        self.assertGreater(app.metricas_turno["t_texto"], 1000.0)

        # Ahora simula origen micrófono
        app.origen_entrada_actual = "microfono"
        cerebro_perfil.inicializar_metricas_turno(app, "Hola por voz")
        self.assertEqual(app.t_fin_habla, 100.0)
        self.assertEqual(app.metricas_turno["t_fin_habla"], 100.0)
        self.assertIsNone(app.t_inicio_texto)

    def test_emision_perfil_un_solo_primer_token(self):
        """Verifica que emitir_primer_token imprima el formato exacto requerido y no se duplique."""
        perfil = cerebro_perfil.iniciar_perfil("ok")
        time.sleep(0.002)
        perfil.marcar_pre_enrutado()
        time.sleep(0.002)
        perfil.marcar_memoria()
        time.sleep(0.002)
        perfil.marcar_despacho_llm()
        time.sleep(0.002)

        captura = io.StringIO()
        with patch("sys.stdout", captura):
            perfil.emitir_primer_token()
            # Segunda llamada no debe emitir de nuevo
            perfil.emitir_primer_token()

        salida = captura.getvalue().strip()
        self.assertIn("[perfil]", salida)
        self.assertIn("pre_enrutado=", salida)
        self.assertIn("memoria=", salida)
        self.assertIn("despacho_llm=", salida)
        # Una sola línea
        lineas = [l for l in salida.splitlines() if "[perfil]" in l]
        self.assertEqual(len(lineas), 1)


if __name__ == "__main__":
    unittest.main()
