"""Regresión: frase suelta de acción cierra su flujo y rearma aro/escucha.

Reproduce el caso real: el LLM habla, la acción habla después y al terminar
debe quedar ``voz.ocupada()`` en False, con ``fin_voz`` y micrófono rearmado.
"""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import conversacion
import eventos


class RelojFalso:
    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=30):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class FlujoFalso:
    def __init__(self, voz, al_terminar, emocion="neutral", **opciones):
        self.voz, self.al_terminar = voz, al_terminar
        self.emocion, self.opciones = emocion, opciones
        self.frases = []
        self.cerrado = False
        self._activo = False

    def agregar(self, frase, emocion=None):
        self.frases.append(str(frase))
        if not self._activo:
            self._activo = True
            self.voz.activos += 1

    def cerrar(self):
        if self.cerrado:
            return
        self.cerrado = True
        if self._activo:
            self.voz.pendientes.append(self)


class VozFalsa:
    def __init__(self):
        self.flujos = []
        self.pendientes = []
        self.activos = 0

    def ocupada(self):
        return self.activos > 0

    def flujo(self, al_terminar=None, **opciones):
        flujo = FlujoFalso(self, al_terminar, **opciones)
        self.flujos.append(flujo)
        return flujo

    def hablar(self, texto, al_terminar=None, emocion=None):
        flujo = self.flujo(al_terminar, emocion=emocion)
        flujo.agregar(texto)
        flujo.cerrar()

    def terminar(self, flujo):
        if flujo in self.pendientes:
            self.pendientes.remove(flujo)
        if flujo._activo:
            flujo._activo = False
            self.activos = max(0, self.activos - 1)
            if flujo.al_terminar is not None:
                flujo.al_terminar()


class CaraFalsa:
    def __init__(self, reloj):
        self.root = reloj
        self.escuchando = False
        self.llamadas_escucha = []
        self.burbujas = []

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)
        self.llamadas_escucha.append(bool(valor))

    def decir(self, texto, _ms=None, emocion=None):
        self.burbujas.append(str(texto))

    def fijar_emocion(self, _emocion):
        pass

    def programar_retorno_neutral(self, _ms=None):
        pass


class TestAccionesFlujoVozCierre(unittest.TestCase):
    def setUp(self):
        parche = patch.object(conversacion, "grabar", lambda app, generacion=None: None)
        parche.start()
        self.addCleanup(parche.stop)

    def _app(self):
        reloj = RelojFalso()
        voz = VozFalsa()
        cara = CaraFalsa(reloj)
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False,
            flujo=None, texto_flujo="", _flujo_cerrado=False,
            voz=voz, cara=cara, musica_activa=False, musica=False,
            pendiente_descanso=False, escenario=None, silencios=0,
            _t_accion_llm=0, ultimo_dicho="", _ecosistema_origen=None,
            t_fin_habla=None, metricas_turno=None, t_inicio_texto=None,
            origen_entrada_actual=None,
        )

        def ejecutar(accion):
            if str(accion).startswith("abrir"):
                app.cola.put(("frase", "Abriendo Code.exe."))

        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda _texto: False
        app.enviar = lambda _texto: None
        app.ejecutar = ejecutar
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)), emocion=kw.get("emocion"))
        return app, reloj, voz, cara

    def _drenar(self, app):
        vistos = []
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            vistos.append((tipo, valor))
            eventos.atender_evento(app, tipo, valor)
        return vistos

    def test_frase_de_accion_cierra_flujo_y_rearma(self):
        app, reloj, voz, cara = self._app()

        app.cola.put(("frase", "¡Claro que sí, ya te lo abro!"))
        app.cola.put(("respuesta", (
            "¡Claro que sí, ya te lo abro!", "abrir_app | Code.exe", "alegre")))
        vistos = self._drenar(app)

        self.assertEqual([v for t, v in vistos if t == "frase"],
                         ["¡Claro que sí, ya te lo abro!", "Abriendo Code.exe."])
        self.assertEqual(len(voz.flujos), 2)
        self.assertTrue(all(f.cerrado for f in voz.flujos))
        self.assertEqual(voz.flujos[0].frases, ["¡Claro que sí, ya te lo abro!"])
        self.assertEqual(voz.flujos[1].frases, ["Abriendo Code.exe."])
        self.assertTrue(voz.ocupada())
        self.assertFalse(any(t == "fin_voz" for t, _v in vistos))

        voz.terminar(voz.flujos[0])
        self.assertTrue(any(t == "fin_voz" for t, _v in self._drenar(app)))
        self.assertTrue(voz.ocupada())  # la frase de acción sigue sonando

        voz.terminar(voz.flujos[1])
        self.assertTrue(any(t == "fin_voz" for t, _v in self._drenar(app)))
        self.assertFalse(voz.ocupada())
        reloj.drenar()

        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)
        self.assertIn(True, cara.llamadas_escucha)
        self.assertIsNone(app.flujo)

    def test_streaming_dos_frases_no_se_corta(self):
        app, reloj, voz, cara = self._app()

        app.cola.put(("frase", "Primera parte del LLM."))
        app.cola.put(("frase", "Segunda parte del LLM."))
        app.cola.put(("respuesta", ("Respuesta final.", "ninguna", "neutral")))
        vistos = self._drenar(app)

        self.assertEqual([v for t, v in vistos if t == "frase"],
                         ["Primera parte del LLM.", "Segunda parte del LLM."])
        self.assertEqual(len(voz.flujos), 1)
        self.assertEqual(voz.flujos[0].frases,
                         ["Primera parte del LLM.", "Segunda parte del LLM."])
        self.assertTrue(voz.flujos[0].cerrado)

        voz.terminar(voz.flujos[0])
        self.assertTrue(any(t == "fin_voz" for t, _v in self._drenar(app)))
        reloj.drenar()
        self.assertFalse(voz.ocupada())
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)

    def test_hablar_registro_cierra_y_emite_fin_voz(self):
        app, _reloj, voz, _cara = self._app()

        app.cola.put(("hablar_registro", ("Texto de registro.", "")))
        vistos = self._drenar(app)
        self.assertEqual(len(voz.flujos), 1)
        self.assertTrue(voz.flujos[0].cerrado)
        self.assertEqual(voz.flujos[0].frases, ["Texto de registro."])
        self.assertFalse(any(t == "fin_voz" for t, _v in vistos))

        voz.terminar(voz.flujos[0])
        self.assertTrue(any(t == "fin_voz" for t, _v in self._drenar(app)))
        self.assertFalse(voz.ocupada())


if __name__ == "__main__":
    unittest.main()
