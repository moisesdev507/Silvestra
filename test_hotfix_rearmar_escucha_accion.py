"""Regresión: la escucha se rearma tras una acción de sistema que habla.

La causa era el fin_voz de la respuesta del LLM llegando mientras la frase de
la acción aún hablaba: se abria el microfono a los 700 ms con voz ocupada y,
al terminar la accion, no quedaba otro rearmado.
"""
import queue
import unittest
from types import SimpleNamespace

import eventos


class RelojFalso:
    """No ejecuta temporizadores: los guarda para drenarlos en el test."""

    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=25):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class FlujoFalso:
    def __init__(self, voz, fin):
        self.voz, self.fin = voz, fin

    def agregar(self, texto, emocion=None):
        self.voz.ocupada_estado = True
        self.voz.fin_accion = self.fin

    def cerrar(self):
        pass


class VozFalsa:
    """Mantiene ocupada la voz hasta que el test declara terminada la accion."""

    def __init__(self):
        self.ocupada_estado = False
        self.fin_accion = None

    def ocupada(self):
        return self.ocupada_estado

    def hablar(self, texto, callback=None, emocion=None):
        self.ocupada_estado = True

    def flujo(self, callback, **_kw):
        return FlujoFalso(self, callback)

    def terminar_accion(self):
        self.ocupada_estado = False
        fin, self.fin_accion = self.fin_accion, None
        if fin is not None:
            fin()


class TestRearmeEscuchaAccion(unittest.TestCase):
    def _app(self):
        reloj = RelojFalso()
        voz = VozFalsa()
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False,
            flujo=None, pendiente_descanso=False, musica_activa=False,
            escuchadas_durante_voz=[], escuchadas_libres=[], paradas=0,
            voz=voz,
            cara=SimpleNamespace(
                root=reloj,
                decir=lambda *_a, **_kw: None,
                fijar_emocion=lambda *_a: None,
                poner_escuchando=lambda *_a: None,
                programar_retorno_neutral=lambda *_a: None,
            ),
        )

        def escuchar():
            if voz.ocupada():
                app.escuchadas_durante_voz.append("escuchar")
            else:
                app.escuchadas_libres.append("escuchar")
            app.escuchando = True

        def dejar_de_escuchar():
            app.paradas += 1
            app.escuchando = False

        app.escuchar = escuchar
        app._dejar_de_escuchar = dejar_de_escuchar
        app.decir = lambda texto, **_kw: voz.hablar(texto)
        app.ejecutar = lambda accion: app.cola.put(
            ("frase", "Minimizando todas las ventanas."))
        app._es_eco = lambda texto: False
        return app, reloj, voz

    def _drenar_cola(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def test_rearma_tras_accion_que_habla(self):
        app, reloj, voz = self._app()

        eventos.atender_evento(
            app, "respuesta",
            ("Listo, Moisés.", "minimizar_ventanas", "neutral"))
        self._drenar_cola(app)  # La accion encola su frase y sigue hablando.

        # fin_voz del LLM: llega mientras la frase de la accion suena.
        app.cola.put(("fin_voz", None))
        self._drenar_cola(app)
        reloj.drenar()
        self.assertFalse(app.escuchando)
        self.assertEqual(app.escuchadas_durante_voz, [])

        voz.terminar_accion()  # Encola el fin_voz de "Minimizando...".
        self._drenar_cola(app)
        reloj.drenar()

        self.assertEqual(app.escuchadas_durante_voz, [])
        self.assertEqual(app.escuchadas_libres, ["escuchar"])
        self.assertTrue(app.escuchando)

    def test_flujo_normal_sin_accion_sigue_rearmando(self):
        app, reloj, voz = self._app()
        voz.ocupada_estado = False
        eventos.atender_evento(app, "fin_voz", None)
        reloj.drenar()
        self.assertEqual(app.escuchadas_libres, ["escuchar"])
        self.assertTrue(app.escuchando)


if __name__ == "__main__":
    unittest.main()
