"""Pruebas unitarias para puente_subjetividad.py y mecanismos anti-sordera (v1.1.0).

Valida el orquestador de subjetividad, la construcción del bloque de identidad,
el ciclo reposo-despertar-turnos-cierre, la iniciativa proactiva y el watchdog
de audio/micrófono sin dependencias de red ni hardware real.
"""
from __future__ import annotations

import json
import os
import queue
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from consolidador_diario import ConsolidarSesion
from diario_kaya import DiarioKaya
from homeostasis import Homeostasis
import live_estado
import oido_ws
from pensamiento_interno import MotorPensamiento
from puente_subjetividad import PuenteSubjetividad, reiniciar_puente_para_pruebas


class TestPuenteSubjetividad(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_db = os.path.join(self.temp_dir.name, "diario.db")
        self.ruta_estado = os.path.join(self.temp_dir.name, "estado.json")

        self.homeostasis = Homeostasis(ruta_archivo=self.ruta_estado)
        self.diario = DiarioKaya(ruta_db=self.ruta_db)

        # Mock de cliente LLM que devuelve JSON válido
        self.mock_llm = MagicMock(return_value=json.dumps({
            "pensamiento": "Observo el entorno tranquilamente",
            "quiere_hablar": False,
            "frase_iniciativa": "",
        }))

        self.motor = MotorPensamiento(
            homeostasis=self.homeostasis,
            diario=self.diario,
            cliente_llm=self.mock_llm,
            intervalo_seg=300.0,
            cooldown_proactivo_seg=60.0,
        )
        self.consolidador = ConsolidarSesion(diario=self.diario, cliente_llm=self.mock_llm)

        self.puente = PuenteSubjetividad(
            homeostasis=self.homeostasis,
            diario=self.diario,
            motor_pensamiento=self.motor,
            consolidador=self.consolidador,
            ruta_datos=self.temp_dir.name,
        )
        reiniciar_puente_para_pruebas(self.puente)

    def tearDown(self) -> None:
        reiniciar_puente_para_pruebas(None)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_construir_contexto_identidad_no_servil(self) -> None:
        self.diario.guardar_entrada(
            reflexion="Ayer exploramos código modular y me sentí motivada.",
            estado_animo="enfocada",
            tema="programación",
        )
        self.diario.actualizar_rasgo("estilo", "autónoma y reflexiva")
        self.motor._cola_pensamientos.append("Me agrada la calma de la tarde.")

        bloque = self.puente.construir_contexto_identidad()

        # Debe contener la identidad viva no servil
        self.assertIn("presencia viva, empática y con criterio propio", bloque)
        self.assertIn("No eres una asistente servil", bloque)
        self.assertNotIn("¿en qué puedo ayudarle hoy?", bloque.lower())

        # Debe contener sensación en primera persona sin números crudos
        self.assertIn("[ESTADO FÍSICO Y ANÍMICO ACTUAL]", bloque)
        self.assertNotIn("0.", bloque)  # no debe exponer números 0.85 etc.

        # Debe incluir recuerdos y rasgos de diario
        self.assertIn("Ayer exploramos código modular", bloque)
        self.assertIn("estilo: autónoma y reflexiva", bloque)

        # Debe incluir pensamientos recientes
        self.assertIn("Me agrada la calma de la tarde.", bloque)

    def test_ciclo_reposo_despertar_turnos_y_cierre(self) -> None:
        # 1. Al despertar o hablar: pausa motor y registra interacción
        self.puente.al_despertar_o_hablar()
        self.assertFalse(self.puente._en_reposo)
        self.assertTrue(self.motor.esta_pausado())

        # 2. Registrar turnos conversacionales
        self.puente.registrar_turno("usuario", "Hola Kaya, ¿cómo estás?")
        self.puente.registrar_turno("kaya", "Muy bien, concentrada en nuestro proyecto.")
        self.assertEqual(len(self.puente._turnos_pendientes), 2)

        # 3. Al entrar en reposo: reanuda motor
        self.puente.al_entrar_reposo()
        self.assertTrue(self.puente._en_reposo)
        self.assertFalse(self.motor.esta_pausado())

        # 4. Al cerrar: detiene motor y llama cierre de homeostasis
        self.puente.al_cerrar(timeout_seg=0.5)
        estado = self.homeostasis.obtener_estado()
        self.assertIn("ultimo_cierre", estado)

    def test_iniciativa_proactiva_en_reposo(self) -> None:
        sesion_mock = MagicMock()
        sesion_mock.activo = True
        puente_webrtc_mock = MagicMock()
        puente_webrtc_mock.dormida = True
        sesion_mock._puente_webrtc = puente_webrtc_mock

        self.puente.registrar_sesion_live(sesion_mock)
        self.puente.al_entrar_reposo()

        # Disparar iniciativa en reposo
        self.puente._al_proponer_iniciativa("Estaba pensando en un tema interesante")
        sesion_mock.enviar_texto.assert_called_once_with(
            "Estaba pensando en un tema interesante", turn_complete=True
        )

        # Si no está en reposo, no debe enviar nada para no interrumpir
        sesion_mock.enviar_texto.reset_mock()
        self.puente.al_despertar_o_hablar()
        self.puente._al_proponer_iniciativa("Otra frase")
        sesion_mock.enviar_texto.assert_not_called()

    def test_watchdog_liberacion_bloqueo_microfono(self) -> None:
        # Mock de sesión Live atascada en 'hablando'
        sesion = MagicMock()
        sesion.activo = True
        sesion._estado_actual = "hablando"
        sesion._t_inicio_bloqueo = time.time() - 20.0  # 20 segundos bloqueado
        sesion.cola_audio_salida = queue.Queue()
        sesion.cola_audio_salida.put(b"stale pcm audio")

        # El watchdog debe detectar que superó el timeout (14s) y liberar
        liberado = live_estado.vigilar_bloqueo(sesion, timeout_seg=14.0)
        self.assertTrue(liberado)
        sesion.vaciar_colas_audio_entrada.assert_called_once()
        self.assertTrue(sesion.cola_audio_salida.empty())

    def test_limpiar_para_reconexion(self) -> None:
        sesion = MagicMock()
        sesion.activo = True
        sesion._estado_actual = "reposo"
        sesion.cola_audio_salida = queue.Queue()
        sesion.cola_audio_salida.put(b"chunk viejo")
        sesion._puente_webrtc = MagicMock()

        live_estado.limpiar_para_reconexion(sesion)
        sesion.vaciar_colas_audio_entrada.assert_called_once()
        self.assertTrue(sesion.cola_audio_salida.empty())
        sesion._puente_webrtc.interrumpir_salida.assert_called_once()

    def test_keepalive_deepgram_ws(self) -> None:
        sesion_ws = oido_ws.SesionStreaming(clave="fake_key")
        # Si no está activa, mantener_vivo devuelve False
        self.assertFalse(sesion_ws.mantener_vivo())

        # Si está activa con un mock de socket
        sesion_ws.activa = True
        sesion_ws.ws = MagicMock()
        resultado = sesion_ws.mantener_vivo()
        self.assertTrue(resultado)
        sesion_ws.ws.send.assert_called_once_with('{"type": "KeepAlive"}')


if __name__ == "__main__":
    unittest.main()
