"""Validacion global pasiva de la integracion multimodal de Silvestra."""
import threading
import time
import tracemalloc
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from audio_evento_modelo import (EventoAcustico, ClasificacionAcustica,
    CategoriaSonido, NivelRelevanciaSonido)
from multimodal_integracion_modelo import ObservacionIntegrada
from multimodal_puente_app import SistemaMultimodalSilvestra


class AppFalsa:
    def __init__(self):
        from queue import Queue
        self.cola = Queue()
        self.voz = None
        self.camara = None


class TestValidacionGlobal(unittest.TestCase):
    def setUp(self):
        self.app = AppFalsa()
        self.sistema = SistemaMultimodalSilvestra(self.app)

    def tearDown(self):
        self.sistema.detener()

    def test_01_privacidad_por_defecto(self):
        estado = self.sistema.estado_salud()
        self.assertFalse(estado["permiso_camara"])
        self.assertFalse(estado["permiso_microfono"])
        self.assertFalse(estado["permitir_grabacion_continua"])
        self.assertFalse(estado["autorizacion_externa"])

    def test_02_activar_requiere_permiso(self):
        self.assertFalse(self.sistema.activar_fuente("camara")["ok"])

    def test_03_desactivar_microfono_limpia_grabacion(self):
        self.sistema.activar_fuente("microfono", permiso=True,
                                    permitir_grabacion_continua=True)
        self.sistema.desactivar_fuente("microfono")
        self.assertFalse(self.sistema.permitir_grabacion_continua)

    def test_04_inicio_detencion_idempotentes(self):
        self.sistema.iniciar()
        self.sistema.iniciar()
        self.assertTrue(self.sistema.estado_salud()["activo"])
        self.sistema.detener()
        self.assertFalse(self.sistema.estado_salud()["activo"])

    def test_05_observacion_aislada_es_insuficiente(self):
        o = self._obs("audio", "alarma observada", ("alarma",), "probable")
        self.sistema.integrador.registrar_observacion(o, publicar=False)
        resultado = self.sistema.interprete.interpretar([o])
        self.assertEqual(resultado.nivel_incertidumbre.value, "insuficiente")
        self.assertTrue(resultado.lagunas_informacion)

    def test_06_alarma_y_notificacion_visual(self):
        audio = self._audio("alarma", "notificacion alarma audible")
        visual = self._vision("notificacion visible en pantalla")
        a = self.sistema.registrar_audio(audio)
        v = self.sistema.registrar_vision(visual)
        self.assertIsNotNone(a)
        self.assertIsNotNone(v)
        self.assertGreaterEqual(len(self.sistema.integrador.correlacionador.correlacionar(
            list(self.sistema.integrador._observaciones))), 0)

    def test_07_error_app_y_contexto_windows(self):
        ctx = {"hwnd": 4, "pid": 50, "titulo": "Editor", "ejecutable": "editor.exe"}
        self.sistema.integrador.ingerir_contexto_windows(ctx)
        ui = SimpleNamespace(aplicacion="editor.exe", hwnd=4,
            alertas=[SimpleNamespace(texto="Error de aplicación")], elementos=[], timestamp=time.time())
        self.assertIsNotNone(self.sistema.registrar_interfaz(ui))
        import os
        self.sistema._activo = True
        with patch("contexto_windows.obtener_contexto_windows", side_effect=[ctx, {
            "hwnd": 0, "pid": os.getpid(), "titulo": "Silvestra", "ejecutable": "silvestra.exe"}]):
            primera = self.sistema._actualizar_contexto()
            segunda = self.sistema._actualizar_contexto()
        self.assertEqual(primera["titulo"], "Editor")
        self.assertEqual(segunda["titulo"], "Editor")

    def test_08_cambio_interfaz_y_evento_auditivo(self):
        ui = SimpleNamespace(aplicacion="navegador", hwnd=5, alertas=[], elementos=[], timestamp=time.time())
        self.sistema.registrar_interfaz(ui)
        self.assertIsNotNone(self.sistema.registrar_audio(self._audio("timbre", "timbre durante cambio")))

    def test_09_observaciones_contradictorias_no_rompen_pipeline(self):
        a = self._obs("vision", "ventana abierta", ("abierta",), "confirmado")
        b = self._obs("interfaz", "ventana cerrada", ("cerrada",), "confirmado")
        self.sistema.integrador.registrar_observacion(a, publicar=False)
        self.sistema.integrador.registrar_observacion(b, publicar=False)
        salida = self.sistema.interprete.interpretar(
            self.sistema.integrador.consultar_situacion_actual()["situacion"])
        self.assertIsNotNone(salida)

    def test_10_fallo_parcial_reintentos_acotados(self):
        self.sistema.iniciar()
        with patch("contexto_windows.obtener_contexto_windows", side_effect=OSError("sensor")):
            for _ in range(8):
                self.sistema._actualizar_contexto()
        self.assertLessEqual(self.sistema._reintentos, 3)

    def test_11_cancelacion_respeta_token(self):
        ev = threading.Event(); ev.set()
        from situacion_interpretacion_motor import MotorInterpretacionSituaciones
        with self.assertRaises(InterruptedError):
            MotorInterpretacionSituaciones().interpretar([], token_cancelacion=ev)

    def test_12_consulta_desde_main_difiere_captura(self):
        with patch.object(self.sistema, "_captura_temporal_segura", return_value="captura prueba") as cap:
            result = self.sistema.consultar_entorno_actual("que ves en pantalla")
            self.assertIn("captura diferida", result["captura_pantalla"])
            self.sistema._pantalla.shutdown(wait=True, cancel_futures=False)
            cap.assert_called_once()

    def test_13_captura_efimera_cierra_imagen(self):
        class Img:
            width, height = 20, 10
            closed = False
            def close(self): self.closed = True
        img = Img()
        with patch("gui_seguridad.escritorio_de_entrada_activo", return_value=True), \
             patch("contexto_windows.obtener_contexto_windows", return_value={"titulo":"Editor"}), \
             patch("PIL.ImageGrab.grab", return_value=img):
            self.assertIn("no almacenada", self.sistema._captura_temporal_segura())
        self.assertTrue(img.closed)

    def test_14_ventana_sensible_no_captura(self):
        with patch("gui_seguridad.escritorio_de_entrada_activo", return_value=True), \
             patch("contexto_windows.obtener_contexto_windows", return_value={"titulo":"Password manager"}), \
             patch("PIL.ImageGrab.grab") as grab:
            self.assertIn("omitida", self.sistema._captura_temporal_segura())
        grab.assert_not_called()

    def test_15_memoria_acotada_bajo_tracemalloc(self):
        tracemalloc.start()
        for i in range(80):
            self.sistema.integrador.registrar_observacion(
                self._obs("vision", f"evento {i}", (str(i),), "confirmado"), publicar=False)
        actual, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(pico, 8 * 1024 * 1024)
        self.assertLessEqual(len(self.sistema.integrador._observaciones), 48)

    def test_16_latencia_ingesta(self):
        inicio = time.perf_counter()
        for i in range(10):
            self.sistema.integrador.registrar_observacion(
                self._obs("vision", f"latencia {i}", ("latencia",), "confirmado"), publicar=False)
        self.assertLess(time.perf_counter() - inicio, 1.0)

    def test_17_no_accion_autonoma(self):
        self.assertIsNone(self.sistema.integrador.orquestador)
        self.assertIsNone(self.sistema.interprete.orquestador)

    def test_18_pipeline_e2e_publica_solo_por_cola(self):
        salida = self.sistema.registrar_vision(self._vision("cuadro de dialogo visible"))
        self.assertIsNotNone(salida)
        self.assertIsNotNone(self.app.cola)
        from cerebro import Cerebro
        self.app.sistema_multimodal = SimpleNamespace(consultar_entorno_actual=lambda q: {
            "ventana": {"titulo": "Editor de texto"}, "audio": "sin eventos",
            "situacion": "informacion insuficiente", "captura_pantalla": "captura efimera"})
        with patch("cerebro.construir_prompt", return_value="prompt base"):
            cerebro = Cerebro(None, SimpleNamespace(), app=self.app)
            prompt = cerebro.instrucciones("¿Qué ves en mi pantalla?")
        self.assertIn("Editor de texto", prompt)
        self.assertIn("hechos de hipótesis", prompt)

    def test_19_seguimiento_voz_actualiza_ventana_en_cerebro(self):
        from cerebro import Cerebro
        ventanas = [
            {"hwnd": 10, "pid": 51, "titulo": "Microsoft Edge", "ejecutable": "msedge.exe"},
            {"hwnd": 11, "pid": 52, "titulo": "Visual Studio Code", "ejecutable": "code.exe"},
            {"hwnd": 12, "pid": 53, "titulo": "Bloc de notas", "ejecutable": "notepad.exe"},
        ]
        self.sistema._activo = True
        self.app.sistema_multimodal = self.sistema
        with patch("contexto_windows.obtener_contexto_windows", side_effect=ventanas), \
             patch.object(self.sistema, "_captura_temporal_segura", return_value="captura efimera"), \
             patch("cerebro.construir_prompt", return_value="prompt base"):
            cerebro = Cerebro(None, SimpleNamespace(), app=self.app)
            primero = cerebro.instrucciones("¿Qué ves en la pantalla?")
            transcripcion = cerebro.instrucciones("y ahora a que parte de a cambio")
            seguimiento = cerebro.instrucciones("¿y ahora?")
        self.assertIn("Microsoft Edge", primero)
        self.assertIn("Visual Studio Code", transcripcion)
        self.assertIn("Bloc de notas", seguimiento)
        self.assertEqual(self.sistema.estado_salud()["ultima_ventana_externa"]["titulo"], "Bloc de notas")

    @staticmethod
    def _obs(modalidad, texto, tags, epistemico):
        return ObservacionIntegrada(modalidad, "prueba", texto,
            etiquetas_semanticas=tags,
            datos_estructurados={"nivel_epistemico": epistemico, "observaciones": [texto]},
            relevancia="media")

    @staticmethod
    def _vision(texto):
        return SimpleNamespace(descripcion=texto, observaciones_verificables=[texto],
            interpretaciones_inciertas=[], texto_extraido="", elementos_identificados=[],
            nivel_confianza=None, id_entrada="visual-test", timestamp=time.time())

    @staticmethod
    def _audio(categoria, texto):
        c = CategoriaSonido(categoria)
        return EventoAcustico(fuente="sintetico", energia_rms=.2, ratio_voz_vad=0,
            clasificacion=ClasificacionAcustica(categoria=c, confianza=.8),
            relevancia=NivelRelevanciaSonido.alta,
            observaciones_verificables=[texto])


if __name__ == "__main__":
    unittest.main()
