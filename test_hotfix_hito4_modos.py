"""Regresión Hito 4: modos compuestos en local y telemetría por palabra exacta."""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import eventos
import modos_rutina
import modos_sistema
import respuesta_flujo
import telemetria
from test_hotfix_hito2_telemetria import CaraFalsa, RelojFalso, VozFalsa, SIS, datos_fijos


class TestHotfixHito4Modos(unittest.TestCase):
    def _activar_falso(self, app):
        def activar(aplicacion, modo, origen="voz"):
            if aplicacion is not None:
                aplicacion.modo_activo = modo
            return True, f"Modo {modo} activado.", None
        return patch.object(modos_sistema, "activar_modo", activar)

    def test_activacion_de_los_tres_modos(self):
        casos = (
            ("modo código", "codigo", "programacion", "Modo código activado"),
            ("activa modo programar", "codigo", "programacion", "Modo código activado"),
            ("modo estudio", "estudio", "estudio", "Modo estudio activado"),
            ("modo descanso", "descanso", "noche", "Modo descanso activado"),
            ("modo relax", "descanso", "noche", "Modo descanso activado"),
        )
        for texto, esperado, sistema, frase in casos:
            with self.subTest(texto=texto):
                self.assertEqual(modos_rutina.detectar_modo(texto), esperado)
                app = SimpleNamespace()
                with self._activar_falso(app), patch(
                        "control_pc.resolver_ruta_vscode", lambda: "code.exe"):
                    resp = modos_rutina.detectar_y_ejecutar_modo(texto, app=app)
                self.assertIsInstance(resp, str)
                self.assertIn(frase, resp)
                self.assertEqual(app.modo_activo, sistema)

    def test_fallo_parcial_de_paso_opcional_no_tumba_la_respuesta(self):
        app = SimpleNamespace()
        with self._activar_falso(app), patch.dict(
                modos_rutina._OPERACIONES,
                {"editor": lambda _ctx: (_ for _ in ()).throw(RuntimeError("sin VS Code"))}):
            resp = modos_rutina.detectar_y_ejecutar_modo("modo código", app=app)
        self.assertIn("Modo código activado", resp)
        self.assertEqual(app.modo_activo, "programacion")

        with patch.dict(
                modos_rutina._OPERACIONES,
                {"activar": lambda _ctx: (_ for _ in ()).throw(RuntimeError("estado"))}):
            resp = modos_rutina.detectar_y_ejecutar_modo("modo descanso", app=app)
        self.assertIn("No pude activar el modo descanso", resp)

    def test_preguntas_generales_no_activan_modo(self):
        for texto in ("¿qué es el modo oscuro?", "explica el modo estudio",
                      "¿cómo va la laptop?", "hola Lyris", "pendientes de programación"):
            with self.subTest(texto=texto):
                self.assertIsNone(modos_rutina.detectar_modo(texto))
                with patch.object(modos_sistema, "activar_modo",
                                  side_effect=AssertionError("No debe activar")):
                    self.assertIsNone(modos_rutina.detectar_y_ejecutar_modo(texto))

    def test_programacion_no_dispara_telemetria_de_ram(self):
        with datos_fijos(), patch.object(
                telemetria, "estado_sistema", side_effect=AssertionError("No debe leer RAM")):
            for texto in ("pendientes de programación", "activa modo programar",
                          "modo código"):
                with self.subTest(texto=texto):
                    self.assertIsNone(telemetria.responder_telemetria(texto))
        with datos_fijos():
            self.assertEqual(telemetria.responder_telemetria("cuánta RAM estoy usando"),
                             SIS["texto"])
            self.assertEqual(telemetria.responder_telemetria("cómo está la CPU"),
                             SIS["texto"])

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
        app.escuchar = lambda: None
        app._dejar_de_escuchar = lambda: None
        app._es_eco = lambda _texto: False
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)), emocion=kw.get("emocion"))
        return app, reloj, voz, cara

    def test_flujo_real_una_voz_y_rearme_a_amarillo(self):
        import conversacion
        app, reloj, voz, cara = self._app()
        app.escuchar = lambda: conversacion.escuchar(app)
        cerebro = SimpleNamespace(historial=[], app=app,
                                  instrucciones=lambda _t: "Eres Lyris.")
        frases = []

        def al_frase(frase):
            frases.append(frase)
            app.cola.put(("frase", frase))

        with self._activar_falso(app), patch(
                "memoria_adaptadores.atender_turno", lambda *_a: None), patch.object(
                respuesta_flujo.proveedores, "completar_flujo",
                side_effect=AssertionError("No debe llamar al LLM")), patch.object(
                respuesta_flujo.cerebro_enrutador, "completar_pro_flujo",
                side_effect=AssertionError("No debe llamar al LLM")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, "modo descanso", al_frase)
            self.assertTrue(resultado[0].startswith("Modo descanso activado"))
            self.assertIsNone(resultado[1])
            app.cola.put(("respuesta", resultado))
            while not app.cola.empty():
                tipo, valor = app.cola.get_nowait()
                eventos.atender_evento(app, tipo, valor)

        self.assertEqual(len(voz.frases), 1)
        self.assertEqual(frases, [resultado[0]])
        self.assertTrue(voz.ocupada())
        voz.terminar()
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)
        reloj.drenar()

        self.assertFalse(voz.ocupada())
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)
        self.assertEqual(app.modo_activo, "noche")


if __name__ == "__main__":
    unittest.main()
