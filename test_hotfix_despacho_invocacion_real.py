"""Regresión real: oído -> invocación -> eventos -> cerebro -> memoria -> voz."""
import contextlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import conversacion
import eventos
import invocacion_lyris
import memoria_persistente
import oido as oido_mod
import oido_deepgram
import respuesta_flujo
from invocacion_pruebas import CaraFalsa, fabricar_app
from oido import Oido

ORDEN = ("recuerda que mañana tengo entrega de programación 1 "
         "en la fiec a las 9 de la mañana")
TRANSCRITO = f"Lyris, {ORDEN}."
SEGUIMIENTO = "recuerda que mañana tengo entrega de programación 1"


class Reloj:
    def __init__(self, inicial=1000.0):
        self.valor = inicial

    def __call__(self):
        return self.valor

    def avanzar(self, segundos):
        self.valor += segundos


class FlujoFalso:
    def __init__(self, **_kw):
        self.bloques = 3

    def asegurar_flujo(self):
        pass

    def drenar(self):
        pass

    def aplicar_guarda_antieco(self, **_kw):
        pass

    def leer(self, timeout=0.1):
        if self.bloques <= 0:
            return None
        self.bloques -= 1
        return np.full(800, 500, dtype=np.int16)


class VadFalso:
    def __init__(self, **_kw):
        self.entregas, self.completo = 0, False

    def reset(self):
        self.entregas, self.completo = 0, False

    def alimentar(self, _datos):
        self.entregas += 1
        if self.entregas >= 2:
            self.completo = True

    def detectando_voz(self):
        return True

    def hay_segmento_completo(self):
        return self.completo

    def flush(self):
        pass

    def extraer_segmento(self):
        return np.sin(np.linspace(0, 100, 8000)).astype(np.float32) * 0.3


class FlujoVozFalso:
    def __init__(self, al_terminar=None):
        self.al_terminar = al_terminar
        self.frases = []
        self.cerrado = False

    def agregar(self, frase, emocion=None):
        self.frases.append(frase)

    def cerrar(self):
        self.cerrado = True


class VozFalsa:
    def __init__(self):
        self.hablado = []
        self.flujos = []

    def ocupada(self):
        return False

    def flujo(self, al_terminar=None, **_kw):
        flujo = FlujoVozFalso(al_terminar)
        self.flujos.append(flujo)
        return flujo

    def hablar(self, texto, al_terminar=None, emocion=None):
        self.hablado.append(texto)
        flujo = self.flujo(al_terminar)
        flujo.agregar(texto)
        flujo.cerrar()


