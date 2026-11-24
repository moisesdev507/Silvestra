"""Regresión: ninguna respuesta del cerebro debe dejar a Lyris muda."""
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro_parser as cp
import conversacion
import eventos
import voz_stream


class FlujoFalso:
    def __init__(self, voz, al_terminar=None, **opciones):
        self.voz = voz
        self.al_terminar = al_terminar
        self.opciones = opciones
        self.frases = []
        self.cerrado = False

    def agregar(self, frase, emocion=None):
        self.frases.append(frase)

    def cerrar(self):
        self.cerrado = True


class VozFalsa:
    def __init__(self):
        self.flujos = []
        self.hablado = []

    def flujo(self, al_terminar=None, **opciones):
        flujo = FlujoFalso(self, al_terminar, **opciones)
        self.flujos.append(flujo)
        return flujo

    def hablar(self, texto, al_terminar=None, emocion=None):
        self.hablado.append(texto)
        flujo = self.flujo(al_terminar, emocion=emocion)
        flujo.agregar(texto, emocion=emocion)
        flujo.cerrar()
        return flujo

    def ocupada(self):
        return False


class CaraFalsa:
    def __init__(self):
        self.burbujas = []
        self.emocion = None

    def decir(self, texto, _ms=None, emocion=None):
        self.burbujas.append(texto)

    def fijar_emocion(self, emocion):
        self.emocion = emocion

    def programar_retorno_neutral(self, _ms=None):
        pass

    def poner_escuchando(self, _valor):
        pass

    def asentir(self, _valor=None):
        pass


class TestSalidaVocalGarantizada(unittest.TestCase):
    def setUp(self):
        for objetivo, nombre in ((eventos.sonidos_ui, "reproducir"),
                                 (conversacion, "grabar")):
            parche = patch.object(objetivo, nombre, lambda *a, **k: None)
            parche.start()
            self.addCleanup(parche.stop)

    def _app(self, ejecutar=None):
        voz, cara = VozFalsa(), CaraFalsa()
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False,
            flujo=None, texto_flujo="", _flujo_cerrado=False,
            _fragmentos_voz=False, _t_accion_llm=0, _ecosistema_origen=None,
            voz=voz, cara=cara, musica_activa=False, musica=False,
            pendiente_descanso=False, escenario=None, silencios=0,
            ultimo_dicho="", t_fin_habla=None, metricas_turno=None,
            t_inicio_texto=None, origen_entrada_actual=None,
        )
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)),
            emocion=kw.get("emocion"))
        app.ejecutar = ejecutar or (lambda _accion: None)
        app.escuchar = lambda: None
        app._dejar_de_escuchar = lambda: None
        app._es_eco = lambda _texto: False
        app.enviar = lambda _texto: None
        return app, voz, cara

    def _drenar(self, app):
        vistos = []
        while not app.cola.empty():
            evento = app.cola.get_nowait()
            vistos.append(evento)
            eventos.atender_evento(app, evento[0], evento[1])
        return vistos

    def test_respuesta_normal_sintetiza_voz(self):
        app, voz, cara = self._app()
        texto = "Hola Moisés, todo listo por aquí."
        app.cola.put(("respuesta", (texto, None, "neutral")))
        self._drenar(app)
        self.assertEqual(voz.hablado, [texto])
        self.assertEqual([f.frases for f in voz.flujos], [[texto]])
        self.assertTrue(all(f.cerrado for f in voz.flujos))
        self.assertEqual(cara.burbujas, [texto])
        self.assertTrue(app._fragmentos_voz)

    def test_marca_de_fragmentos_obsoleta_no_bloquea_voz_directa(self):
        app, voz, _cara = self._app()
        app._fragmentos_voz = True
        texto = "Respuesta posterior sin flujo activo."
        app.cola.put(("respuesta", (texto, None, "neutral")))
        self._drenar(app)
        self.assertEqual(voz.hablado, [texto])

    def test_think_se_limpia_antes_de_dividir_y_se_habla(self):
        self.assertEqual(
            cp.limpiar_etiquetas("<think>analizo</think> Respuesta corta."),
            "Respuesta corta.")
        app, voz, _cara = self._app()
        crudo = "<think>no hablar esto</think> Sí, Moisés, la entrega es mañana."
        app.cola.put(("frase", crudo))
        app.cola.put(("respuesta", (crudo, None, "neutral")))
        self._drenar(app)
        frases = [f for flujo in voz.flujos for f in flujo.frases]
        self.assertEqual(frases, ["Sí, Moisés, la entrega es mañana."])
        self.assertTrue(all("<think>" not in f for f in frases))
        self.assertEqual(voz.hablado, [])

    def test_think_solo_no_genera_voz_fantasma(self):
        app, voz, _cara = self._app()
        crudo = "<think>solo razonamiento interno</think>"
        app.cola.put(("frase", crudo))
        app.cola.put(("respuesta", (crudo, None, "neutral")))
        vistos = self._drenar(app)
        self.assertEqual(voz.flujos, [])
        self.assertEqual(voz.hablado, [])
        self.assertIn(("fin_voz", None), vistos)

    def test_accion_sin_voz_principal_habla_la_confirmacion(self):
        confirmacion = "Listo, Moisés. Te lo recordaré mañana a las 8:00 p. m."

        def ejecutar(_accion):
            app.cola.put(("hablar", confirmacion))

        app, voz, _cara = self._app(ejecutar=ejecutar)
        crudo = "<think>crear recordatorio</think>"
        app.cola.put(("respuesta", (crudo, "recordatorio | mañana 8pm", "neutral")))
        self._drenar(app)
        self.assertEqual(voz.hablado, [confirmacion])
        self.assertGreater(app._t_accion_llm, 0)

    def test_accion_con_voz_principal_no_duplica_confirmacion(self):
        principal = "Listo, ya quedó anotado."

        def ejecutar(_accion):
            app.cola.put(("hablar", principal))

        app, voz, _cara = self._app(ejecutar=ejecutar)
        app.cola.put(("respuesta", (principal, "anotar | entrega", "neutral")))
        self._drenar(app)
        self.assertEqual(voz.hablado, [principal])

    def test_flujo_vacio_se_cierra_y_se_habla_el_texto_final(self):
        app, voz, _cara = self._app()
        vacio = voz.flujo(lambda: app.cola.put(("fin_voz", None)))
        app.flujo = vacio
        app._flujo_cerrado = True
        texto = "Perdón, repetimos: la entrega es mañana."
        app.cola.put(("respuesta", (texto, None, "neutral")))
        self._drenar(app)
        self.assertTrue(vacio.cerrado)
        self.assertEqual(voz.hablado, [texto])
        self.assertEqual(len(voz.flujos), 2)

    def test_oraciones_limpia_etiquetas_y_think(self):
        self.assertEqual(voz_stream.oraciones("<think>x</think> Vamos allá. Y ya."),
                         ["Vamos allá. Y ya."])


if __name__ == "__main__":
    unittest.main()
