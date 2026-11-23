"""Pruebas del Sprint 2B: salud dinámica, prompt condicional, caché y split."""
from __future__ import annotations

import contextlib
import inspect
import io
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import acciones
import cerebro_contexto_cache
import cerebro_prompt
import cerebro_prompt_compacto
import proveedores
import proveedores_cadenas as pc
import proveedores_cadenas_dinamicas as pcd
import proveedores_salud
import respuesta_flujo
import respuesta_flujo_acciones


class _BaseSalud(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_db = os.path.join(self.tmp.name, "salud.db")
        self._anterior = proveedores_salud._registro
        proveedores_salud.configurar(ruta_db=self.ruta_db, alfa=0.5)

    def tearDown(self):
        proveedores_salud._registro = self._anterior
        self.tmp.cleanup()


class TestSaludProveedores(_BaseSalud):
    def test_01_ewma_ttft(self):
        proveedores_salud.registrar_ttft("Groq", "modelo-a", 1.0)
        proveedores_salud.registrar_ttft("Groq", "modelo-a", 3.0)
        datos = proveedores_salud.obtener_salud("Groq", "modelo-a")
        self.assertEqual(datos["muestras_ttft"], 2)
        self.assertAlmostEqual(datos["ewma_ttft"], 2.0)
        self.assertEqual(datos["tasa_error"], 0.0)

    def test_02_fallos_tasas_y_sanitizacion(self):
        proveedores_salud.registrar_exito("Groq", "modelo-a")
        proveedores_salud.registrar_fallo("Groq", "modelo-a", "timeout", "tarde")
        proveedores_salud.registrar_fallo(
            "Groq", "modelo-a", "429", "Bearer sk-abcdef123456 agotado"
        )
        datos = proveedores_salud.obtener_salud("Groq", "modelo-a")
        self.assertEqual(datos["intentos"], 3)
        self.assertEqual(datos["errores"], 2)
        self.assertEqual(datos["errores_429"], 1)
        self.assertAlmostEqual(datos["tasa_error"], 2 / 3)
        self.assertAlmostEqual(datos["tasa_429"], 1 / 3)
        self.assertIn("429", datos["ultimo_fallo"])
        self.assertNotIn("sk-abcdef123456", datos["ultimo_fallo"])

    def test_03_persistencia_en_bd_temporal(self):
        proveedores_salud.registrar_ttft("Cerebras", "modelo-b", 0.8)
        proveedores_salud.registrar_fallo("Cerebras", "modelo-b", "404", "no existe")
        self.assertTrue(os.path.exists(self.ruta_db))
        proveedores_salud.configurar(ruta_db=self.ruta_db, alfa=0.5)
        datos = proveedores_salud.obtener_salud("Cerebras", "modelo-b")
        self.assertAlmostEqual(datos["ewma_ttft"], 0.8)
        self.assertEqual(datos["errores"], 1)
        self.assertIn("404", datos["ultimo_fallo"])

    def test_04_reordenamiento_sin_historial_conserva_orden(self):
        candidatos = [{"nombre": n} for n in ("Groq", "Google", "Cerebras")]
        resultado = pcd.reordenar(candidatos, tarea="charla", carril="rapido")
        self.assertEqual([c["nombre"] for c in resultado], ["Groq", "Google", "Cerebras"])

    def test_05_reordenamiento_degrada_proveedor(self):
        for _ in range(4):
            proveedores_salud.registrar_fallo("Google", "modelo-g", "429", "cuota")
        proveedores_salud.registrar_exito("Groq", "modelo-q")
        proveedores_salud.registrar_ttft("Groq", "modelo-q", 0.4)
        candidatos = [{"nombre": n, "modelos_activos": [f"modelo-{n[0].lower()}"]}
                      for n in ("Groq", "Google", "Cerebras")]
        resultado = pcd.reordenar(candidatos, tarea="charla", carril="rapido")
        self.assertEqual(resultado[-1]["nombre"], "Google")
        self.assertEqual(resultado[0]["nombre"], "Groq")

    def test_06_firmas_con_carril_compatibles(self):
        self.assertIn("carril", inspect.signature(pc.obtener_candidatos_tarea).parameters)
        self.assertIn("carril", inspect.signature(pc.proveedores_disponibles).parameters)
        self.assertIn("carril", inspect.signature(proveedores.proveedores_disponibles).parameters)


class TestPromptCondicional(unittest.TestCase):
    def setUp(self):
        self.memoria = SimpleNamespace(
            hechos=[], datos={"resumenes_tematicos": {}},
            nombre="Lyris", creador="Moisés", proposito="asistente personal",
        )

    def _prompt(self, texto):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            return cerebro_prompt.construir_prompt(self.memoria, texto_actual=texto)

    def test_07_charla_omite_catalogo(self):
        catalogo = cerebro_prompt_compacto.catalogo_condicional("hola, ¿cómo estás?", acciones)
        self.assertEqual(catalogo, cerebro_prompt_compacto.BLOQUE_MINIMO)
        prompt = self._prompt("hola, ¿cómo estás?")
        self.assertIn("ACCIONES DISPONIBLES", prompt)
        self.assertNotIn("- buscar:", prompt)

    def test_08_comando_inyecta_catalogo(self):
        self.assertTrue(cerebro_prompt_compacto.tiene_intencion_operativa("Abre el navegador"))
        catalogo = cerebro_prompt_compacto.catalogo_condicional("Abre el navegador", acciones)
        self.assertIn("- buscar:", catalogo)
        self.assertIn("- buscar:", self._prompt("Abre el navegador"))

    def test_09_consulta_teorica_no_es_operativa(self):
        self.assertFalse(
            cerebro_prompt_compacto.tiene_intencion_operativa("Explícame qué es una base de datos")
        )

    def test_10_delegacion_con_modulo_inyectado(self):
        import acciones
        falso = SimpleNamespace(
            ACCIONES=dict(acciones.ACCIONES),
            ESPECIALES=dict(acciones.ESPECIALES),
            VIVAS=dict(acciones.VIVAS),
        )
        with patch("cerebro_prompt.acciones", falso):
            self.assertEqual(
                cerebro_prompt.describir_acciones_compactas("hola"),
                cerebro_prompt_compacto.BLOQUE_MINIMO,
            )
            self.assertIn("- buscar:", cerebro_prompt.describir_acciones_compactas("Abre el navegador"))


class TestCacheContexto(unittest.TestCase):
    def setUp(self):
        cerebro_contexto_cache.invalidar()

    def tearDown(self):
        cerebro_contexto_cache.invalidar()

    def test_11_ttl_reutiliza_snapshot(self):
        motor = MagicMock()
        motor.obtener_contexto.return_value = {"timestamp": 1, "probable": {}}
        with patch("contexto_motor.obtener_motor_contexto", return_value=motor):
            primero = cerebro_contexto_cache.obtener_contexto()
            segundo = cerebro_contexto_cache.obtener_contexto()
            cerebro_contexto_cache.invalidar()
            tercero = cerebro_contexto_cache.obtener_contexto()
        self.assertEqual(primero, segundo)
        self.assertEqual(motor.obtener_contexto.call_count, 2)
        self.assertEqual(tercero, primero)

    def test_12_copias_profundas_y_cambio_de_motor(self):
        ctx = {"detectado": {"ventana": {"ejecutable": "Code.exe"}}}
        motor = MagicMock()
        motor.obtener_contexto.return_value = ctx
        with patch("contexto_motor.obtener_motor_contexto", return_value=motor):
            primero = cerebro_contexto_cache.obtener_contexto()
            primero["detectado"]["ventana"]["ejecutable"] = "otro.exe"
            segundo = cerebro_contexto_cache.obtener_contexto()
            motor_nuevo = MagicMock()
            motor_nuevo.obtener_contexto.return_value = {"detectado": {}}
        self.assertEqual(segundo["detectado"]["ventana"]["ejecutable"], "Code.exe")
        with patch("contexto_motor.obtener_motor_contexto", return_value=motor_nuevo):
            tercero = cerebro_contexto_cache.obtener_contexto()
        self.assertEqual(tercero, {"detectado": {}})


class TestSplitRespuestaFlujo(unittest.TestCase):
    def test_13_firma_y_modulo_extraido(self):
        firma = inspect.signature(respuesta_flujo.responder_flujo)
        self.assertEqual(
            list(firma.parameters), ["cerebro", "texto", "al_frase", "on_primer_token"]
        )
        self.assertTrue(callable(respuesta_flujo_acciones.atender))
        self.assertTrue(callable(respuesta_flujo_acciones._reg_turno))

    def test_14_interceptor_de_vision_sigue_operativo(self):
        cerebro = SimpleNamespace(historial=[], app=None, _podar_historial=lambda: None)
        frases = []
        with patch("vision_pantalla.detectar_peticion_vision", return_value=True), \
             patch("vision_pantalla.capturar_y_analizar_pantalla", return_value=(True, "Vi la pantalla")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, "mira mi pantalla", frases.append
            )
        self.assertEqual(resultado, ("Vi la pantalla", None, "atenta"))
        self.assertEqual(frases, ["Vi la pantalla"])

    def test_15_tamano_orquestador_bajo_objetivo(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(respuesta_flujo.__file__)),
                            "respuesta_flujo.py")
        self.assertLess(os.path.getsize(ruta), 10500)


if __name__ == "__main__":
    unittest.main()
