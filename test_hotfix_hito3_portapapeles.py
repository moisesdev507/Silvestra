"""Regresión Hito 3: copiloto de portapapeles bajo demanda, sin inyección global."""
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import conversacion
import eventos
import portapapeles
import respuesta_flujo
from test_hotfix_hito2_telemetria import CaraFalsa, RelojFalso, VozFalsa

TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "app.py", line 10, in main\n'
    "    conexion.iniciar()\n"
    "ValueError: puerto invalido"
)


class TestHotfixHito3Portapapeles(unittest.TestCase):
    def test_deteccion_explicita_y_falsos_positivos(self):
        positivos = (
            "explica lo que copié",
            "Lyris, revisa este error",
            "resume lo que tengo copiado",
            "por qué falla esto",
            "qué dice el portapapeles",
            "corrige este código",
            "traduce lo que copié",
        )
        negativos = (
            "¿qué hora es?", "hola Lyris", "¿cómo va la laptop?",
            "cuéntame un chiste", "revisa cómo va la batería", "",
        )
        for texto in positivos:
            with self.subTest(positivo=texto):
                self.assertTrue(portapapeles.pide_portapapeles(texto))
        for texto in negativos:
            with self.subTest(negativo=texto):
                self.assertFalse(portapapeles.pide_portapapeles(texto))

    def test_recorte_limpio_del_portapapeles(self):
        with patch.object(portapapeles, "_leer_win32", lambda: ("línea de código\n" * 400)):
            recortado = portapapeles.leer_portapapeles(max_chars=120)
        self.assertLessEqual(len(recortado), 120)
        self.assertIn("[recortado]", recortado)
        self.assertNotIn("\n\n\n", recortado)

    def test_traceback_se_inyecta_solo_en_el_turno_actual(self):
        captura = {}

        def falso_llamado(mensajes, al_frase, **_kw):
            captura["mensajes"] = mensajes
            return "El puerto está mal configurado. Cámbialo en settings."

        cerebro = SimpleNamespace(historial=[], app=None,
                                  instrucciones=lambda _t: "Eres Lyris.")
        with patch.object(portapapeles, "_leer_win32", lambda: TRACEBACK), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo", falso_llamado), \
             patch("memoria_adaptadores.atender_turno", lambda *_a: None), \
             patch.object(respuesta_flujo.cerebro_enrutador,
                          "verificar_pro_disponible", lambda: False):
            respuesta, accion, _emo = respuesta_flujo.responder_flujo(
                cerebro, "revisa este error", None)

        self.assertEqual(respuesta, "El puerto está mal configurado. Cámbialo en settings.")
        self.assertIsNone(accion)
        mensajes = captura["mensajes"]
        bloque = mensajes[1]["content"]
        self.assertTrue(bloque.startswith("[PORTAPAPELES DEL USUARIO]"))
        self.assertIn("ValueError: puerto invalido", bloque)
        self.assertIn("[/PORTAPAPELES]", bloque)
        self.assertIn("1-3 frases", bloque)

        # Un turno normal no debe arrastrar el bloque del portapapeles.
        captura.clear()
        with patch.object(portapapeles, "_leer_win32", lambda: TRACEBACK), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo", falso_llamado), \
             patch("memoria_adaptadores.atender_turno", lambda *_a: None), \
             patch.object(respuesta_flujo.cerebro_enrutador,
                          "verificar_pro_disponible", lambda: False):
            respuesta_flujo.responder_flujo(cerebro, "hola Lyris", None)
        self.assertFalse(any("PORTAPAPELES DEL USUARIO" in str(m.get("content", ""))
                             for m in captura["mensajes"]))

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
        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda _texto: False
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)), emocion=kw.get("emocion"))
        return app, reloj, voz, cara

    def test_portapapeles_vacio_responde_local_y_vuelve_a_amarillo(self):
        app, reloj, voz, cara = self._app()
        cerebro = SimpleNamespace(historial=[], app=app,
                                  instrucciones=lambda _t: "Eres Lyris.")
        frases = []

        def al_frase(frase):
            frases.append(frase)
            app.cola.put(("frase", frase))

        with patch.object(portapapeles, "_leer_win32", lambda: ""), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo",
                          side_effect=AssertionError("No debe llamar al LLM")), \
             patch.object(respuesta_flujo.cerebro_enrutador, "completar_pro_flujo",
                          side_effect=AssertionError("No debe llamar al LLM")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, "explica lo que copié", al_frase)
            self.assertEqual(resultado[0], portapapeles.SIN_TEXTO)
            self.assertIsNone(resultado[1])
            app.cola.put(("respuesta", resultado))
            while not app.cola.empty():
                tipo, valor = app.cola.get_nowait()
                eventos.atender_evento(app, tipo, valor)

        self.assertEqual(frases, [portapapeles.SIN_TEXTO])
        self.assertEqual(voz.frases, [portapapeles.SIN_TEXTO])
        self.assertTrue(voz.ocupada())
        voz.terminar()
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)
        reloj.drenar()

        self.assertFalse(voz.ocupada())
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)


if __name__ == "__main__":
    unittest.main()
