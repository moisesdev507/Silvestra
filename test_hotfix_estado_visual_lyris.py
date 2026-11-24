"""Regresión: cara celeste en reposo, amarillo al escuchar/hablar y turno Lyris autocerrado."""
import contextlib
import io
import os
import queue
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

import cara_dibujo
import cara_nucleo
import conversacion
import estado
import eventos
import eventos_rearme
import palabra_clave
import sonidos_ui

class CaraFalsa:
    """Doble mínimo de la cara: refleja los indicadores que decidían el color."""

    def __init__(self):
        self.escuchando = False
        self.hablando = False
        self.root = SimpleNamespace(after=lambda *_a: None)

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)

    def poner_hablando(self, valor):
        self.hablando = bool(valor)

    def asentir(self, *_a):
        pass

    def decir(self, *_a, **_k):
        self.hablando = True

    def fijar_emocion(self, *_a):
        pass

    def programar_retorno_neutral(self, *_a):
        pass

class LienzoNucleo(QWidget):
    """Widget mínimo para renderizar el núcleo sin arrancar la aplicación completa."""

    def __init__(self, **estado):
        super().__init__(None)
        self.setFixedSize(cara_dibujo.TAM, cara_dibujo.TAM)
        self.t0 = time.time()
        self.viva = estado.get("viva", True)
        self.escuchando = estado.get("escuchando", False)
        self.hablando = estado.get("hablando", False)
        self.pensando = False
        self.feliz_hasta = 0.0
        self.baile_hasta = 0.0
        self.emocion_objetivo = "neutral"
        self.nivel_volumen = estado.get("nivel", 0.5)
        self.voz_silenciada = estado.get("silenciada", False)
        self._ref_voz = None
        self._nivel_suave = 0.0
        self._color_r = float(cara_nucleo.CELESTE.red())
        self._color_g = float(cara_nucleo.CELESTE.green())
        self._color_b = float(cara_nucleo.CELESTE.blue())
        self._energia_suave = 0.0
        self._radio_suave = 52.0
        self._sonrisa_suave = 0.0

    def paintEvent(self, _evento):
        cara_dibujo.pintar(self)

