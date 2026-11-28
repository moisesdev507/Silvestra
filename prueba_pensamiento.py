"""Pruebas unitarias para pensamiento_interno.py y consolidador_diario.py.

Valida el motor de flujo de consciencia interno, límites de memoria, cooldown
proactivo, tolerancia a fallos y consolidación de sesiones de diario con mocks.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from consolidador_diario import ConsolidarSesion
from diario_kaya import DiarioKaya
from homeostasis import Homeostasis
from pensamiento_interno import MotorPensamiento, obtener_titulo_ventana_activa


class MockLLM:
    """Mock flexible para respuestas de modelos LLM."""

    def __init__(self, respuestas=None, excepcion=None):
        self.respuestas = list(respuestas) if respuestas else []
        self.excepcion = excepcion
        self.llamadas: list[str] = []

    def __call__(self, prompt: str):
        self.llamadas.append(prompt)
        if self.excepcion:
            raise self.excepcion
        if self.respuestas:
            return self.respuestas.pop(0)
        return json.dumps({
            "pensamiento": "Pensamiento de prueba",
            "quiere_hablar": False,
            "frase_iniciativa": "",
        })


class TestPensamientoYConsolidacion(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_db = os.path.join(self.temp_dir.name, "diario_test.db")
        self.ruta_estado = os.path.join(self.temp_dir.name, "estado.json")
        self.diario = DiarioKaya(ruta_db=self.ruta_db)
        self.homeostasis = Homeostasis(ruta_archivo=self.ruta_estado)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_cola_circular_limite_cinco(self) -> None:
        respuestas = [
            json.dumps({"pensamiento": f"Pensamiento #{i}", "quiere_hablar": False})
            for i in range(1, 8)
        ]
        mock_llm = MockLLM(respuestas=respuestas)
        motor = MotorPensamiento(
            homeostasis=self.homeostasis,
            diario=self.diario,
            cliente_llm=mock_llm,
        )

        for _ in range(7):
            resultado = motor.pensar_ahora()
            self.assertIsNotNone(resultado)

        pensamientos = motor.obtener_pensamientos()
        self.assertEqual(len(pensamientos), 5)
        self.assertEqual(pensamientos[0], "Pensamiento #3")
        self.assertEqual(pensamientos[-1], "Pensamiento #7")

    def test_construir_bloque_pensamientos(self) -> None:
        motor = MotorPensamiento(cliente_llm=MockLLM())
        self.assertEqual(motor.construir_bloque_pensamientos(), "")

        motor._cola_pensamientos.append("Observo el código.")
        motor._cola_pensamientos.append("Parece que lloverá pronto.")
        bloque = motor.construir_bloque_pensamientos()

        self.assertIn("[PENSAMIENTOS INTERNOS RECIENTES DE KAYA", bloque)
        self.assertIn("- Observo el código.", bloque)
        self.assertIn("- Parece que lloverá pronto.", bloque)

    def test_pausar_y_reanudar(self) -> None:
        motor = MotorPensamiento(cliente_llm=MockLLM())
        self.assertFalse(motor.esta_pausado())

        motor.pausar()
        self.assertTrue(motor.esta_pausado())

        motor.reanudar()
        self.assertFalse(motor.esta_pausado())

    def test_cooldown_iniciativa(self) -> None:
        iniciativas: list[str] = []

        def _on_iniciativa(frase: str):
            iniciativas.append(frase)

        respuestas = [
            json.dumps({
                "pensamiento": "Veo algo interesante",
                "quiere_hablar": True,
                "frase_iniciativa": "¡Oye, mira esto!",
            }),
            json.dumps({
                "pensamiento": "Sigo pensando en eso",
                "quiere_hablar": True,
                "frase_iniciativa": "¿Te puedo decir algo?",
            }),
        ]
        mock_llm = MockLLM(respuestas=respuestas)
        motor = MotorPensamiento(
            cliente_llm=mock_llm,
            cooldown_proactivo_seg=60.0,
            on_iniciativa=_on_iniciativa,
        )

        # Primer intento: debe disparar
        motor.pensar_ahora()
        self.assertEqual(len(iniciativas), 1)
        self.assertEqual(iniciativas[0], "¡Oye, mira esto!")

        # Segundo intento inmediato: bloqueado por cooldown
        motor.pensar_ahora()
        self.assertEqual(len(iniciativas), 1)

        # Simular paso del tiempo para expirar el cooldown
        motor._ultimo_intento_iniciativa -= 65.0
        mock_llm.respuestas.append(
            json.dumps({
                "pensamiento": "Tiempo transcurrido",
                "quiere_hablar": True,
                "frase_iniciativa": "Ha pasado un buen rato.",
            })
        )
        motor.pensar_ahora()
        self.assertEqual(len(iniciativas), 2)
        self.assertEqual(iniciativas[1], "Ha pasado un buen rato.")

    def test_tolerancia_json_malformado_y_errores(self) -> None:
        # Respuesta no JSON
        motor_roto = MotorPensamiento(cliente_llm=lambda p: "esto no es json")
        self.assertIsNone(motor_roto.pensar_ahora())
        self.assertEqual(len(motor_roto.obtener_pensamientos()), 0)

        # Excepción en cliente LLM
        motor_ex = MotorPensamiento(
            cliente_llm=MockLLM(excepcion=RuntimeError("Fallo de red simulado"))
        )
        self.assertIsNone(motor_ex.pensar_ahora())
        self.assertEqual(len(motor_ex.obtener_pensamientos()), 0)

    def test_consolidar_sesion_corta_se_ignora(self) -> None:
        mock_llm = MockLLM()
        consolidador = ConsolidarSesion(diario=self.diario, cliente_llm=mock_llm)

        # Solo un turno
        turnos_cortos = [{"rol": "user", "texto": "Hola Kaya"}]
        resultado = consolidador.consolidar(turnos_cortos)
        self.assertFalse(resultado)
        self.assertEqual(len(mock_llm.llamadas), 0)
        self.assertEqual(len(self.diario.obtener_recuerdos_recientes()), 0)

    def test_consolidar_sesion_valida(self) -> None:
        respuesta_llm = json.dumps({
            "reflexion": "Hoy estuvimos trabajando en la arquitectura de consciencia. Me sentí muy enfocada.",
            "tema": "programación",
            "rasgos": {
                "lenguaje_favorito": "Python",
                "estilo_trabajo": "modular",
            },
        })
        mock_llm = MockLLM(respuestas=[respuesta_llm])
        consolidador = ConsolidarSesion(diario=self.diario, cliente_llm=mock_llm)

        turnos = [
            {"rol": "user", "texto": "Hola Kaya, ¿cómo estás hoy?"},
            {"rol": "asistente", "texto": "Hola, me siento muy bien y lista para ayudarte."},
            {"rol": "user", "texto": "Vamos a implementar la fase 2 de subjetividad en Python."},
            {"rol": "asistente", "texto": "Excelente idea, mantendremos todo modular."},
        ]

        resultado = consolidador.consolidar(turnos, estado_animo="curiosa")
        self.assertTrue(resultado)

        recuerdos = self.diario.obtener_recuerdos_recientes(limite=5)
        self.assertEqual(len(recuerdos), 1)
        self.assertEqual(recuerdos[0]["tema_principal"], "programación")
        self.assertIn("arquitectura de consciencia", recuerdos[0]["reflexion_primera_persona"])

        rasgos = self.diario.obtener_rasgos()
        self.assertEqual(rasgos.get("lenguaje_favorito"), "Python")
        self.assertEqual(rasgos.get("estilo_trabajo"), "modular")

    def test_consolidar_error_llm(self) -> None:
        mock_llm = MockLLM(respuestas=["respuesta rota sin json"])
        consolidador = ConsolidarSesion(diario=self.diario, cliente_llm=mock_llm)

        turnos = [
            {"rol": "user", "texto": "Hola Kaya"},
            {"rol": "asistente", "texto": "Hola usuario"},
            {"rol": "user", "texto": "Seguimos hablando"},
            {"rol": "asistente", "texto": "Claro que sí"},
        ]
        self.assertFalse(consolidador.consolidar(turnos))

    def test_obtener_titulo_ventana_activa(self) -> None:
        titulo = obtener_titulo_ventana_activa()
        self.assertIsInstance(titulo, str)
        self.assertTrue(len(titulo) > 0)


if __name__ == "__main__":
    unittest.main()
