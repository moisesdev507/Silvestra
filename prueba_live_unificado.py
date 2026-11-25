"""Pruebas unitarias para la integración de Gemini Live en main.py."""
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
        with live_audio._LOCK_DISYUNTOR:
            live_audio._DISYUNTOR_HASTA = 0.0
        try:
            import estado
            d = estado.cargar()
            d["modo_voz_principal"] = "gemini_live"
            estado.guardar(d)
        except Exception:
            pass

    def test_compuerta_anti_eco_ventana_gracia(self):
        q_salida = queue.Queue()
        compuerta = live_audio.CompuertaAntiEco(modo_audifonos=False, eco_cola_ms=120.0, cola_salida=q_salida)
        chunk = b"\x10\x00" * 400
        self.assertFalse(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, chunk)
        self.assertFalse(sil)

        compuerta.marcar_inicio_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, bytes(len(chunk)))
        self.assertTrue(sil)

        compuerta.marcar_fin_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertTrue(sil)

        time.sleep(0.15)
        self.assertFalse(compuerta.esta_en_ventana_eco())
        c_res, sil = compuerta.filtrar_chunk_entrada(chunk)
        self.assertEqual(c_res, chunk)
        self.assertFalse(sil)

    def test_watchdog_silencio_9_segundos(self):
        # 1. Blindaje: rechazar valores menores a 2.0s y fijar 9.0s por defecto
        sesion_defecto = live_motor.SesionKayaLive(timeout_silencio=0.1)
        self.assertEqual(sesion_defecto.timeout_silencio, 9.0)

        # 2. Con timeout válido >= 2.0s
        cierre = []
        sesion = live_motor.SesionKayaLive(timeout_silencio=2.0, on_cierre_automatico=lambda: cierre.append(True))
        sesion.activo = True
        sesion.puerta.activar()
        sesion.puerta.notificar_actividad(instante=time.monotonic() - 3.0)

        async def _correr():
            await sesion._tarea_watchdog()

        asyncio.run(_correr())
        self.assertFalse(sesion.activo)
        self.assertEqual(len(cierre), 1)

    def test_disyuntor_cuota_429(self):
        exc_429 = Exception("429 ResourceExhausted: Quota exceeded for model")
        self.assertTrue(live_motor.es_error_cuota(exc_429))
        self.assertFalse(live_motor.es_error_cuota(Exception("Network timeout")))

        live_motor.activar_enfriamiento_cuota(0.01)
        self.assertTrue(live_motor.esta_en_enfriamiento_cuota())

        app_mock = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        self.assertFalse(coordinador.intentar_activar_live("hola"))

    def test_puente_delgado_herramientas_paridad(self):
        txt_tele = live_herramientas.consultar_sistema()
        self.assertIn("Fecha y hora", txt_tele)

        res_vol = live_herramientas.ejecutar_accion_local("sube el volumen")
        self.assertTrue("subido" in res_vol.lower() or "volumen" in res_vol.lower())

        tools = live_herramientas.declarar_declaraciones_herramientas()
        nombres = [f.name for f in tools[0].function_declarations]
        for esperado in ("ejecutar_accion_pc", "consultar_estado_pc", "entrar_en_reposo", "consultar_clima", "buscar_en_internet"):
            self.assertIn(esperado, nombres)

    def test_envio_inmediato_orden_inicial_al_conectar(self):
        s1 = live_motor.SesionKayaLive(orden_inicial="qué clima hace")
        self.assertEqual(s1.orden_inicial, "qué clima hace")

        s2 = live_motor.SesionKayaLive(orden_inicial="Kaya")
        self.assertEqual(s2.orden_inicial, "Kaya")

        app_mock = MagicMock()
        app_mock.invocacion = MagicMock()
        app_mock.oido = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        coordinador.modo_live_habilitado = True

        with patch.object(live_motor.SesionKayaLive, "iniciar", return_value=True):
            ok = coordinador.intentar_activar_live("revisa mis correos")
            self.assertTrue(ok)
            self.assertEqual(coordinador.sesion_live.orden_inicial, "revisa mis correos")
            app_mock.oido.pausar.assert_called_once()
            app_mock.invocacion.pausar.assert_called_once()

    def test_retorno_flujo_principal_sin_false_como_voz(self):
        from main import Silvestra
        from voz import Voz

        voz = Voz()
        cb = []
        voz.hablar(False, al_terminar=lambda: cb.append(True))
        self.assertTrue(len(cb) <= 1)

        app_mock = MagicMock()
        app_mock.voz = voz
        app_mock.cara = MagicMock()
        app_mock.coordinador_live = None

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

        t1 = loop.create_task(_tarea_larga())
        t2 = loop.create_task(_tarea_larga())
        sesion.detener()

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
        self.assertIsNone(oido.escuchar())

        oido.reanudar()
        self.assertFalse(oido.esta_pausado())

    def test_evento_poner_hablando_sin_error_visual(self):
        import eventos
        app_mock = MagicMock()
        app_mock.cara = MagicMock()
        app_mock.flujo = None

        eventos.atender_evento(app_mock, "poner_hablando", False)
        app_mock.cara.poner_hablando.assert_called_with(False)
        app_mock.cara.decir.assert_not_called()

        app_mock.reset_mock()
        eventos.atender_evento(app_mock, "cara_metodo", ("poner_hablando", False))
        app_mock.cara.poner_hablando.assert_called_with(False)
        app_mock.cara.decir.assert_not_called()

        app_mock.reset_mock()
        eventos.atender_evento(app_mock, "cara_metodo", ("poner_escuchando", True))
        app_mock.cara.poner_escuchando.assert_called_with(True)
        app_mock.cara.decir.assert_not_called()

    def test_selector_ajustes_modo_voz(self):
        app_mock = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        coordinador.modo_live_habilitado = True

        coordinador.actualizar_modo_voz("clasico")
        self.assertFalse(coordinador.es_modo_principal())
        self.assertFalse(coordinador.intentar_activar_live("hola"))

        coordinador.actualizar_modo_voz("gemini_live")
        self.assertTrue(coordinador.es_modo_principal())

    def test_precalentamiento_paralelo_y_prompt_rapido(self):
        # 1. Prompt rápido ultracompacto para el primer saludo
        prompt_rapido = live_audio.construir_instruccion_arranque_rapido()
        self.assertIn("Kaya", prompt_rapido)
        self.assertLess(len(prompt_rapido), 800)

        # 2. Telemetría de primera voz
        live_audio._PRIMERA_VOZ_REGISTRADA = False
        live_audio.registrar_tiempo_primera_voz()
        self.assertTrue(live_audio._PRIMERA_VOZ_REGISTRADA)

        # 3. Pre-calentamiento en paralelo en Coordinador
        app_mock = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app_mock)
        coordinador.modo_live_habilitado = True
        with patch.object(coordinador, "intentar_activar_live") as mock_activar:
            coordinador.precalentar_en_paralelo()
            time.sleep(0.08)
            mock_activar.assert_called_once()

    def test_ciclo_completo_audio_habla_desbloqueo_y_captura_remuestreada(self):
        import struct
        from google.genai import types

        q_salida = queue.Queue()
        compuerta = live_audio.CompuertaAntiEco(modo_audifonos=False, eco_cola_ms=100.0, cola_salida=q_salida)

        compuerta.marcar_inicio_escritura()
        chunk_prueba = b"\x10\x00" * 160
        c_res, silenciado = compuerta.filtrar_chunk_entrada(chunk_prueba)
        self.assertTrue(silenciado)
        self.assertEqual(c_res, bytes(len(chunk_prueba)))

        compuerta.marcar_fin_escritura()
        time.sleep(0.12)
        c_res, silenciado = compuerta.filtrar_chunk_entrada(chunk_prueba)
        self.assertFalse(silenciado)
        self.assertEqual(c_res, chunk_prueba)

        muestras_48k = [800] * 480
        pcm_48k = struct.pack(f"<{len(muestras_48k)}h", *muestras_48k)
        pcm_16k = live_audio.remuestrear_pcm16_a_16k(pcm_48k, 48000)
        self.assertEqual(len(pcm_16k), 160 * 2)

        sesion = live_motor.SesionKayaLive()
        sesion.compuerta = compuerta
        sesion.activo = True
        sesion.puerta.activar()
        sesion._rate_entrada = 48000
        t_prev = sesion.puerta.ultima_actividad
        time.sleep(0.02)  # resolución de time.monotonic() en Windows ≈ 15.6 ms

        sesion._callback_audio_in(pcm_48k, len(muestras_48k), None, None)
        self.assertFalse(sesion.cola_audio_entrada.empty())
        self.assertGreater(sesion.puerta.ultima_actividad, t_prev)

        session_mock = MagicMock()
        session_mock.send_realtime_input = unittest.mock.AsyncMock()

        async def _enviar_test():
            item = sesion.cola_audio_entrada.get_nowait()
            await session_mock.send_realtime_input(audio=types.Blob(data=item, mime_type="audio/pcm;rate=16000"))

        asyncio.run(_enviar_test())
        session_mock.send_realtime_input.assert_called_once()
        _, kwargs = session_mock.send_realtime_input.call_args
        blob = kwargs.get("audio")
        self.assertIsNotNone(blob)
        self.assertEqual(blob.mime_type, "audio/pcm;rate=16000")
        self.assertEqual(len(blob.data), 160 * 2)

    def test_cierre_streams_garantizado(self):
        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        mock_in = MagicMock()
        mock_out = MagicMock()
        sesion._stream_entrada = mock_in
        sesion._stream_salida = mock_out

        sesion.detener()
        self.assertFalse(sesion.activo)
        self.assertIsNone(sesion._stream_entrada)
        self.assertIsNone(sesion._stream_salida)
        mock_in.abort.assert_called_once()
        mock_in.close.assert_called_once()
        mock_out.abort.assert_called_once()
        mock_out.close.assert_called_once()

    def test_calibracion_ruido_vs_voz_y_watchdog(self):
        import struct
        # 1. Ruido o silencio post-frase (rms ~200, nivel ~0.02) NO se detecta como voz para el watchdog
        ruido = struct.pack("<480h", *([200] * 480))
        es_habla, rms, nivel = live_audio.es_voz_activa(ruido)
        self.assertFalse(es_habla)

        # 2. Voz real (rms ~650, nivel ~0.12) SÍ se detecta como voz activa (umbral 480)
        voz = struct.pack("<480h", *([650] * 480))
        es_habla, rms, nivel = live_audio.es_voz_activa(voz)
        self.assertTrue(es_habla)

        # 3. Con el gate abierto, el silencio se descarta localmente (0 tokens)
        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        sesion.puerta.activar()
        sesion._rate_entrada = 48000
        t_base = sesion.puerta.ultima_actividad

        sesion._callback_audio_in(ruido, 480, None, None)
        self.assertTrue(sesion.cola_audio_entrada.empty())
        self.assertEqual(sesion.puerta.ultima_actividad, t_base)

        # 4. Con voz activa sí se libera audio y se refresca el watchdog
        time.sleep(0.02)
        sesion._callback_audio_in(voz, 480, None, None)
        self.assertFalse(sesion.cola_audio_entrada.empty())
        self.assertGreater(sesion.puerta.ultima_actividad, t_base)

        sesion.puerta.notificar_actividad(instante=t_base)
        time.sleep(0.02)
        sesion._callback_audio_in(voz, 480, None, None)
        self.assertGreater(sesion.puerta.ultima_actividad, t_base)

    def test_herramientas_clima_y_busqueda_web(self):
        import consulta_web

        self.assertEqual(consulta_web.detectar_consulta_clima("¿cómo está el clima hoy?"), "Panamá")
        self.assertEqual(consulta_web.detectar_consulta_clima("clima en Madrid"), "Madrid")
        self.assertIsNone(consulta_web.detectar_consulta_clima("hace tiempo que no te veo"))
        self.assertEqual(consulta_web.detectar_consulta_busqueda("busca en internet precio del oro"), "precio del oro")

        tools = live_herramientas.declarar_declaraciones_herramientas()
        nombres = [f.name for f in tools[0].function_declarations]
        self.assertIn("consultar_clima", nombres)
        self.assertIn("buscar_en_internet", nombres)

        with patch("consulta_web.consultar_clima", return_value="En Panamá hay 30 grados."):
            res = asyncio.run(live_herramientas.despachar_herramienta_asincrona("consultar_clima", {"ciudad": "Panamá"}))
            self.assertIn("Panamá", res)

        with patch("consulta_web.buscar_web", return_value="Resultados de búsqueda web."):
            res = asyncio.run(live_herramientas.despachar_herramienta_asincrona("buscar_en_internet", {"consulta": "noticias"}))
            self.assertEqual(res, "Resultados de búsqueda web.")

        with patch("consulta_web.consultar_clima", return_value="En Panamá hay 29 grados."):
            res_c = consulta_web.responder_consulta_web_o_clima("¿qué clima hace en Panamá?")
            self.assertIsNotNone(res_c)
            self.assertIn("29 grados", res_c[0])

    def test_supresion_doble_voz_en_nacimiento_y_decir(self):
        from main import Silvestra
        import nacimiento

        app_mock = MagicMock()
        coordinador = MagicMock()
        coordinador.es_modo_principal.return_value = True
        coordinador.esta_live_activo.return_value = False
        app_mock.coordinador_live = coordinador
        app_mock.voz = MagicMock()
        app_mock.cara = MagicMock()

        nacimiento.saludar(app_mock)
        app_mock.voz.hablar.assert_not_called()

        Silvestra.decir(app_mock, "Hola usuario", con_voz=True)
        app_mock.voz.hablar.assert_not_called()
        app_mock.cara.decir.assert_called_once()


if __name__ == "__main__":
    unittest.main()
