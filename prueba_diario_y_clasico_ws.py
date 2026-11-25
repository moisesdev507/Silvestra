"""Pruebas del diario íntimo, streaming WS/fallback y presentación visual.

Todo se ejecuta sin red real: se parchean Deepgram, el LLM y el archivo del
diario. Qt se inicializa en modo offscreen para validar los estados visuales.
"""
import contextlib
import io
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import estado  # noqa: E402
import oido_ws  # noqa: E402
import voz_ws  # noqa: E402

_REDACCION = (
    "Hoy estuve pensando en la conversación que tuvimos: me quedé reflexionando "
    "sobre lo aprendido y sentí curiosidad por seguir explorando ideas contigo."
)


class _App:
    """App mínima con historial real para la reflexión automática."""

    class _Cola:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    def __init__(self, turnos=3):
        self.cola = self._Cola()
        self.memoria = MagicMock()
        self.memoria.hechos = ["charla sobre programación"]
        self.memoria.creador = "Moisés"
        self.cerebro = MagicMock()
        self.cerebro.historial = []
        for i in range(turnos):
            self.cerebro.historial.append({"role": "user", "content": f"mensaje {i}"})
            self.cerebro.historial.append({"role": "assistant", "content": "te escucho"})


def _parches_diario(tmp):
    """Devuelve gestores de parche para aislar diario, estado y LLM."""
    ruta = os.path.join(tmp, "diario.md")
    return (
        patch.object(estado, "cargar", return_value={}),
        patch.object(estado, "guardar", return_value=True),
        patch("diario.RUTA_DIARIO", ruta),
        patch("diario_helpers.RUTA_DIARIO", ruta),
        patch("diario.obtener_instancia", return_value=None),
        patch("proveedores.completar", return_value=_REDACCION),
    )


