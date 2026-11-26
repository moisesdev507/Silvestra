"""Pruebas de la Fase 2 del Cerebro Único (Sistema 2 asíncrono)."""
import contextlib
import json
import os
import re
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import capacidades_extra
import cerebro_planificador
import cerebro_sistema2
import cerebro_unico
import herramientas_cerebro


def _frases(texto):
    return [f for f in re.split(r"(?<=[.!?])\s+", str(texto or "").strip()) if f]


class TestSistema2Unico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_estado = os.path.join(self.tmp.name, "estado_sistema2.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _estado_terminal(self, id_tarea, timeout=3.0, clave="entregado"):
        fin = time.time() + timeout
        while time.time() < fin:
            if os.path.exists(self.ruta_estado):
                try:
                    with open(self.ruta_estado, encoding="utf-8") as archivo:
                        datos = json.load(archivo)
                    for tarea in datos.get("tareas", []):
                        if (tarea.get("id") == id_tarea
                                and tarea.get("estado") in ("completada", "con_aviso", "error")
                                and (not clave or clave in tarea)):
                            return tarea
                except Exception:
                    pass
            time.sleep(0.02)
        return {}

    @staticmethod
    def _parches_plan(stack):
        stack.enter_context(patch.object(
            cerebro_sistema2.cerebro_planificador, "descomponer_en_pasos",
            return_value=[("consultar_conocimiento_local", "tema"), ("resumen", "resumir")]))
        stack.enter_context(patch.object(
            cerebro_sistema2.cerebro_planificador, "ejecutar_plan_multipaso",
            return_value=[("consultar_conocimiento_local", True, "dato local"),
                          ("resumen", True, "resumen listo")]))
        stack.enter_context(patch.object(
            cerebro_sistema2.cerebro_planificador, "verificar_coherencia_y_sintetizar",
            return_value="Resumen final en voz alta."))
        stack.enter_context(patch.object(cerebro_sistema2, "_razonar", return_value=""))
        stack.enter_context(patch.object(
            cerebro_sistema2.memoria_unificada, "recordar", return_value=True))

    def test_a_descomposicion_y_ejecucion_multipaso(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(
                herramientas_cerebro, "consultar_conocimiento_local", return_value="Hallazgo local."))
            stack.enter_context(patch.object(
                herramientas_cerebro, "resumir_enlace_o_video", return_value="Enlace resumido."))
            stack.enter_context(patch.object(
                cerebro_unico, "compilar_contexto_unico", return_value="Contexto local."))
            stack.enter_context(patch.object(
                capacidades_extra, "revisar_pantalla", return_value="Pantalla revisada."))
            pasos = cerebro_planificador.descomponer_en_pasos(
                "Investiga el proyecto y mira la pantalla", contexto="contexto previo")
            self.assertTrue(2 <= len(pasos) <= 5)
            resultados = cerebro_planificador.ejecutar_plan_multipaso(pasos)
            self.assertEqual(len(resultados), len(pasos))
            self.assertTrue(all(ok for _, ok, _ in resultados))
            sintesis = cerebro_planificador.verificar_coherencia_y_sintetizar(pasos, resultados)
        self.assertLessEqual(len(_frases(sintesis)), 3)
        self.assertTrue(sintesis)

    def test_a2_tolerancia_a_fallos_por_paso(self):
        pasos = [("consultar_conocimiento_local", "tema"), ("paso_inexistente_xyz", "x"),
                 ("resumen", "resumir")]
        with patch.object(herramientas_cerebro, "consultar_conocimiento_local",
                          return_value="Dato local."):
            resultados = cerebro_planificador.ejecutar_plan_multipaso(pasos)
        self.assertEqual(len(resultados), 3)
        self.assertTrue(resultados[0][1])
        self.assertFalse(resultados[1][1])
        self.assertTrue(resultados[2][1])

    def test_b_entrega_segunda_plano_despertando_puente(self):
        puente = SimpleNamespace(dormida=True, despertar=MagicMock())
        entregado = threading.Event()
        sesion = SimpleNamespace(
            activo=True, _puente_webrtc=puente,
            enviar_texto=MagicMock(side_effect=lambda texto: (entregado.set(), True)[1]))
        app = SimpleNamespace(
            coordinador_live=SimpleNamespace(sesion_live=sesion, app=None),
            cola=MagicMock())
        app.coordinador_live.app = app
        creados = []
        thread_real = threading.Thread

        def fabrica(*args, **kwargs):
            hilo = thread_real(*args, **kwargs)
            creados.append(hilo)
            return hilo

        with contextlib.ExitStack() as stack:
            self._parches_plan(stack)
            stack.enter_context(patch.object(cerebro_sistema2, "_app", app))
            stack.enter_context(patch.object(cerebro_sistema2, "RUTA_ESTADO", self.ruta_estado))
            with patch.object(cerebro_sistema2.threading, "Thread", side_effect=fabrica):
                respuesta = cerebro_sistema2.lanzar_tarea_sistema2("Investiga el proyecto")
            self.assertTrue(respuesta["aceptado"])
            self.assertTrue(entregado.wait(3.0))
            self.assertTrue(creados)
            self.assertTrue(creados[0].daemon)
            self.assertFalse(puente.dormida)
            puente.despertar.assert_called_once_with()
            sesion.enviar_texto.assert_called_once_with("Resumen final en voz alta.")
            app.cola.put.assert_not_called()
            estado = self._estado_terminal(respuesta["id"])
            self.assertEqual(estado.get("estado"), "completada")

    def test_c_fallback_cola_sin_live_activo(self):
        entregado = threading.Event()
        cola = MagicMock()
        cola.put.side_effect = lambda item: entregado.set()
        app = SimpleNamespace(
            coordinador_live=SimpleNamespace(
                sesion_live=SimpleNamespace(activo=False), app=None),
            cola=cola)
        app.coordinador_live.app = app
        with contextlib.ExitStack() as stack:
            self._parches_plan(stack)
            stack.enter_context(patch.object(cerebro_sistema2, "_app", app))
            stack.enter_context(patch.object(cerebro_sistema2, "RUTA_ESTADO", self.ruta_estado))
            respuesta = cerebro_sistema2.lanzar_tarea_sistema2("Cruza fuentes locales")
            self.assertTrue(entregado.wait(3.0))
            cola.put.assert_any_call(("hablar", "Resumen final en voz alta."))
            estado = self._estado_terminal(respuesta["id"])
            self.assertEqual(estado.get("entregado"), True)

    def test_d_entrega_directa_no_toca_cola(self):
        puente = SimpleNamespace(dormida=False, despertar=MagicMock())
        sesion = SimpleNamespace(activo=True, _puente_webrtc=puente,
                                 enviar_texto=MagicMock(return_value=True))
        cola = MagicMock()
        coordinador = SimpleNamespace(sesion_live=sesion, app=SimpleNamespace(cola=cola))
        self.assertTrue(cerebro_sistema2._entregar_live_seguro(coordinador, "Hola de S2"))
        sesion.enviar_texto.assert_called_once_with("Hola de S2")
        puente.despertar.assert_not_called()
        cola.put.assert_not_called()

    def test_e_herramienta_inmediata_y_declarada(self):
        with patch.object(cerebro_sistema2, "lanzar_tarea_sistema2",
                          return_value={"aceptado": True, "id": "s2-prueba"}) as lanzar:
            texto = herramientas_cerebro.ejecutar_plan_complejo("Investiga y cruza fuentes")
        self.assertTrue(texto.startswith("Plan iniciado en segundo plano..."))
        lanzar.assert_called_once()
        declaraciones = herramientas_cerebro.declaraciones()
        self.assertIn("ejecutar_plan_complejo", [d.name for d in declaraciones])
        with patch.object(cerebro_sistema2, "lanzar_tarea_sistema2",
                          return_value={"aceptado": True, "id": "s2-prueba"}):
            self.assertIn("Plan iniciado", herramientas_cerebro.despachar(
                "ejecutar_plan_complejo", {"objetivo": "Investiga y cruza fuentes"}))


if __name__ == "__main__":
    unittest.main()
