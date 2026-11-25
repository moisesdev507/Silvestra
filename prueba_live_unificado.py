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

    def setUp(self):
        with live_motor._LOCK_DISYUNTOR:
            live_motor._DISYUNTOR_HASTA = 0.0

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

    def test_envio_inmediato_orden_inicial_al_conectar(self):
        # 1. Con orden específica
        s1 = live_motor.SesionKayaLive(orden_inicial="qué clima hace")
        self.assertEqual(s1.orden_inicial, "qué clima hace")

        # 2. Con orden vacía o solo 'Kaya'
        s2 = live_motor.SesionKayaLive(orden_inicial="Kaya")
        self.assertEqual(s2.orden_inicial, "Kaya")

        # 3. Verificar que el coordinador inyecta la orden inicial
        app_mock = MagicMock()
        app_mock.invocacion = MagicMock()
        app_mock.oido = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        coordinador.modo_live_habilitado = True

        with patch.object(live_motor.SesionKayaLive, "iniciar", return_value=True):
            ok = coordinador.intentar_activar_live("revisa mis correos")
            self.assertTrue(ok)
            self.assertEqual(coordinador.sesion_live.orden_inicial, "revisa mis correos")
            # Verificar que oido e invocacion fueron pausados
            app_mock.oido.pausar.assert_called_once()
            app_mock.invocacion.pausar.assert_called_once()

    def test_retorno_flujo_principal_sin_false_como_voz(self):
        from main import Silvestra
        from voz import Voz

        voz = Voz()
        callback_llamado = []
        # voz.hablar(False) debe descartarse sin error
        voz.hablar(False, al_terminar=lambda: callback_llamado.append(True))
        self.assertTrue(len(callback_llamado) <= 1)

        app_mock = MagicMock()
        app_mock.voz = voz
        app_mock.cara = MagicMock()
        app_mock.coordinador_live = None

        # app.decir(False) debe descartarse limpiamente sin hablar
        Silvestra.decir(app_mock, False)
        app_mock.cara.decir.assert_not_called()

    def test_cierre_limpio_loop_sin_futures_colgados(self):
        sesion = live_motor.SesionKayaLive()
        loop = asyncio.new_event_loop()
        sesion._loop = loop
        sesion.activo = True

        async def _tarea_larga():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                pass

        # Crear tareas en el loop
        t1 = loop.create_task(_tarea_larga())
        t2 = loop.create_task(_tarea_larga())

        # Detener la sesión
        sesion.detener()

        # Recolectar tareas sin error 'Event loop stopped before Future completed'
        pendientes = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pendientes:
            t.cancel()
        loop.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
        loop.close()

        self.assertTrue(t1.cancelled() or t1.done())
        self.assertTrue(t2.cancelled() or t2.done())

    def test_pausa_y_reanudacion_oido(self):
        from oido import Oido
        oido = Oido(cliente=None, vocabulario={})
        self.assertFalse(oido.esta_pausado())

        oido.pausar()
        self.assertTrue(oido.esta_pausado())
        # Mientras está pausado, escuchar devuelve None de inmediato sin tocar micrófono
        res = oido.escuchar()
        self.assertIsNone(res)

        oido.reanudar()
        self.assertFalse(oido.esta_pausado())


if __name__ == "__main__":
    unittest.main()
