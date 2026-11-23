"""Regresión: Lyris nunca debe sintetizar etiquetas internas del LLM.

Cubre la ruta real: ``_respuesta_parcial()`` no emite nada para una etiqueta
sola, ``separar()`` es el fallback usado por el streaming, y ``eventos_voz``
es la última red de seguridad antes de llamar al motor de voz.
"""
import queue
import unittest
from types import SimpleNamespace

import cerebro_parser as cp
import eventos
import eventos_voz


class FlujoFalso:
    def __init__(self, voz, al_terminar):
        self.voz, self.al_terminar = voz, al_terminar
        self.frases = []
        self.cerrado = False

    def agregar(self, frase, emocion=None):
        self.frases.append(str(frase))

    def cerrar(self):
        self.cerrado = True


class VozFalsa:
    def __init__(self):
        self.flujos = []
        self.llamadas_hablar = []

    def flujo(self, al_terminar=None, **_opciones):
        flujo = FlujoFalso(self, al_terminar)
        self.flujos.append(flujo)
        return flujo

    def hablar(self, texto, **_opciones):
        self.llamadas_hablar.append(str(texto))


class CaraFalsa:
    def __init__(self):
        self.emocion = None
        self.burbujas = []

    def fijar_emocion(self, emocion):
        self.emocion = emocion

    def decir(self, texto, _ms=None, emocion=None):
        self.burbujas.append((str(texto), emocion))


class TestNoHablarEtiquetas(unittest.TestCase):
    def _app(self):
        voz, cara = VozFalsa(), CaraFalsa()
        acciones = []
        app = SimpleNamespace(
            cola=queue.Queue(), flujo=None, texto_flujo="", _flujo_cerrado=False,
            voz=voz, cara=cara, escenario=None, musica_activa=False,
            _ecosistema_origen=None, _t_accion_llm=0, ultimo_dicho="",
            t_fin_habla=None, metricas_turno=None, t_inicio_texto=None,
            ejecutar=acciones.append,
        )
        app.decir = lambda texto, **kw: voz.hablar(texto, **kw)
        return app, voz, cara, acciones

    @staticmethod
    def _eventos(app):
        salida = []
        while not app.cola.empty():
            salida.append(app.cola.get_nowait())
        return salida

    def test_etiqueta_sola_no_habla_y_aplica_emocion(self):
        self.assertIsNone(cp._respuesta_parcial("EMOCION: alegre"))
        resp, accion, recuerdo, emo = cp.separar("EMOCION: alegre")
        self.assertEqual((resp, accion, recuerdo, emo), ("", None, None, "alegre"))

        app, voz, cara, _acciones = self._app()
        eventos.atender_evento(app, "emocion", emo)
        self.assertEqual(cara.emocion, "alegre")

        eventos.atender_evento(app, "frase", "EMOCION: alegre")
        eventos.atender_evento(app, "respuesta", (resp, accion, emo))

        self.assertEqual(voz.flujos, [])
        self.assertEqual(voz.llamadas_hablar, [])
        self.assertEqual(cara.burbujas, [])
        self.assertIn(("fin_voz", None), self._eventos(app))

    def test_frase_mixta_con_emocion_solo_habla_texto_limpio(self):
        crudo = "EMOCION: alegre ¡Hola Moisés!"
        resp, accion, _recuerdo, emo = cp.separar(crudo)
        self.assertEqual(resp, "¡Hola Moisés!")
        self.assertEqual(emo, "alegre")

        app, voz, _cara, _acciones = self._app()
        eventos.atender_evento(app, "frase", crudo)
        eventos.atender_evento(app, "respuesta", (resp, accion, emo))

        self.assertEqual([f for flujo in voz.flujos for f in flujo.frases],
                         ["¡Hola Moisés!"])
        self.assertEqual(voz.llamadas_hablar, [])

    def test_frase_mixta_con_accion_solo_habla_texto_limpio(self):
        crudo = "Listo. ACCION: abrir_app"
        resp, accion, _recuerdo, emo = cp.separar(crudo)
        self.assertEqual(resp, "Listo.")
        self.assertEqual(accion, "abrir_app")

        app, voz, _cara, acciones = self._app()
        eventos.atender_evento(app, "frase", crudo)
        eventos.atender_evento(app, "respuesta", (resp, accion, emo))

        self.assertEqual([f for flujo in voz.flujos for f in flujo.frases],
                         ["Listo."])
        self.assertEqual(acciones, ["abrir_app"])
        self.assertEqual(voz.llamadas_hablar, [])

    def test_tildes_respuesta_y_texto_natural(self):
        self.assertEqual(cp.limpiar_etiquetas("EMOCIÓN: neutral"), "")
        self.assertEqual(cp.limpiar_etiquetas("Hola. ACCIÓN: abrir_app"), "Hola.")

        natural = "Qué emoción me da verte"
        self.assertEqual(cp.limpiar_etiquetas(natural), natural)
        self.assertEqual(cp.separar("RESPUESTA: " + natural)[0], natural)

        resp, _accion, _recuerdo, emo = cp.separar(
            "EMOCION: calida RESPUESTA: Dame un segundito.")
        self.assertEqual(resp, "Dame un segundito.")
        self.assertEqual(emo, "calida")

    def test_suelta_solo_etiquetas_no_habla_y_emite_fin_voz(self):
        app, voz, _cara, _acciones = self._app()
        eventos_voz.suelta(app, "ACCION: ninguna RECUERDO: ninguno")

        self.assertEqual(voz.flujos, [])
        self.assertEqual(voz.llamadas_hablar, [])
        self.assertIn(("fin_voz", None), self._eventos(app))


if __name__ == "__main__":
    unittest.main()
