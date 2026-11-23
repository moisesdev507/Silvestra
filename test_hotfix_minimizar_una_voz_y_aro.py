"""Regresión: una sola confirmación y aro amarillo tras minimizar ventanas.

Reproduce el flujo real: respuesta_flujo (interceptor) -> eventos ('frase' y
'respuesta') -> control_laptop.multimedia (hilo) -> eventos ('fin_voz') ->
eventos_rearme (temporizador de la cara).
"""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import control_laptop
import conversacion
import eventos
import eventos_rearme
import respuesta_flujo


class RelojFalso:
    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=40):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class FlujoFalso:
    def __init__(self, voz, fin):
        self.voz, self.fin = voz, fin

    def agregar(self, texto, emocion=None):
        self.voz.frases.append(texto)
        self.voz.ocupada_estado = True
        self.voz.fin_pendiente = self.fin

    def cerrar(self):
        pass


class VozFalsa:
    def __init__(self):
        self.ocupada_estado = False
        self.frases = []
        self.fin_pendiente = None

    def ocupada(self):
        return self.ocupada_estado

    def flujo(self, callback, **_kw):
        return FlujoFalso(self, callback)

    def terminar(self):
        self.ocupada_estado = False
        fin, self.fin_pendiente = self.fin_pendiente, None
        if fin is not None:
            fin()


class HiloFalso:
    """Captura el hilo de control_laptop para ejecutarlo tras la brecha real."""
    tareas = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        HiloFalso.tareas.append((self.target, self.args))


class User32Falso:
    def __init__(self):
        self.teclas = []

    def keybd_event(self, *args):
        self.teclas.append(args)

    def LockWorkStation(self):
        pass


class TestMinimizarUnaVozYaro(unittest.TestCase):
    def _app(self):
        HiloFalso.tareas.clear()
        reloj = RelojFalso()
        voz = VozFalsa()
        escuchadas = []
        cara = SimpleNamespace(
            root=reloj, escuchando=False, pensando=False, hablando=False,
            decir=lambda *_a, **_k: None,
            fijar_emocion=lambda *_a: None,
            programar_retorno_neutral=lambda *_a: None,
        )
        cara.poner_escuchando = lambda valor: setattr(cara, "escuchando", bool(valor))
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False, flujo=None,
            voz=voz, cara=cara, musica_activa=False, pendiente_descanso=False,
            escenario=None, _t_accion_llm=0, ultimo_dicho="", escuchadas=escuchadas,
        )

        def escuchar():
            escuchadas.append("libre" if not voz.ocupada() else "durante_voz")
            conversacion.escuchar(app)

        app.escuchar = escuchar
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda _texto: False
        app.decir = lambda texto, **_kw: None
        app.ejecutar = lambda _accion: self._lanzar_accion(app)
        return app, reloj, voz, cara, escuchadas

    def _lanzar_accion(self, app):
        user32 = User32Falso()
        with patch.object(control_laptop, "threading", SimpleNamespace(Thread=HiloFalso)), \
             patch.object(control_laptop, "ctypes",
                          SimpleNamespace(windll=SimpleNamespace(user32=user32))), \
             patch.object(control_laptop.control_seguridad, "registrar_log", lambda *a: None):
            control_laptop.multimedia(app, "minimizar")

    def _drenar(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def _turno_minimizar(self, app):
        """Ejecuta el interceptor real y encola la respuesta como conversacion.py."""
        cerebro = SimpleNamespace(historial=[])
        resultado = respuesta_flujo.responder_flujo(
            cerebro, "Lyris, minimaliza la ventana actual, por favor.",
            lambda frase: app.cola.put(("frase", frase)))
        app.cola.put(("respuesta", resultado))
        self._drenar(app)
        return resultado

    def test_una_sola_voz_y_rearme_amarillo_tras_minimizar(self):
        app, reloj, voz, cara, escuchadas = self._app()

        resultado = self._turno_minimizar(app)
        self.assertEqual(resultado[1], "minimizar_todo")
        self.assertEqual(voz.frases, ["Minimizando la ventana."])
        self.assertEqual(len(HiloFalso.tareas), 1)

        # Termina la primera frase; el rearme espera a que la voz esté libre.
        voz.terminar()
        self._drenar(app)
        self.assertEqual(escuchadas, [])

        # Transcurren los ~3.7 s reales y termina la acción local (hilo).
        objetivo, args = HiloFalso.tareas.pop(0)
        objetivo(*args)
        self._drenar(app)

        # El micrófono se rearma solo con la voz libre y el aro vuelve a amarillo.
        reloj.drenar()
        self.assertEqual(voz.frases, ["Minimizando la ventana."])
        self.assertEqual(escuchadas, ["libre"])
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)

    def test_accion_rearma_aun_sin_fin_voz_del_flujo(self):
        app, reloj, voz, _cara, escuchadas = self._app()
        self._turno_minimizar(app)

        # La voz ya terminó pero el callback fin_voz se perdió (flujo cancelado).
        voz.ocupada_estado = False
        voz.fin_pendiente = None
        objetivo, args = HiloFalso.tareas.pop(0)
        objetivo(*args)
        self._drenar(app)
        reloj.drenar()

        self.assertEqual(voz.frases, ["Minimizando la ventana."])
        self.assertEqual(escuchadas, ["libre"])
        self.assertTrue(app.escuchando)

    def test_rearmar_con_microfono_abierto_curaro_desincronizado(self):
        app, _reloj, _voz, cara, _escuchadas = self._app()
        conversacion.escuchar(app)
        cara.escuchando = False  # aro azul pese a que el micrófono está abierto

        eventos_rearme.rearmar(app)

        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)


if __name__ == "__main__":
    unittest.main()