def _leer(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


class TestDiarioPrimeraPersona(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "diario.md")
        self.parches = _parches_diario(self.tmp.name)
        for p in self.parches:
            p.start()
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        for p in reversed(self.parches):
            p.stop()
        self.tmp.cleanup()

    def test_helper_detecta_tema_y_exige_primera_persona(self):
        import diario_helpers as dh

        self.assertTrue(dh.es_orden_diario("escribe en tu diario sobre mi día"))
        self.assertTrue(dh.es_orden_diario("anota en tu diario esto que te digo"))
        self.assertFalse(dh.es_orden_diario("abre el navegador"))
        tema = dh.extraer_tema("escribe en tu diario sobre mi conversación con Kaya")
        self.assertIn("conversación", tema)
        self.assertNotIn("escribe", tema.lower())
        self.assertTrue(dh.es_primera_persona("Me quedé reflexionando sobre lo que aprendí."))
        self.assertFalse(dh.es_primera_persona("Anota la lista de compras de Moisés."))
        self.assertTrue(dh.parece_transcripcion("Quiero que anotes mi examen de mañana", "mi examen de mañana"))
        self.assertFalse(dh.parece_transcripcion(_REDACCION, "mi día"))

    def test_clasico_guarda_solo_redaccion_de_kaya(self):
        import diario_intimo

        frase, emo = diario_intimo.atender(
            "escribe en tu diario sobre mi examen de mañana", app=_App()
        )
        self.assertIn("diario", frase.lower())
        self.assertEqual(emo, "calida")
        contenido = _leer(self.ruta)
        self.assertIn("Diario de Kaya", contenido)
        self.assertIn("estuve pensando", contenido)
        self.assertNotIn("examen de mañana", contenido)
        self.assertNotIn("Quiero que", contenido)

    def test_rechaza_eco_del_usuario_aunque_el_llm_lo_devuelva(self):
        import diario_intimo

        with patch("proveedores.completar", return_value="Quiero que anotes mi examen de mañana"):
            frase, emo = diario_intimo.atender("anota en tu diario mi examen", app=_App())
        self.assertIn("No pude redactar", frase)
        self.assertEqual(emo, "seria")
        self.assertFalse(os.path.exists(self.ruta))

    def test_reflexion_automatica_requiere_interaccion_real(self):
        import diario_intimo

        def nueva_app(turnos):
            return _App(turnos)

        with patch("proveedores.completar", return_value=_REDACCION):
            self.assertTrue(diario_intimo.reflexionar(nueva_app(3)))
        contenido = _leer(self.ruta)
        self.assertIn("estuve pensando", contenido)
        self.assertIn("me quedé", contenido.lower())
        os.remove(self.ruta)

        sin_interaccion = _App(0)
        sin_interaccion.cerebro.historial = [{"role": "user", "content": "hola"}]
        with patch("proveedores.completar", return_value=_REDACCION):
            self.assertFalse(diario_intimo.reflexionar(sin_interaccion))
        self.assertFalse(os.path.exists(self.ruta))

    def test_respuesta_flujo_clasico_usa_la_misma_fachada(self):
        import respuesta_flujo

        cerebro = MagicMock()
        cerebro.historial = []
        cerebro.app = _App()
        frase, accion, emo = respuesta_flujo.responder_flujo(
            cerebro, "escribe en mi diario sobre lo que hablamos", lambda *_: None
        )
        self.assertIsNone(accion)
        self.assertIn("diario", frase.lower())
        self.assertEqual(emo, "calida")
        self.assertIn("estuve pensando", _leer(self.ruta))


class TestStreamingWebSocket(unittest.TestCase):
    def test_connect_usa_additional_headers_de_websockets_17(self):
        with patch("websockets.sync.client.connect") as conectar:
            oido_ws._conectar("wss://api.deepgram.com/v1/listen", "MI_TOKEN")
        _, kwargs = conectar.call_args
        self.assertIn("additional_headers", kwargs)
        self.assertNotIn("extra_headers", kwargs)
        self.assertEqual(kwargs["additional_headers"], {"Authorization": "Token MI_TOKEN"})
        self.assertIn("endpointing=350", oido_ws.url_stream())
        self.assertIn("interim_results=true", oido_ws.url_stream())
        self.assertIn("nova-3", oido_ws.url_stream())

    @staticmethod
    def _ws_fake(mensaje=None, fallo_send=False):
        ws = MagicMock()
        ws.send.side_effect = OSError("socket cerrado") if fallo_send else None
        ws.recv.return_value = mensaje
        return ws

    def test_ws_exito_devuelve_transcripcion_y_metrica(self):
        mensaje = ('{"type":"Results","is_final":true,"result":{"channels":'
                   '[{"alternatives":[{"transcript":"hola kaya"}]}]}}')
        salida = io.StringIO()
        with patch.object(oido_ws, "_conectar", return_value=self._ws_fake(mensaje)):
            with contextlib.redirect_stdout(salida):
                sesion = oido_ws.SesionStreaming(clave="token")
                self.assertTrue(sesion.iniciar())
                sesion.enviar(b"\0\0" * 160)
                resultado = sesion.finalizar()
        self.assertEqual(resultado[0], "hola kaya")
        self.assertIn("clasico_stt=", salida.getvalue())
        self.assertIn("(ws)", salida.getvalue())

    def test_ws_caido_activa_fallback_http_limpio(self):
        salida = io.StringIO()
        with patch.object(oido_ws, "_conectar", side_effect=OSError("sin red")):
            with patch("oido_deepgram.transcribir", return_value=("respaldo http", 0.2)) as http:
                with contextlib.redirect_stdout(salida):
                    sesion = oido_ws.SesionStreaming(clave="token")
                    self.assertFalse(sesion.iniciar())
                    sesion.enviar(b"\0\0" * 160)
                    resultado = sesion.finalizar()
        self.assertEqual(resultado[0], "respaldo http")
        http.assert_called_once()
        self.assertIn("(http)", salida.getvalue())

    def test_corte_a_mitad_de_stream_tambien_cae_a_http(self):
        ws = self._ws_fake(fallo_send=True)
        with patch.object(oido_ws, "_conectar", return_value=ws):
            with patch("oido_deepgram.transcribir", return_value=("http tras corte", 0.3)):
                sesion = oido_ws.SesionStreaming(clave="token")
                sesion.iniciar()
                sesion.enviar(b"\0\0" * 80)
                self.assertFalse(sesion.activa)
                self.assertEqual(sesion.finalizar()[0], "http tras corte")


class TestVozStreaming(unittest.TestCase):
    def test_primer_audio_registra_metrica_y_respeta_cancelacion(self):
        salida = io.StringIO()
        llamado = []

        def falso(texto, cancelar=None, al_ini=None, al_niv=None):
            if al_ini:
                al_ini()
            return True

        with patch.object(voz_ws.tts_aura_stream, "reproducir_stream_aura", side_effect=falso):
            with contextlib.redirect_stdout(salida):
                ok = voz_ws.reproducir("hola", al_iniciar=lambda: llamado.append(1))
        self.assertTrue(ok)
        self.assertEqual(llamado, [1])
        self.assertIn("clasico_tts_primer_audio=", salida.getvalue())

    def test_detener_y_reproductor_inyectado(self):
        import tts_aura_stream

        with patch.object(tts_aura_stream, "detener_reproduccion_activa") as detener:
            voz_ws.detener()
        detener.assert_called_once()

        voz = MagicMock()
        voz.version = 1
        reproductor = MagicMock(return_value=True)
        with patch("voz_local.debe_ir_local_primero", return_value=False):
            ok, audio = tts_aura_stream.procesar_frase_consumidor(
                voz, "hola", None, "neutral", 1, 1, None, None, reproductor=reproductor
            )
        self.assertTrue(ok)
        self.assertIsNone(audio)
        reproductor.assert_called_once()


class TestPresentacionVisual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app_qt = QApplication.instance() or QApplication([])

    def test_estados_y_onda_sin_errores(self):
        import cara_presentacion
        import cara_qt

        cara = cara_qt.Cara(lambda: None, lambda: None, lambda: None, lambda: None)
        try:
            cara.poner_escuchando(True)
            self.assertEqual(cara._presentacion_estado, "escuchando")
            cara.poner_escuchando(False)
            cara.poner_herramienta(True)
            self.assertEqual(cara._presentacion_estado, "herramienta")
            self.assertTrue(cara.pensando)
            cara.decir("Hola Moisés, estoy lista.")
            self.assertGreaterEqual(cara._presentacion_progreso, 0.0)
            cara_presentacion.avanzar(cara, time.time() + 0.4)
            self.assertLessEqual(cara._presentacion_progreso, 1.0)
            self.assertGreater(cara._presentacion_nivel, 0.0)
            cara.paintEvent(None)
            cara.poner_hablando(True)
            self.assertEqual(cara._presentacion_estado, "hablando")
            cara.paintEvent(None)
        finally:
            cara.close()
            cara.deleteLater()

    def test_opacidad_de_despliegue_es_suave(self):
        import cara_presentacion

        self.assertEqual(cara_presentacion.opacidad_despliegue(0), 0.0)
        self.assertEqual(cara_presentacion.opacidad_despliegue(1), 1.0)
        medio = cara_presentacion.opacidad_despliegue(0.5)
        self.assertGreater(medio, 0.5)
        self.assertLess(medio, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
