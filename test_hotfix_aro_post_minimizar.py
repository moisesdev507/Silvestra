"""Regresión: aro amarillo (escuchando) tras minimizar ventanas.

En cara_dibujo.py el aro es amarillo cuando 'escuchando' o 'pensando' estan
activos, y cian/azul en reposo. Tras la segunda frase de la accion, la cara
podia quedar desincronizada de app.escuchando y el aro se quedaba azul.
"""
import queue
import time
import unittest
from types import SimpleNamespace

import conversacion
import eventos


class RelojFalso:
    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=10):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class CaraFalsa:
    def __init__(self, root):
        self.root = root
        self.escuchando = False
        self.pensando = False
        self.llamadas_escucha = []

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)
        self.llamadas_escucha.append(bool(valor))

    def decir(self, texto, _ms=None, emocion=None):
        self.pensando = str(texto).startswith("«")

    def fijar_emocion(self, _emocion):
        pass

    def programar_retorno_neutral(self, _ms=2500):
        pass


class VozFalsa:
    def __init__(self):
        self.ocupada_estado = False
        self.fin = None

    def ocupada(self):
        return self.ocupada_estado

    def hablar(self, texto, callback=None, emocion=None):
        self.ocupada_estado = True
        self.fin = callback

    def flujo(self, callback, **_kw):
        return SimpleNamespace(agregar=lambda _t, emocion=None: None,
                               cerrar=lambda: None)


class TestAroPostMinimizar(unittest.TestCase):
    def _app(self):
        reloj = RelojFalso()
        cara = CaraFalsa(reloj)
        voz = VozFalsa()
        app = SimpleNamespace(
            cola=queue.Queue(), cara=cara, voz=voz, conversacion=True,
            escuchando=False, flujo=None, silencios=0, musica_activa=False,
            pendiente_descanso=False, ultimo_dicho="",
        )
        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app.decir = lambda t, **kw: voz.hablar(t, lambda: app.cola.put(("fin_voz", None)))
        app.ejecutar = lambda a: app.cola.put(("frase", "Minimizando todas las ventanas."))
        return app, reloj, cara, voz

    def _drenar(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def test_aro_vuelve_a_amarillo_tras_minimizar(self):
        app, reloj, cara, voz = self._app()

        # Turno: "«minimaliza la ventana actual»" pone pensando (amarillo).
        cara.decir("«minimaliza la ventana actual»", 60000)
        app._dejar_de_escuchar = lambda: (
            setattr(app, "escuchando", False), cara.poner_escuchando(False))
        app._dejar_de_escuchar()

        # Respuesta del interceptor y segunda frase de la accion.
        eventos.atender_evento(
            app, "respuesta", ("Minimizando la ventana.", "minimizar_todo", "alegre"))
        self._drenar(app)  # frase de control_laptop -> pensando=False
        self.assertFalse(cara.pensando)

        # Desincronizacion: app ya escucha pero la cara sigue en azul.
        app.escuchando = True
        cara.poner_escuchando(False)
        self.assertFalse(cara.escuchando)

        voz.ocupada_estado = False
        app.escuchando = False
        app.cola.put(("fin_voz", None))
        self._drenar(app)
        reloj.drenar()

        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)
        self.assertIn(True, cara.llamadas_escucha)

    def test_fin_voz_de_la_segunda_frase_no_se_descarta(self):
        app, reloj, _cara, _voz = self._app()
        app.escuchando = False

        eventos.atender_evento(app, "fin_voz", None)
        self.assertTrue(getattr(app, "_rearme_activo", False))
        self.assertEqual(len(reloj.temporizadores), 1)

        # Llega el fin_voz de "Minimizando todas las ventanas." con el
        # rearme anterior ainda pendiente: debe programar el suyo.
        eventos.atender_evento(app, "fin_voz", None)
        self.assertEqual(len(reloj.temporizadores), 2)

    def test_apagado_legitimo_no_fuerza_amarillo(self):
        app, reloj, cara, _voz = self._app()
        app.conversacion = False
        app.escuchando = False
        eventos.atender_evento(app, "fin_voz", None)
        reloj.drenar()
        self.assertFalse(cara.escuchando)


if __name__ == "__main__":
    unittest.main()
