"""Regresión: apertura local de apps conocidas, sin LLM y con una sola voz."""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import acciones
import control_laptop
import conversacion
import eventos
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

    def agregar(self, frase, emocion=None):
        self.voz.frases.append(frase)
        self.voz.ocupada_estado = True
        self.voz.fin_pendiente = self.fin

    def cerrar(self):
        pass


class VozFalsa:
    def __init__(self):
        self.frases = []
        self.ocupada_estado = False
        self.fin_pendiente = None

    def ocupada(self):
        return self.ocupada_estado

    def flujo(self, fin=None, **_kw):
        return FlujoFalso(self, fin)

    def hablar(self, texto, fin=None, emocion=None):
        flujo = self.flujo(fin)
        flujo.agregar(texto)
        flujo.cerrar()

    def terminar(self):
        self.ocupada_estado = False
        fin, self.fin_pendiente = self.fin_pendiente, None
        if fin is not None:
            fin()


class CaraFalsa:
    def __init__(self, reloj):
        self.root = reloj
        self.escuchando = False
        self.burbujas = []

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)

    def decir(self, texto, _ms=None, emocion=None):
        self.burbujas.append(texto)

    def fijar_emocion(self, _emocion):
        pass

    def programar_retorno_neutral(self, _ms=None):
        pass


class HiloFalso:
    tareas = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        HiloFalso.tareas.append((self.target, self.args))


class PopenFalso:
    llamadas = []

    def __init__(self, args, **_kw):
        PopenFalso.llamadas.append(list(args))


class TestAbrirAppLocal(unittest.TestCase):
    def setUp(self):
        parche = patch.object(conversacion, "grabar", lambda app, generacion=None: None)
        parche.start()
        self.addCleanup(parche.stop)
        HiloFalso.tareas.clear()
        PopenFalso.llamadas.clear()

    def _app(self):
        reloj = RelojFalso()
        voz = VozFalsa()
        cara = CaraFalsa(reloj)
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False, flujo=None,
            texto_flujo="", _flujo_cerrado=False, voz=voz, cara=cara,
            musica_activa=False, pendiente_descanso=False, escenario=None,
            _t_accion_llm=0, ultimo_dicho="", silencios=0, _ecosistema_origen=None,
            t_fin_habla=None, metricas_turno=None, t_inicio_texto=None,
        )

        def ejecutar(linea):
            nombre, arg = acciones.interpretar(linea)
            if nombre:
                acciones.ejecutar(nombre, arg)

        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda _texto: False
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)), emocion=kw.get("emocion"))
        app.ejecutar = ejecutar
        return app, reloj, voz, cara

    def _drenar(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def _turno(self, app, texto):
        cerebro = SimpleNamespace(historial=[], app=app)
        with patch.object(control_laptop, "threading", SimpleNamespace(Thread=HiloFalso)), \
             patch.object(control_laptop.subprocess, "Popen", PopenFalso), \
             patch.object(control_laptop.control_seguridad, "registrar_log", lambda *a, **k: None), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo",
                          side_effect=AssertionError("Se llamó al LLM")), \
             patch.object(respuesta_flujo.cerebro_enrutador, "completar_pro_flujo",
                          side_effect=AssertionError("Se llamó al LLM")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, texto, lambda frase: app.cola.put(("frase", frase)))
            app.cola.put(("respuesta", resultado))
            self._drenar(app)
            for objetivo, args in list(HiloFalso.tareas):
                objetivo(*args)
            HiloFalso.tareas.clear()
            self._drenar(app)
        return resultado

    def test_abrir_visual_code_resuelve_localmente(self):
        app, reloj, voz, cara = self._app()

        resultado = self._turno(app, "Lyris, ¿puedes abrir Visual Code, por favor?")

        self.assertEqual(resultado[1], "abrir_app_local | visual studio code")
        self.assertEqual(voz.frases, ["Abriendo visual studio code."])
        self.assertEqual(PopenFalso.llamadas, [["code.cmd"]])
        self.assertTrue(voz.ocupada())

        voz.terminar()
        self._drenar(app)
        reloj.drenar()

        self.assertFalse(voz.ocupada())
        self.assertIsNone(app.flujo)
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)

    def test_abrir_visual_studio_code_directo(self):
        app, _reloj, voz, _cara = self._app()

        resultado = self._turno(app, "abre Visual Studio Code")

        self.assertEqual(resultado[1], "abrir_app_local | visual studio code")
        self.assertEqual(voz.frases, ["Abriendo visual studio code."])
        self.assertEqual(PopenFalso.llamadas, [["code.cmd"]])

    def test_negaciones_y_charla_no_se_interceptan(self):
        for texto in (
            "no abras Visual Studio Code",
            "no quiero abrir Spotify",
            "ayúdame con Visual Studio Code",
            "¿cómo uso Visual Studio Code?",
            "¿qué es Chrome?",
            "explícame cómo funciona Edge",
        ):
            with self.subTest(texto=texto):
                self.assertIsNone(acciones.extraer_app_abrir(texto))

    def test_variantes_y_apps_no_soportadas(self):
        casos = {
            "abre Visual Estilo Code": "visual studio code",
            "abre VS Code": "visual studio code",
            "ábreme el Chrome": "chrome",
            "abre Microsoft Edge": "edge",
            "abre Spotify": "spotify",
            "abre el bloc de notas": "bloc de notas",
            "abre la calculadora": "calculadora",
            "abre YouTube": None,
            "abre la página de GitHub": None,
            "abre Chrome y Spotify": None,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(acciones.extraer_app_abrir(texto), esperado)

    def test_no_hay_doble_frase_de_confirmacion(self):
        app, _reloj, voz, _cara = self._app()
        self._turno(app, "abre Spotify")
        self.assertEqual(voz.frases, ["Abriendo spotify."])
        self.assertEqual(len(PopenFalso.llamadas), 1)


if __name__ == "__main__":
    unittest.main()