class TestEstadoVisualLyris(unittest.TestCase):
    def _app(self, en_conversacion=False, escuchando=False):
        app = SimpleNamespace(
            memoria=SimpleNamespace(nombre="Lyris", creador="Usuario"),
            cara=CaraFalsa(),
            cola=queue.Queue(),
            voz=SimpleNamespace(ocupada=lambda: False),
            oido=SimpleNamespace(bloqueo=threading.RLock(), escuchar=lambda **_kw: None),
            conversacion=en_conversacion,
            escuchando=escuchando,
            descansando=False,
            musica_activa=False,
            silencios=0,
            flujo=None,
            pendiente_descanso=False,
            _generacion_escucha=0,
            _t_accion_llm=0,
            _flujo_cerrado=False,
            _iniciar_reflexion=lambda: None,
            _es_eco=lambda _t: False,
            decir=lambda *_a, **_k: None,
            enviar=lambda _t: None,
            puede_hablar_sola=lambda: True,
        )
        app.alternar_conversacion = lambda motivo="evento": (
            conversacion.alternar_conversacion(app, motivo=motivo))
        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app.despertar = lambda: conversacion.despertar(app)
        app.descansar = lambda: None
        return app

    @staticmethod
    def _detector(app):
        with patch.object(estado, "cargar", lambda: {}), \
             patch.object(palabra_clave.PalabraClave, "_cargar_modelo", lambda self: None):
            detector = palabra_clave.PalabraClave(app)
        detector.modelo = object()
        return detector

    @staticmethod
    def _color(app):
        return cara_dibujo.color_estado(
            True, app.cara.escuchando, app.cara.hablando)

    def test_color_celeste_en_reposo_y_amarillo_solo_activo(self):
        self.assertEqual(cara_dibujo.color_estado(True, False, False),
                         cara_dibujo.CIAN)
        self.assertEqual(cara_dibujo.color_estado(True, True, False),
                         cara_dibujo.AMARILLO)
        self.assertEqual(cara_dibujo.color_estado(True, False, True),
                         cara_dibujo.AMARILLO)
        self.assertEqual(cara_dibujo.color_estado(True, True, True),
                         cara_dibujo.AMARILLO)
        self.assertEqual(cara_dibujo.color_estado(True, False, False),
                         cara_dibujo.CIAN)
        self.assertEqual(cara_dibujo.color_estado(False, True, True),
                         cara_dibujo.GRIS)

    def test_paleta_y_render_qt_offscreen_cuatro_estados(self):
        self.assertEqual((cara_dibujo.CIAN.red(), cara_dibujo.CIAN.green(),
                          cara_dibujo.CIAN.blue()), (34, 211, 238))
        self.assertEqual((cara_dibujo.AMARILLO.red(), cara_dibujo.AMARILLO.green(),
                          cara_dibujo.AMARILLO.blue()), (245, 158, 11))
        self.assertEqual((cara_dibujo.GRIS.red(), cara_dibujo.GRIS.green(),
                          cara_dibujo.GRIS.blue()), (100, 116, 139))
        self.assertEqual(cara_dibujo.color_estado(True, True, True, silenciada=True),
                         cara_dibujo.GRIS)

        QApplication.instance() or QApplication([])
        estados = (
            ("reposo", {}, cara_dibujo.CIAN),
            ("escuchando", {"escuchando": True}, cara_dibujo.AMARILLO),
            ("hablando", {"hablando": True, "nivel": 0.8}, cara_dibujo.AMARILLO),
            ("silenciada", {"silenciada": True}, cara_dibujo.GRIS),
        )
        for nombre, params, esperado in estados:
            with self.subTest(estado=nombre):
                lienzo = LienzoNucleo(**params)
                imagen = QImage(cara_dibujo.TAM, cara_dibujo.TAM,
                                QImage.Format_ARGB32)
                imagen.fill(Qt.transparent)
                lienzo.render(imagen)
                self.assertGreater(
                    imagen.pixelColor(cara_dibujo.TAM // 2,
                                      cara_dibujo.TAM // 2).alpha(), 0)
                self.assertEqual(cara_dibujo.color_estado(
                    lienzo.viva, lienzo.escuchando, lienzo.hablando,
                    silenciada=lienzo.voz_silenciada), esperado)

    def test_interpolacion_suave_de_color_energia_y_radio(self):
        QApplication.instance() or QApplication([])

        def canales(color):
            return (color.red(), color.green(), color.blue())

        lienzo = LienzoNucleo()
        primer = cara_nucleo.color_suavizado(lienzo, cara_nucleo.AMBAR)
        self.assertNotEqual(canales(primer), canales(cara_nucleo.AMBAR))
        self.assertLess(primer.red(), cara_nucleo.AMBAR.red())
        for _ in range(80):
            actual = cara_nucleo.color_suavizado(lienzo, cara_nucleo.AMBAR)
        self.assertEqual(canales(actual), canales(cara_nucleo.AMBAR))

        vuelta = cara_nucleo.color_suavizado(lienzo, cara_nucleo.CELESTE)
        self.assertNotEqual(canales(vuelta), canales(cara_nucleo.CELESTE))
        for _ in range(80):
            actual = cara_nucleo.color_suavizado(lienzo, cara_nucleo.CELESTE)
        self.assertEqual(canales(actual), canales(cara_nucleo.CELESTE))
        for _ in range(80):
            actual = cara_nucleo.color_suavizado(lienzo, cara_dibujo.GRIS)
        self.assertEqual(canales(actual), canales(cara_dibujo.GRIS))

        lienzo.escuchando = True
        lienzo.nivel_volumen = 0.9
        imagen = QImage(cara_dibujo.TAM, cara_dibujo.TAM, QImage.Format_ARGB32)
        imagen.fill(Qt.transparent)
        painter = QPainter(imagen)
        try:
            cara_nucleo.dibujar(painter, lienzo, cara_nucleo.AMBAR, 1.0,
                                cara_dibujo.TAM)
            energia_1, radio_1 = lienzo._energia_suave, lienzo._radio_suave
            self.assertGreater(energia_1, 0.0)
            self.assertLess(energia_1, 1.0)
            for _ in range(30):
                cara_nucleo.dibujar(painter, lienzo, cara_nucleo.AMBAR, 1.1,
                                    cara_dibujo.TAM)
            self.assertGreater(lienzo._energia_suave, energia_1)
            self.assertGreater(lienzo._radio_suave, radio_1)
        finally:
            painter.end()

    def test_cierre_tras_respuesta_por_wakeword(self):
        app = self._app()
        detector = self._detector(app)
        app.palabra_clave = detector

        with patch.object(conversacion, "grabar", lambda *_a: None), \
             patch.object(eventos_rearme, "rearmar", lambda _app: None):
            eventos.atender_evento(app, "alternar_conversacion", "palabra_clave_vosk")
            self.assertTrue(app.turno_wakeword)
            self.assertTrue(app.turno_wakeword_esperando_orden)
            self.assertEqual(self._color(app), cara_dibujo.AMARILLO)

            eventos.atender_evento(app, "fin_voz", None)
            self.assertTrue(app.conversacion)

            eventos.atender_evento(app, "oido", "dime la hora")
            self.assertFalse(app.turno_wakeword_esperando_orden)
            app.cara.decir("Son las diez.", None)

            eventos.atender_evento(app, "fin_voz", None)

        self.assertFalse(app.conversacion)
        self.assertFalse(app.escuchando)
        self.assertFalse(app.cara.escuchando)
        self.assertFalse(app.cara.hablando)
        self.assertEqual(self._color(app), cara_dibujo.CIAN)
        self.assertTrue(detector.debe_escuchar())
        detector._disparar()
        self.assertEqual(app.cola.get_nowait(),
                         ("alternar_conversacion", "palabra_clave_vosk"))

    def test_silencio_sin_orden_cierra_turno_sin_hablar(self):
        app = self._app()
        detector = self._detector(app)
        app.palabra_clave = detector
        hablado = []
        app.decir = lambda *a, **k: hablado.append(a)

        with patch.object(conversacion, "grabar", lambda *_a: None):
            eventos.atender_evento(app, "alternar_conversacion", "palabra_clave_vosk")
            hablado.clear()
            eventos.atender_evento(app, "silencio", None)

        self.assertFalse(app.conversacion)
        self.assertFalse(app.escuchando)
        self.assertFalse(app.cara.hablando)
        self.assertEqual(self._color(app), cara_dibujo.CIAN)
        self.assertEqual(hablado, [])
        self.assertTrue(detector.debe_escuchar())

    def test_conversacion_manual_no_se_cierra_con_fin_voz(self):
        app = self._app()
        with patch.object(conversacion, "grabar", lambda *_a: None), \
             patch.object(eventos_rearme, "rearmar") as rearmar:
            eventos.atender_evento(app, "alternar_conversacion", "interfaz")
            self.assertFalse(getattr(app, "turno_wakeword", False))
            conversacion.dejar_de_escuchar(app)  # la captura terminó antes que la voz
            eventos.atender_evento(app, "fin_voz", None)
            rearmar.assert_called_once_with(app)
        self.assertTrue(app.conversacion)

    def test_silenciador_rapido_sigue_intacto(self):
        app = self._app(en_conversacion=True, escuchando=True)
        detector = self._detector(app)
        app.palabra_clave = detector
        self.assertTrue(conversacion.alternar_silencio(app))
        self.assertFalse(app.conversacion)
        self.assertFalse(app.escuchando)
        self.assertFalse(detector.debe_escuchar())
        self.assertEqual(self._color(app), cara_dibujo.CIAN)

    def test_frames_dinamicos_cuatro_estados(self):
        QApplication.instance() or QApplication([])
        img = QImage(cara_dibujo.TAM, cara_dibujo.TAM, QImage.Format_ARGB32)
        p = QPainter(img)
        casos = (("reposo", {}, cara_nucleo.CELESTE, "_particulas"),
                 ("escuchando", {"escuchando": True}, cara_nucleo.AMBAR, "_radar"),
                 ("hablando", {"hablando": True, "nivel": .9},
                  cara_nucleo.AMBAR, "_ondas_choque"),
                 ("silenciada", {"silenciada": True}, cara_dibujo.GRIS, None))
        try:
            for nombre, kw, color, fn in casos:
                with self.subTest(estado=nombre):
                    lienzo = LienzoNucleo(**kw)
                    ctx = (patch.object(cara_nucleo, fn,
                                        wraps=getattr(cara_nucleo, fn))
                           if fn else contextlib.nullcontext())
                    huellas = set()
                    with ctx as espia:
                        for i in range(5):
                            lienzo.nivel_volumen = .2 + .16 * i
                            img.fill(Qt.transparent)
                            cara_nucleo.dibujar(p, lienzo, color, 1 + i * .12,
                                                cara_dibujo.TAM)
                            huellas.add(bytes(img.constBits()))
                        if fn:
                            self.assertTrue(espia.called)
                    self.assertGreater(len(huellas), 1)
                    if nombre == "hablando":
                        self.assertTrue(lienzo._ondas)
                    if nombre == "silenciada":
                        self.assertEqual(lienzo._ondas, [])
        finally:
            p.end()

    def test_inercia_y_quietud_gris(self):
        QApplication.instance() or QApplication([])
        lienzo = LienzoNucleo(hablando=True, nivel=.9)
        img = QImage(cara_dibujo.TAM, cara_dibujo.TAM, QImage.Format_ARGB32)
        p = QPainter(img)
        try:
            for i in range(40):
                cara_nucleo.dibujar(p, lienzo, cara_nucleo.AMBAR, 1 + i * .016,
                                    cara_dibujo.TAM)
            rapido = lienzo._vel_ang
            self.assertGreater(rapido, .35)
            lienzo.hablando = False
            for i in range(40):
                cara_nucleo.dibujar(p, lienzo, cara_nucleo.CELESTE, 2 + i * .016,
                                    cara_dibujo.TAM)
            self.assertLess(lienzo._vel_ang, rapido)
            lienzo.voz_silenciada = True
            for i in range(80):
                cara_nucleo.dibujar(p, lienzo, cara_dibujo.GRIS, 3 + i * .016,
                                    cara_dibujo.TAM)
            self.assertLess(lienzo._vel_ang, .08)
            self.assertEqual(lienzo._ondas, [])
        finally:
            p.end()

    def test_earcon_hud_valido(self):
        for nombre in ("activar", "confirmar", "captado", "accion"):
            with wave.open(io.BytesIO(sonidos_ui.generar_wav(nombre))) as wf:
                self.assertEqual((wf.getnchannels(), wf.getsampwidth(),
                                  wf.getframerate()), (1, 2, 22050))
                self.assertGreater(wf.getnframes(), 1000)
        t0 = time.time()
        sonidos_ui.reproducir("activar")
        self.assertLess(time.time() - t0, .2)

if __name__ == "__main__":
    unittest.main()
