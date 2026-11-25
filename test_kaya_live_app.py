"""Pruebas unitarias para kaya_live_app.py y callbacks de kaya_live_nucleo.py."""
import unittest
from unittest.mock import MagicMock

import kaya_live_app
import kaya_live_nucleo


class TestKayaLiveAppPuente(unittest.TestCase):

    def test_energia_pcm16(self):
        """Verifica cálculo de energía y normalización de PCM."""
        silencio = b"\x00\x00" * 100
        self.assertEqual(kaya_live_nucleo.calcular_energia_pcm16(silencio), 0.0)
        self.assertEqual(kaya_live_nucleo.calcular_energia_pcm16(b""), 0.0)

        # Señal alta
        audio = b"\xff\x7f" * 100
        energia = kaya_live_nucleo.calcular_energia_pcm16(audio)
        self.assertGreater(energia, 0.5)

    def test_callbacks_sesion_live(self):
        """Verifica que la sesión Live invoque callbacks de estado, nivel y transcripción."""
        estados = []
        niveles = []
        textos = []

        sesion = kaya_live_nucleo.SesionKayaLive(
            on_estado=lambda e: estados.append(e),
            on_nivel_voz=lambda n: niveles.append(n),
            on_transcripcion=lambda r, t: textos.append((r, t)),
        )

        sesion._notificar_estado("conectando")
        sesion._notificar_estado("escuchando")
        sesion._notificar_nivel_voz(0.75)
        sesion._notificar_transcripcion("kaya", "Hola mundo")

        self.assertEqual(estados, ["conectando", "escuchando"])
        self.assertEqual(niveles, [0.75])
        self.assertEqual(textos, [("kaya", "Hola mundo")])

    def test_puente_qt_encolado_y_drenado(self):
        """Verifica que PuenteLiveQt encole eventos y los despache a la Cara mockeada sin Qt activo."""
        cara_mock = MagicMock()
        sesion = kaya_live_nucleo.SesionKayaLive()

        # Creamos puente sin iniciar QTimer para test puro
        puente = object.__new__(kaya_live_app.PuenteLiveQt)
        puente.cara = cara_mock
        puente.sesion = sesion
        import queue
        puente.cola_eventos = queue.Queue(maxsize=100)
        puente.corriendo = True
        puente._conectar_callbacks()

        # Encolar eventos simulados
        sesion._notificar_estado("escuchando")
        sesion._notificar_nivel_voz(0.6)
        sesion._notificar_transcripcion("kaya", "Respuesta de voz")

        # Drenar cola
        puente._drenar_cola()

        cara_mock.poner_escuchando.assert_called_with(True)
        self.assertEqual(cara_mock.nivel_volumen, 0.6)
        cara_mock.decir.assert_called_with("Respuesta de voz")


if __name__ == "__main__":
    unittest.main()
