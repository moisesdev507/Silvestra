"""Regresiones del motor clásico: Celeste tras Live, WS Deepgram y charla continua."""
import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import oido_adaptacion
import oido_helpers
import oido_ws
import tts_aura_stream
import voz
import voz_ws


class _SesionLiveFalsa:
    def __init__(self):
        self.activo = True

    def detener(self):
        self.activo = False


class _WSFalso:
    """Socket mínimo que entrega un único resultado final."""

    def __init__(self, mensaje):
        self.enviados = []
        self.mensaje = mensaje
        self.lecturas = 0
        self.cerrado = None

    def send(self, dato):
        self.enviados.append(dato)

    def recv(self, timeout=None):
        self.lecturas += 1
        if self.lecturas == 1:
            return self.mensaje
        raise ConnectionError("cerrado")

    def close(self, code=1000):
        self.cerrado = code


class TestCelesteTrasCambio(unittest.TestCase):

    def test_reanudar_limpia_pausa_y_cancelacion_heredada(self):
        tts_aura_stream.detener_reproduccion_activa("prueba")
        self.assertTrue(tts_aura_stream._EVENTO_CANCELAR_STREAM.is_set())
        falso = SimpleNamespace(
            version=2, _activos=1, _pausada=True,
            nivel_volumen=0.75, _estado_lock=threading.RLock(),
        )
        voz.Voz.reanudar(falso)
        self.assertEqual(falso.version, 3)
        self.assertEqual(falso._activos, 0)
        self.assertFalse(falso._pausada)
        self.assertEqual(falso.nivel_volumen, 0.0)
        self.assertFalse(tts_aura_stream._EVENTO_CANCELAR_STREAM.is_set())

    def test_cambio_a_clasico_reanuda_voz_sin_cerrar_app(self):
        import live_audio
        import live_orquestador
        from PySide6.QtWidgets import QApplication

        app = MagicMock()
        app.voz = MagicMock()
        app.oido = MagicMock()
        app.invocacion = MagicMock()
        sesion = _SesionLiveFalsa()
        with patch.object(live_audio, "obtener_api_key", return_value="clave"):
            with patch("estado.cargar", return_value={"modo_voz_principal": "gemini_live"}):
                with patch.object(voz_ws, "detener"):
                    with patch.object(QApplication, "quit") as salir:
                        coord = live_orquestador.CoordinadorLiveSilvestra(app)
                        coord.sesion_live = sesion
                        inicio = time.monotonic()
                        coord.actualizar_modo_voz("clasico")
                        self.assertLess(time.monotonic() - inicio, 0.5)
                        fin = time.monotonic() + 2.0
                        while time.monotonic() < fin and not app.voz.reanudar.called:
                            time.sleep(0.01)
                        app.voz.reanudar.assert_called_once()
                        app.oido.reanudar.assert_called()
                        self.assertFalse(sesion.activo)
                        self.assertIsNone(coord.sesion_live)
                        salir.assert_not_called()

    def test_voz_ws_registra_metrica_y_diagnostica_omision(self):
        def con_audio(_texto, _cancelar, al_iniciar, _al_nivel):
            al_iniciar()
            return True

        salida = io.StringIO()
        with patch.object(tts_aura_stream, "reproducir_stream_aura", side_effect=con_audio):
            with redirect_stdout(salida):
                self.assertTrue(voz_ws.reproducir("¿Sí?"))
        self.assertIn("[tiempo] clasico_tts_primer_audio=", salida.getvalue())

        salida = io.StringIO()
        with patch.object(tts_aura_stream, "reproducir_stream_aura", return_value=False):
            with redirect_stdout(salida):
                self.assertFalse(voz_ws.reproducir("hola"))
        self.assertIn("streaming omitido", salida.getvalue())


