"""Pruebas del ahorro de tokens en Gemini Live y del despertar local por voz."""
import asyncio
import json
import os
import queue
import struct
import time
import unittest
from unittest.mock import MagicMock, patch

import despertar_local
import eventos
import live_audio
import live_motor
import live_orquestador
import puerta_audio_live


class Reloj:
    def __init__(self, inicio=1000.0):
        self.t = inicio

    def __call__(self):
        return self.t

    def avanzar(self, segundos):
        self.t += segundos


def pcm(voz=False):
    valor = 1500 if voz else 0
    return struct.pack("<h", valor) * 800  # 50 ms a 16 kHz


class ReconocedorFalso:
    def __init__(self, texto=""):
        self.texto = texto
        self.llamadas = 0

    def AcceptWaveForm(self, datos):
        self.llamadas += 1

    def PartialResult(self):
        return json.dumps({"partial": self.texto})

    def Result(self):
        return json.dumps({"text": ""})


class HiloSincrono:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self.target, self.args = target, args
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class TestPuertaAudioLive(unittest.TestCase):

    def test_timeout_defecto_es_9_segundos(self):
        self.assertEqual(live_audio.TIMEOUT_SILENCIO_DEFECTO, 9.0)
        self.assertEqual(puerta_audio_live.PuertaAudioLive().timeout_silencio, 9.0)
        self.assertEqual(live_motor.SesionKayaLive().timeout_silencio, 9.0)
        self.assertEqual(live_audio.timeout_silencio_configurado("7"), 7.0)
        self.assertEqual(live_audio.timeout_silencio_configurado("mal"), 9.0)
        with patch.dict(os.environ, {"KAYA_TIMEOUT_SILENCIO": "9"}):
            self.assertEqual(live_audio.timeout_silencio_configurado(), 9.0)

    def test_apagado_exacto_a_los_9_segundos_desde_fin_real(self):
        reloj = Reloj()
        gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        gate.activar()
        gate.marcar_reproduccion(True)
        reloj.avanzar(30.0)  # turno largo: inactividad pausada
        self.assertFalse(gate.debe_cerrar())
        gate.marcar_reproduccion(False)
        reloj.avanzar(0.15 + 8.9)
        self.assertFalse(gate.debe_cerrar())
        reloj.avanzar(0.2)  # supera los 9.0 s desde fin + margen de 150 ms
        self.assertTrue(gate.debe_cerrar())

    def test_silencio_activo_envia_cero_frames_y_voz_entra_sin_reconectar(self):
        reloj = Reloj()
        gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        gate.activar()
        cola = queue.Queue(maxsize=60)
        for _ in range(120):  # 6 s de silencio con WebSocket abierto
            reloj.avanzar(0.05)
            self.assertFalse(puerta_audio_live.encolar_autorizados(gate, pcm(False), cola))
        self.assertTrue(cola.empty())
        self.assertEqual(gate.frames_enviados, 0)
        autorizados, habla = gate.procesar(pcm(True))
        self.assertTrue(habla)
        self.assertTrue(autorizados)

    def test_silencio_local_no_envia_frames(self):
        gate = puerta_audio_live.PuertaAudioLive(reloj=Reloj())
        gate.activar()
        cola = queue.Queue(maxsize=60)
        for _ in range(20):
            self.assertFalse(puerta_audio_live.encolar_autorizados(gate, pcm(False), cola))
        self.assertTrue(cola.empty())
        self.assertEqual(gate.frames_enviados, 0)
        self.assertEqual(gate.frames_descartados, 20)

    def test_preroll_voz_y_hangover_se_libera(self):
        reloj = Reloj()
        gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        gate.activar()
        for _ in range(8):
            reloj.avanzar(0.05)
            gate.procesar(pcm(False))
        reloj.avanzar(0.05)
        autorizados, habla = gate.procesar(pcm(True))
        self.assertTrue(habla)
        self.assertEqual(len(autorizados), 7)  # 300 ms de pre-roll + voz, sin retención
        reloj.avanzar(0.05)
        autorizados, habla = gate.procesar(pcm(True))
        self.assertEqual(len(autorizados), 1)  # frames siguientes en tiempo real
        self.assertTrue(habla)
        reloj.avanzar(0.35)
        autorizados, habla = gate.procesar(pcm(False))
        self.assertEqual(len(autorizados), 1)  # dentro de la cola de 450 ms
        self.assertFalse(habla)
        reloj.avanzar(0.15)
        self.assertEqual(gate.procesar(pcm(False))[0], [])  # cola cerrada
        self.assertFalse(gate.abierta)

    def test_eco_bloqueado_durante_reproduccion_y_margen(self):
        reloj = Reloj(2000.0)
        gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        gate.activar()
        cola = queue.Queue()
        gate.marcar_reproduccion(True)
        t_actividad = gate.ultima_actividad
        reloj.avanzar(0.1)
        autorizados, habla = gate.procesar(pcm(True))
        self.assertEqual(autorizados, [])
        self.assertFalse(habla)
        self.assertEqual(gate.frames_enviados, 0)
        self.assertEqual(gate.ultima_actividad, t_actividad)
        self.assertFalse(puerta_audio_live.encolar_autorizados(gate, pcm(True), cola))
        self.assertTrue(cola.empty())

        gate.marcar_reproduccion(False)  # el buffer de salida se vació
        reloj.avanzar(0.10)  # dentro del margen acústico de 150 ms
        self.assertEqual(gate.procesar(pcm(True))[0], [])
        self.assertTrue(gate.reproduciendo)

        reloj.avanzar(0.10)  # 200 ms: margen vencido, la voz pasa al instante
        autorizados, habla = gate.procesar(pcm(True))
        self.assertTrue(habla)
        self.assertTrue(autorizados)

    def test_inactividad_pausada_y_reinicia_al_terminar_reproduccion(self):
        reloj = Reloj(3000.0)
        gate = puerta_audio_live.PuertaAudioLive(timeout_silencio=12.0, reloj=reloj)
        gate.activar()
        gate.marcar_reproduccion(True)
        reloj.avanzar(100.0)
        self.assertFalse(gate.debe_cerrar())  # pausado mientras Kaya habla

        gate.marcar_reproduccion(False)
        reloj.avanzar(0.35)  # termina el margen acústico de 150 ms
        self.assertFalse(gate.debe_cerrar())
        reloj.avanzar(11.7)  # cuenta desde 0 al terminar de sonar
        self.assertFalse(gate.debe_cerrar())
        reloj.avanzar(0.2)
        self.assertTrue(gate.debe_cerrar())

    def test_compuerta_eco_150ms_y_callback_no_envia(self):
        q_salida = queue.Queue()
        compuerta = live_audio.CompuertaAntiEco(modo_audifonos=False, cola_salida=q_salida)
        self.assertEqual(compuerta.eco_cola_ms, 150.0)
        self.assertFalse(compuerta.esta_en_ventana_eco())
        compuerta.marcar_inicio_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())
        compuerta.marcar_fin_escritura()
        self.assertTrue(compuerta.esta_en_ventana_eco())  # cola acústica
        _, silenciado = compuerta.filtrar_chunk_entrada(pcm(True))
        self.assertTrue(silenciado)

        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        sesion.puerta.activar()
        sesion.puerta.marcar_reproduccion(True)
        sesion._rate_entrada = live_audio.RATE_ENTRADA
        sesion._callback_audio_in(pcm(True), 800, None, None)
        self.assertTrue(sesion.cola_audio_entrada.empty())
        self.assertEqual(sesion.puerta.frames_enviados, 0)

    def test_timeout_cierra_stream_y_websocket_sin_tokens(self):
        streams, cierre_auto, cierre_ws = [], [], []
        sesion = live_motor.SesionKayaLive(
            timeout_silencio=9.0,
            on_cierre_automatico=lambda: cierre_auto.append(True),
        )
        sesion.activo = True
        sesion.puerta.activar()
        micro = MagicMock(name="micro")
        sesion._stream_entrada = micro
        sesion._loop = MagicMock()
        sesion._loop.is_running.return_value = True
        sesion._session_genai = MagicMock(name="gemini-live")
        sesion.puerta.notificar_actividad(instante=time.monotonic() - 10.0)

        def _cerrar_stream(stream):
            streams.append(stream)
            return None

        def _cerrar_ws(session, loop):
            cierre_ws.append((session, loop))

        with patch.object(live_motor.live_audio, "cerrar_stream", side_effect=_cerrar_stream), \
                patch.object(live_motor.live_audio, "cerrar_sesion_live", side_effect=_cerrar_ws):
            asyncio.run(sesion._tarea_watchdog())

        self.assertFalse(sesion.activo)
        self.assertEqual(sesion.puerta.estado, "en_reposo")
        self.assertEqual(sesion.puerta.frames_enviados, 0)
        self.assertIn(micro, streams)
        self.assertEqual(len(cierre_ws), 1)
        self.assertIs(cierre_ws[0][0], sesion._session_genai)
        self.assertEqual(len(cierre_auto), 1)

    def test_variantes_locales_de_kaya_en_cualquier_punto(self):
        for texto in ("kaya", "KAÍA", "kaya qué hora es", "oye kaya dime algo",
                      "ayúdame con esto kaya", "calla", "caia, ¿qué hora es?"):
            self.assertTrue(despertar_local.contiene_kaya(texto), texto)
        for texto in ("", "hola", "kayak", "llama a Lucía"):
            self.assertFalse(despertar_local.contiene_kaya(texto), texto)

    def _wake_local(self, texto, despiertes):
        reloj = Reloj()
        rec = ReconocedorFalso(texto)
        wake = despertar_local.EscuchaDespertarLocal(
            lambda palabra, audio: despiertes.append((palabra, audio)),
            reconocedor=rec, reloj=reloj, dormir=lambda _s: None,
        )
        wake._gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        wake._gate.activar()
        wake._vivo = True
        return wake, rec, reloj

    def test_kaya_local_reactiva_live_sin_clic(self):
        despiertes = []
        wake, rec, reloj = self._wake_local("kaya, ¿qué hora es?", despiertes)
        for _ in range(10):
            reloj.avanzar(0.05)
            wake.procesar_frame(pcm(True))
        self.assertGreater(rec.llamadas, 0)
        self.assertIsNotNone(wake._t_deteccion)
        wake._vigilar()  # despacha en cuanto aparece en el partial, sin silencio final
        self.assertEqual(len(despiertes), 1)
        self.assertEqual(despiertes[0][0], "kaya")
        self.assertGreaterEqual(len(despiertes[0][1]), 10)
        reloj.avanzar(0.15)
        wake.procesar_frame(pcm(True))  # dicho después del nombre, mientras reconecta
        self.assertEqual(len(wake.drenar_posteriores()), 1)
        wake.detener()
        self.assertFalse(wake.activa)

    def test_despertar_por_partial_en_mitad_de_frase(self):
        despiertes = []
        reloj = Reloj()
        wake = despertar_local.EscuchaDespertarLocal(
            lambda palabra, audio: despiertes.append((palabra, list(audio))),
            reconocedor=ReconocedorFalso("oye kaia dime algo"),
            reloj=reloj, dormir=lambda _s: None,
        )
        wake._gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        wake._gate.activar()
        wake._vivo = True
        reloj.avanzar(0.05)
        wake.procesar_frame(pcm(True))
        self.assertIsNotNone(wake._t_deteccion)
        wake._vigilar()
        self.assertEqual(despiertes[0][0], "kaya")
        wake.detener()

    def test_despertar_por_result_final_al_final_de_la_frase(self):
        class SoloFinal(ReconocedorFalso):
            def PartialResult(self):
                return json.dumps({"partial": ""})

            def Result(self):
                return json.dumps({"text": "ayúdame con esto kaya"})

        despiertes = []
        reloj = Reloj()
        wake = despertar_local.EscuchaDespertarLocal(
            lambda palabra, audio: despiertes.append((palabra, list(audio))),
            reconocedor=SoloFinal(""), reloj=reloj, dormir=lambda _s: None,
        )
        wake._gate = puerta_audio_live.PuertaAudioLive(reloj=reloj)
        wake._gate.activar()
        wake._vivo = True
        for _ in range(3):
            reloj.avanzar(0.05)
            wake.procesar_frame(pcm(True))
        reloj.avanzar(0.6)
        wake.procesar_frame(pcm(False))  # con el gate cerrado se evalúa Result()
        self.assertIsNotNone(wake._t_deteccion)
        wake._vigilar()
        self.assertEqual(despiertes[0][0], "kaya")
        self.assertGreaterEqual(len(despiertes[0][1]), 3)  # frase completa, antes y después
        wake.detener()

    def test_silencio_en_reposo_no_despierta_ni_envia_api(self):
        despiertes = []
        wake, rec, reloj = self._wake_local("", despiertes)
        for _ in range(30):
            reloj.avanzar(0.05)
            wake.procesar_frame(pcm(False))
        self.assertEqual(rec.llamadas, 0)
        self.assertIsNone(wake._t_deteccion)
        self.assertEqual(despiertes, [])
        self.assertEqual(wake._gate.frames_enviados, 0)

    def test_coordinador_reposo_y_reactivacion_con_audio_inicial(self):
        app = MagicMock()
        app.cola = queue.Queue()
        coord = live_orquestador.CoordinadorLiveSilvestra(app)
        with patch.object(despertar_local, "EscuchaDespertarLocal") as cls_wake, \
                patch.object(coord, "intentar_activar_live", return_value=True) as activar, \
                patch.object(live_orquestador.threading, "Thread", HiloSincrono):
            instance = cls_wake.return_value
            instance.activa = False
            instance.iniciar.return_value = True
            coord._al_cierre_automatico()
            cls_wake.assert_called_once()
            instance.iniciar.assert_called_once()

            coord._al_despertar_local("kaya", [pcm(True)])
            activar.assert_called_once()
            self.assertEqual(activar.call_args.args[0], "")
            self.assertEqual(activar.call_args.kwargs["audio_inicial"], [pcm(True)])
            self.assertIs(activar.call_args.kwargs["wake"], instance)
            instance.detener.assert_called()
        eventos = [app.cola.get_nowait()[0] for _ in range(app.cola.qsize())]
        self.assertIn("micro_live_estado", eventos)

    def test_clic_orbe_y_indicador_visual(self):
        app = MagicMock()
        app.cola = queue.Queue()
        coord = MagicMock()
        app.coordinador_live = coord
        with patch.object(live_orquestador.threading, "Thread", HiloSincrono):
            eventos.atender_evento(app, "toggle_micro_live", None)
        coord.alternar_microfono.assert_called_once()

        app.cara.micro_live_cerrado = False
        eventos.atender_evento(app, "micro_live_estado", True)
        self.assertTrue(app.cara.micro_live_cerrado)
        app.cara.poner_escuchando.assert_called_with(False)
        eventos.atender_evento(app, "micro_live_estado", False)
        self.assertFalse(app.cara.micro_live_cerrado)


if __name__ == "__main__":
    unittest.main(verbosity=2)