class TestDespachoInvocacionReal(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.cerebro_visto = []
        self.recuerdos = []
        self.termino = threading.Event()
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.db = os.path.join(self.temporal.name, "memoria.db")
        silencioso = SimpleNamespace(reproducir_feedback_escucha=lambda **_kw: None)

        def responder(_cerebro, texto, _al_frase, on_primer_token=None):
            self.cerebro_visto.append(texto)
            if on_primer_token:
                on_primer_token()
            self.recuerdos.append(memoria_persistente.guardar_recuerdo(
                "general", "entrega", texto, ruta_db=self.db))
            self.termino.set()
            return "Listo, lo tendré presente."

        parches = (
            patch.object(time, "monotonic", self.reloj),
            patch.object(oido_mod, "FlujoMicrofono", FlujoFalso),
            patch.object(oido_mod, "DetectorVozSilero", VadFalso),
            patch.dict(sys.modules, {"oido_feedback": silencioso}),
            patch.object(invocacion_lyris, "_micro_voz", lambda _app: None),
            patch.object(invocacion_lyris, "_sonido", lambda *_a: None),
            patch.object(eventos.sonidos_ui, "reproducir", lambda *_a, **_k: None),
            patch.object(respuesta_flujo, "responder_flujo", responder),
            patch("correcciones.es_correccion", lambda _t: False),
            patch("naturalidad.registrar_turno_usuario", lambda _t: None),
            patch("naturalidad.registrar_turno_asistente", lambda _t: None),
            patch("control_seguridad.es_accion_prohibida", lambda _t: False),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def _app(self):
        app, _enviados, _hablado = fabricar_app()
        app.oido = Oido(SimpleNamespace(), lambda: "Moisés, Lyris")
        app.voz = VozFalsa()
        app.cerebro = SimpleNamespace(turno_invitado=False)
        app._fragmentos_voz = False
        app.ultimo_dicho = ""
        app.enviar = lambda texto: conversacion.enviar(app, texto)
        return app

    def _escuchar(self, app, texto):
        app.oido._flujo = FlujoFalso()
        app.oido._vad = VadFalso()
        oido_deepgram.reiniciar()
        with patch.object(oido_deepgram, "transcribir", lambda *_a: (texto, 1.2)):
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                resultado = app.oido.escuchar(app=app)
        return resultado, salida.getvalue()

    def _drenar(self, app):
        for _ in range(50):
            while not app.cola.empty():
                tipo, valor = app.cola.get_nowait()
                eventos.atender_evento(app, tipo, valor)
            if self.termino.is_set():
                break
            self.termino.wait(0.02)
        self.assertTrue(self.termino.is_set(), "el cerebro no recibió la orden")
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)
        return app

    def _ciclo(self, app, texto):
        transcrito, salida = self._escuchar(app, texto)
        self.assertIsNotNone(transcrito)
        self.assertIn("Deepgram valido: sin Whisper", salida)
        app.invocacion._procesar(transcrito, duracion=1.2)
        self._drenar(app)
        return transcrito

    def test_deepgram_vacio_recupera_palabras_sin_segundo_whisper(self):
        oido_deepgram.reiniciar()
        respuesta = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "metadata": {"duration": 1.91},
                "results": {"channels": [{"alternatives": [{
                    "transcript": "",
                    "words": [{"word": "Iris"}],
                }]}]},
            })
        post = Mock(return_value=respuesta)
        with patch.object(oido_deepgram.config, "DEEPGRAM_API_KEY", "prueba",
                          create=True), \
                patch.object(oido_deepgram.config, "DEEPGRAM_MODEL", "",
                             create=True), \
                patch.object(oido_deepgram.httpx, "post", post):
            resultado = oido_deepgram.transcribir(b"wav")

        self.assertEqual(resultado, ("Iris", 1.91))
        self.assertEqual(post.call_count, 1)

    def test_orden_fiaca_llega_al_cerebro_memoria_y_voz(self):
        app = self._app()
        self._ciclo(app, TRANSCRITO)
        self.assertEqual(self.cerebro_visto, [ORDEN])
        self.assertEqual(len(self.recuerdos), 1)
        self.assertIn("fiec", self.recuerdos[0]["valor"])
        self.assertEqual(app.voz.hablado, ["Listo, lo tendré presente."])
        self.assertTrue(all(f.cerrado for f in app.voz.flujos))

    def test_iris_mas_11s_y_orden_sin_wakeword_despacha_igual(self):
        app = self._app()
        micro, _salida = self._escuchar(app, "Iris")
        self.assertEqual(micro, "Iris")
        app.invocacion._procesar(micro, duracion=1.2)
        self.assertTrue(app.invocacion.esperando_orden)
        self.assertAlmostEqual(app.invocacion.limite_orden, 1020.0, delta=0.01)
        self.assertFalse(self.cerebro_visto)

        self.reloj.avanzar(11.0)  # audio largo + latencia de Deepgram
        self.assertLess(self.reloj(), app.invocacion.limite_orden)
        self._ciclo(app, SEGUIMIENTO)

        self.assertEqual(self.cerebro_visto, [SEGUIMIENTO])
        self.assertEqual(len(self.recuerdos), 1)
        self.assertEqual(app.voz.hablado, ["Listo, lo tendré presente."])


if __name__ == "__main__":
    unittest.main()