class TestWSDeepgramSinDuplicar(unittest.TestCase):

    def test_url_incluye_parametros_de_streaming(self):
        url = oido_ws.url_stream()
        for parametro in (
            "encoding=linear16", "sample_rate=16000", "channels=1",
            "model=nova-3", "language=es-419", "smart_format=true",
            "endpointing=350", "interim_results=true",
        ):
            self.assertIn(parametro, url)

    def test_finalize_devuelve_ws_y_no_duplica_el_buf(self):
        mensaje = json.dumps({
            "is_final": True,
            "result": {"channels": [{"alternatives": [{"transcript": "Kaya"}]}]},
        })
        falso = _WSFalso(mensaje)
        sesion = oido_ws.SesionStreaming(clave="clave")
        sesion.ws = falso
        sesion.activa = True
        sesion.enviar(b"\x00" * 6400, conservar=False)  # silencio previo al VAD
        sesion.enviar(b"\x01" * 6400, conservar=True)   # solo voz detectada

        resultado = sesion.finalizar()
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado[0], "Kaya")
        self.assertAlmostEqual(resultado[1], 0.2, delta=0.01)
        self.assertIn(oido_ws.MENSAJE_FINALIZE, falso.enviados)
        self.assertEqual(falso.cerrado, 1000)
        self.assertEqual(len(sesion.chunks), 1)

    def test_chunks_pcm_se_envian_en_tiempo_real(self):
        mensaje = json.dumps({
            "is_final": True,
            "result": {"channels": [{"alternatives": [{"transcript": "Kaya"}]}]},
        })
        falso = _WSFalso(mensaje)
        sesion = oido_ws.SesionStreaming(clave="clave")
        sesion.ws = falso
        sesion.activa = True
        sesion.enviar(b"\x00" * 6400, conservar=False)
        sesion.enviar(b"\x01" * 6400, conservar=True)
        self.assertEqual(falso.enviados, [b"\x00" * 6400, b"\x01" * 6400])
        self.assertNotIn(oido_ws.MENSAJE_FINALIZE, falso.enviados)

    def test_ensambla_finales_y_reporta_confianza(self):
        primero = json.dumps({
            "is_final": True,
            "result": {"channels": [{"alternatives": [{"transcript": "hola"}]}]},
        })
        segundo = json.dumps({
            "type": "FinalResults",
            "result": {"channels": [{"alternatives": [
                {"transcript": "hola kaya", "confidence": 0.93},
            ]}]},
        })

        class _WSMultifinal:
            def __init__(self, mensajes):
                self.mensajes = list(mensajes)
                self.enviados = []
                self.cerrado = None

            def send(self, dato):
                self.enviados.append(dato)

            def recv(self, timeout=None):
                return self.mensajes.pop(0) if self.mensajes else None

            def close(self, code=1000):
                self.cerrado = code

        falso = _WSMultifinal([primero, segundo])
        sesion = oido_ws.SesionStreaming(clave="clave")
        sesion.ws = falso
        sesion.activa = True
        resultado = sesion.finalizar()
        self.assertEqual(resultado[0], "hola kaya")
        self.assertAlmostEqual(resultado[2], 0.93)
        self.assertFalse(oido_helpers.debe_usar_whisper(resultado))
        self.assertFalse(oido_adaptacion.es_transcripcion_sospechosa(
            resultado[0], confidence=resultado[2], duracion_seg=4.2))

    def test_whisper_solo_por_baja_confianza_o_error_de_red(self):
        self.assertTrue(oido_helpers.debe_usar_whisper(None))
        self.assertTrue(oido_helpers.debe_usar_whisper(("hola", 4.2, 0.84)))
        self.assertFalse(oido_helpers.debe_usar_whisper(("hola", 4.2, 0.88)))
        self.assertFalse(oido_helpers.debe_usar_whisper(("hola", 4.2)))
        self.assertFalse(oido_helpers.debe_usar_whisper(("", 0.5, 1.0)))


class TestVentanaConversacionContinua(unittest.TestCase):

    def test_ventana_se_abre_tras_si_y_tras_respuesta(self):
        import charla_continua
        import invocacion_lyris
        import seguimiento_voz

        app = MagicMock()
        gestor = invocacion_lyris.GestorInvocacion(app)
        try:
            charla_continua.cerrar_ventana_charla()
            with patch.object(invocacion_lyris, "_micro_voz"):
                with patch("estado.cargar", return_value={"palabra_clave": True}):
                    gestor._procesar("kaya", 0.2)
            self.assertTrue(charla_continua.ventana_charla_activa())
            self.assertTrue(gestor.seguimiento_activo)
            self.assertLessEqual(gestor.limite_seguimiento - time.monotonic(), 8.1)

            charla_continua.cerrar_ventana_charla()
            gestor.en_turno = True
            gestor.fin_voz()
            self.assertTrue(charla_continua.ventana_charla_activa())
            self.assertTrue(gestor.seguimiento_activo)
        finally:
            charla_continua.cerrar_ventana_charla()


if __name__ == "__main__":
    unittest.main(verbosity=2)
