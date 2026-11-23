"""Regresión: transcripciones tras un turno no deben ignorarse como eco.

Tras "Listo, minimalizando ventanas.", frases como "Liris, minimaliza la
ventana actual, por favor." tenian ratio ~0.62 con ultimo_dicho y el guard
de eco de eventos.py las descartaba sin voz_dueno, cerebro ni log.
"""
import queue
import unittest
from types import SimpleNamespace

import conversacion
import eventos


class RelojFalso:
    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=20):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class VozFalsa:
    def __init__(self):
        self.ocupada_estado = False

    def ocupada(self):
        return self.ocupada_estado

    def hablar(self, texto, callback=None, emocion=None):
        self.ocupada_estado = True
        self.fin = callback

    def terminar(self, cola):
        self.ocupada_estado = False
        if getattr(self, "fin", None) is not None:
            fin, self.fin = self.fin, None
            fin()


class TestOidoNoIgnorado(unittest.TestCase):
    def _app(self):
        reloj = RelojFalso()
        voz = VozFalsa()
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False,
            flujo=None, silencios=0, pendiente_descanso=False,
            musica_activa=False, ultimo_dicho="Te escucho. Háblame.",
            evaluados=[], enviados=[], acciones_fallidas=[], carencias=[],
            voz=voz,
            voz_dueno=SimpleNamespace(
                activa=False, evaluar_entrada_voz=lambda t: app.evaluados.append(t),
                autorizar_accion=lambda a: (True, "")),
            propuestas=SimpleNamespace(
                detectar_carencia_accion=lambda a: app.carencias.append(a)),
            cara=SimpleNamespace(
                root=reloj,
                decir=lambda *_a, **_kw: None,
                fijar_emocion=lambda *_a, **_kw: None,
                poner_escuchando=lambda *_a: None,
                programar_retorno_neutral=lambda *_a: None,
            ),
        )

        def decir(texto, **_kw):
            app.ultimo_dicho = texto
            voz.hablar(texto, lambda: app.cola.put(("fin_voz", None)))

        def ejecutar(accion):
            app.acciones_fallidas.append(accion)
            app.propuestas.detectar_carencia_accion(accion)

        app.decir = decir
        app.ejecutar = ejecutar
        app.enviar = lambda texto: app.enviados.append(texto)
        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda texto: conversacion.es_eco(app, texto)
        return app, reloj, voz

    def _drenar_cola(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def test_turno2_no_ignorado_tras_accion_fallida_y_rearme(self):
        app, reloj, voz = self._app()
        turno1 = "Minimaliza las ventanas, por favor."
        respuesta = "Listo, minimalizando ventanas."
        turno2 = "Liris, minimaliza la ventana actual, por favor."

        # Turno 1: transcrito, accion no encontrada, respuesta y fin_voz.
        eventos.atender_evento(app, "oido", turno1)
        self.assertEqual(app.evaluados, [turno1])
        self.assertEqual(app.enviados, [turno1])

        eventos.atender_evento(
            app, "respuesta", (respuesta, "minimizar_ventanas", "neutral"))
        self.assertEqual(app.acciones_fallidas, ["minimizar_ventanas"])
        self.assertEqual(app.carencias, ["minimizar_ventanas"])
        self.assertEqual(app.ultimo_dicho, respuesta)

        voz.terminar(app.cola)
        self._drenar_cola(app)   # fin_voz -> eventos_rearme.rearmar
        reloj.drenar()           # rearme diferido -> micrófono abierto
        self.assertTrue(app.escuchando)

        # Turno 2: con el umbral antiguo se trataba como eco y se ignoraba.
        eventos.atender_evento(app, "oido", turno2)

        self.assertEqual(app.evaluados, [turno1, turno2])
        self.assertEqual(app.enviados, [turno1, turno2])

    def test_eco_real_sigue_descartandose(self):
        app, _reloj, _voz = self._app()
        app.ultimo_dicho = "Listo, minimalizando ventanas."
        eventos.atender_evento(app, "oido", "Listo, minimalizando ventanas.")
        self.assertEqual(app.evaluados, [])
        self.assertEqual(app.enviados, [])


if __name__ == "__main__":
    unittest.main()
