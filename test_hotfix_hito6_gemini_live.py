"""Regresión Hito 6: Gemini Live con acciones seguras y caída por 429."""
import asyncio
import contextlib
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import acciones
import config
import gemini_live
import respuesta_flujo


class WsFalso:
    """WebSocket mínimo: devuelve mensajes prefijados y registra lo enviado."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.enviados = []
        self.cerrado = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.cerrado = True

    async def send(self, dato):
        self.enviados.append(json.loads(dato))

    async def recv(self):
        if not self.respuestas:
            raise asyncio.TimeoutError()
        return json.dumps(self.respuestas.pop(0))


class TestHotfixHito6GeminiLive(unittest.TestCase):
    def setUp(self):
        gemini_live.reiniciar()

    def _activo(self, clave="clave-secreta"):
        return (
            patch.object(config, "GEMINI_LIVE_ACTIVO", True, create=True),
            patch.dict(os.environ, {
                "GEMINI_API_KEY": clave, "GOOGLE_API_KEY": "",
                "LYRIS_LIVE_CHAT": "0",
            }),
        )

    def test_herramientas_solo_catalogo_y_delegan_en_acciones(self):
        vistos = []

        def buscar(arg=None):
            vistos.append(arg)
            return True, "Listo."

        with patch.dict(acciones.ACCIONES,
                        {"buscar": (buscar, True, "busca en Google")}, clear=True), \
             patch.dict(acciones.VIVAS, {}, clear=True):
            declaradas = gemini_live.declarar_herramientas()
            self.assertEqual(
                [f["name"] for f in declaradas[0]["function_declarations"]], ["buscar"])
            self.assertEqual(gemini_live.ejecutar_herramienta_live(" Buscar ", "arroz"),
                             (True, "Listo."))
            self.assertEqual(vistos, ["arroz"])
            self.assertEqual(gemini_live.ejecutar_herramienta_live("borrar_todo"),
                             (False, "Acción no permitida."))

    def test_turno_live_streaming_y_herramienta_sin_duplicar_accion(self):
        respuestas = [
            {"server_content": {"model_turn": {"parts": [{"text": "Abriendo "}]}}},
            {"server_content": {"model_turn": {"parts": [{
                "function_call": {"id": "c1", "name": "buscar",
                                  "args": {"arg": "arroz"}}}]}}},
            {"server_content": {"model_turn": {"parts": [{"text": "listo"}]},
                                "turn_complete": True}},
        ]
        ws = WsFalso(respuestas)
        frases = []
        llamadas = []

        def herramienta(nombre, arg=None):
            llamadas.append((nombre, arg))
            return True, "hecho"

        activo = self._activo()
        with activo[0], activo[1], \
             patch("websockets.connect", lambda *_a, **_k: ws), \
             patch.object(gemini_live, "ejecutar_herramienta_live", herramienta):
            resultado = gemini_live.turno_live(
                texto="busca arroz", al_frase=frases.append)

        self.assertEqual(resultado, ("Abriendo listo", None, "neutral"))
        self.assertEqual(frases, ["Abriendo ", "listo"])
        self.assertEqual(llamadas, [("buscar", "arroz")])
        self.assertEqual(ws.enviados[0]["setup"]["model"], gemini_live._MODELO)
        self.assertTrue(any("tool_response" in m for m in ws.enviados))
        self.assertTrue(ws.cerrado)
        self.assertNotIn("clave-secreta", json.dumps(ws.enviados))

    def test_429_activa_enfriamiento_y_evita_reintentos(self):
        intentos = []

        def conectar(*_args, **_kwargs):
            intentos.append(1)
            raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED")

        activo = self._activo()
        salida = io.StringIO()
        with activo[0], activo[1], patch("websockets.connect", conectar), \
             contextlib.redirect_stdout(salida):
            self.assertIsNone(gemini_live.turno_live(texto="hola"))
            self.assertTrue(gemini_live.enfriado())
            self.assertIn("429", gemini_live.motivo_enfriamiento())
            self.assertIsNone(gemini_live.turno_live(texto="hola"))

        self.assertEqual(len(intentos), 1)
        self.assertNotIn("clave-secreta", salida.getvalue())

    def test_sin_flag_o_sin_clave_no_intenta_conectar(self):
        def prohibido(*_args, **_kwargs):
            raise AssertionError("No debe abrir WebSocket")

        with patch.object(config, "GEMINI_LIVE_ACTIVO", False, create=True), \
             patch.dict(os.environ, {"LYRIS_LIVE_CHAT": "0", "GEMINI_API_KEY": "",
                                     "GOOGLE_API_KEY": ""}), \
             patch("websockets.connect", prohibido):
            self.assertIsNone(gemini_live.turno_live(texto="hola"))

        with patch.object(config, "GEMINI_LIVE_ACTIVO", True, create=True), \
             patch.dict(os.environ, {"LYRIS_LIVE_CHAT": "0", "GEMINI_API_KEY": "",
                                     "GOOGLE_API_KEY": ""}), \
             patch("websockets.connect", prohibido):
            self.assertIsNone(gemini_live.turno_live(texto="hola"))
        self.assertFalse(gemini_live.enfriado())

    def test_429_cae_al_flujo_estandar_de_respuesta_flujo(self):
        intentos = []

        def conectar(*_args, **_kwargs):
            intentos.append(1)
            raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED")

        cerebro = SimpleNamespace(
            historial=[], app=None, instrucciones=lambda _texto: "Eres Lyris.")
        activo = self._activo()
        with activo[0], activo[1], patch("websockets.connect", conectar), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo",
                          lambda *_a, **_k: "respuesta estandar"), \
             patch.object(respuesta_flujo.cerebro_enrutador,
                          "verificar_pro_disponible", lambda: False), \
             patch("memoria_adaptadores.atender_turno", lambda *_a: None):
            resultado = respuesta_flujo.responder_flujo(cerebro, "hola Lyris", None)

        self.assertEqual(resultado[0], "respuesta estandar")
        self.assertIsNone(resultado[1])
        self.assertEqual(len(intentos), 1)
        self.assertTrue(gemini_live.enfriado())
        self.assertEqual(cerebro.historial[-1]["content"], "respuesta estandar")


if __name__ == "__main__":
    unittest.main()
