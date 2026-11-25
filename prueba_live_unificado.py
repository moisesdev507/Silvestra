"""Pruebas unitarias para la integración de Gemini Live en main.py:
1. Compuerta anti-eco half-duplex: bloquea envío de micrófono durante reproducción + ventana de cola (~320ms).
2. Watchdog de silencio (9.0s): cierra la sesión Live y regresa a espera local.
3. Conmutación automática y disyuntor ante error de cuota 429 / RESOURCE_EXHAUSTED.
4. Función del puente delgado de herramientas (paridad con los módulos existentes).
"""
import asyncio
import queue
import time
import unittest
from unittest.mock import MagicMock, patch

import live_audio
import live_herramientas
import live_motor
import live_orquestador


class TestGeminiLiveUnificado(unittest.TestCase):

    def test_compuerta_anti_eco_ventana_gracia(self):
        q_salida = queue.Queue()
        # Ventana de 120ms para prueba rápida
        compuerta = live_audio.CompuertaAntiEco(modo_audifonos=False, eco_cola_ms=120.0, cola_salida=q_salida)
        
        chunk = b"\x10\x00" * 400
        # Sin audio de salida: no está en ventana de eco
        self.assertFalse(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, chunk)
        self.assertFalse(sil)

        # 1. Empieza a reproducir en parlantes
        compuerta.marcar_inicio_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, bytes(len(chunk)))
        self.assertTrue(sil)

        # 2. Termina la reproducción: debe permanecer en ventana de gracia (120ms)
        compuerta.marcar_fin_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertTrue(sil)

        # 3. Transcurre la ventana de gracia
        time.sleep(0.15)
        self.assertFalse(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, chunk)
        self.assertFalse(sil)

    def test_watchdog_silencio_9_segundos(self):
        cierre_llamado = []
        sesion = live_motor.SesionKayaLive(
            timeout_silencio=0.1,  # 100ms para prueba unitaria ágil
            on_cierre_automatico=lambda: cierre_llamado.append(True)
        )
        sesion.activo = True
        sesion._t_ultima_voz = time.monotonic() - 0.2  # Simular silencio pasado

        # Ejecutar ciclo watchdog en bucle asyncio
        async def _correr():
            await sesion._tarea_watchdog()

        asyncio.run(_correr())
        self.assertFalse(sesion.activo)
        self.assertEqual(len(cierre_llamado), 1)

    def test_disyuntor_cuota_429(self):
        # Verificar detección de errores de cuota
        exc_429 = Exception("429 ResourceExhausted: Quota exceeded for model")
        self.assertTrue(live_motor.es_error_cuota(exc_429))
        self.assertFalse(live_motor.es_error_cuota(Exception("Network timeout")))

        # Activar disyuntor
        live_motor.activar_enfriamiento_cuota(0.01)  # Enfriamiento breve
        self.assertTrue(live_motor.esta_en_enfriamiento_cuota())

        # El coordinador debe conmutar automáticamente al motor clásico
        app_mock = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        # Con enfriamiento activo, no debe iniciar Live
        self.assertFalse(coordinador.intentar_activar_live("hola"))

    def test_puente_delgado_herramientas_paridad(self):
        # 1. Telemetría del sistema
        txt_tele = live_herramientas.consultar_sistema()
        self.assertIn("Fecha y hora", txt_tele)

        # 2. Control de volumen delegado a acciones.py
        res_vol = live_herramientas.ejecutar_accion_local("sube el volumen")
        self.assertTrue("subido" in res_vol.lower() or "volumen" in res_vol.lower())

        # 3. Declaraciones para Function Calling
        tools = live_herramientas.declarar_declaraciones_herramientas()
        self.assertEqual(len(tools), 1)
        nombres = [f.name for f in tools[0].function_declarations]
        self.assertIn("ejecutar_accion_pc", nombres)
        self.assertIn("consultar_estado_pc", nombres)
        self.assertIn("entrar_en_reposo", nombres)


if __name__ == "__main__":
    unittest.main()
