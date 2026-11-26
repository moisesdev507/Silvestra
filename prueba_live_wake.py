"""Pruebas del wake-word KWS sobre el puente WebRTC en reposo Azul."""
import asyncio
import os
import queue
import struct
import unittest
from unittest.mock import MagicMock, patch

import live_motor
import live_orquestador
import live_webrtc
import live_wake


class _PuenteFalso:
    def __init__(self, dormida=True):
        self.dormida = dormida
        self.despertado = 0
        self.cola_entrada = queue.Queue()

    def despertar(self):
        self.despertado += 1


async def _correr_envio(sesion, session, segundos=0.3):
    tarea = asyncio.create_task(sesion._tarea_envio_audio(session))
    try:
        await asyncio.wait_for(tarea, timeout=segundos)
    except asyncio.TimeoutError:
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass


class TestWakeKwsWebRTC(unittest.TestCase):

    def test_modelo_kws_instalado(self):
        ruta = live_wake.ruta_modelo_kws()
        for nombre in live_wake.ARCHIVOS_KWS:
            self.assertTrue(os.path.isfile(os.path.join(ruta, nombre)), nombre)

    def test_azul_no_envia_audio_y_alimenta_detector(self):
        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        puente = _PuenteFalso(dormida=True)
        sesion._puente_webrtc = puente
        puente.cola_entrada.put_nowait(struct.pack("<160h", *([100] * 160)))

        session = MagicMock()
        session.send_realtime_input = MagicMock()
        detector = MagicMock()
        detector.procesar.return_value = False

        async def _correr():
            with patch.object(live_wake, "DetectorKaya", return_value=detector):
                await _correr_envio(sesion, session)

        asyncio.run(_correr())
        detector.procesar.assert_called()
        session.send_realtime_input.assert_not_called()
        self.assertTrue(puente.dormida)
        self.assertEqual(puente.despertado, 0)

    def test_deteccion_despierta_a_amarillo(self):
        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        puente = _PuenteFalso(dormida=True)
        sesion._puente_webrtc = puente
        puente.cola_entrada.put_nowait(struct.pack("<160h", *([200] * 160)))

        detector = MagicMock()
        detector.procesar.return_value = True
        session = MagicMock()
        session.send_realtime_input = MagicMock()

        async def _correr():
            with patch.object(live_wake, "DetectorKaya", return_value=detector):
                await _correr_envio(sesion, session, segundos=0.15)

        asyncio.run(_correr())
        self.assertFalse(puente.dormida)
        self.assertEqual(puente.despertado, 1)
        detector.reiniciar.assert_called()
        session.send_realtime_input.assert_not_called()

    def test_voz_clasica_pausada_con_live(self):
        app = MagicMock()
        coordinador = live_orquestador.CoordinadorLiveSilvestra(app)
        coordinador.modo_live_habilitado = True
        with patch.object(live_motor.SesionKayaLive, "iniciar", return_value=True):
            self.assertTrue(coordinador.intentar_activar_live("hola"))
        app.voz.pausar.assert_called_once()
        app.oido.pausar.assert_called_once()

    def test_senal_sleep_reinicia_detector(self):
        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        puente = _PuenteFalso(dormida=True)
        sesion._puente_webrtc = puente
        puente.cola_entrada.put_nowait(live_webrtc.SENAL_SLEEP)

        detector = MagicMock()
        detector.procesar.return_value = False
        session = MagicMock()
        session.send_realtime_input = MagicMock()

        async def _correr():
            with patch.object(live_wake, "DetectorKaya", return_value=detector):
                await _correr_envio(sesion, session, segundos=0.15)

        asyncio.run(_correr())
        detector.reiniciar.assert_called()


if __name__ == "__main__":
    unittest.main()
