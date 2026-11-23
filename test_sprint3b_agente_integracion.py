"""Integración del Sprint 3B: conector, confirmación, cancelación y retrocompatibilidad."""
import os
import queue
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import acciones
import agente_bucle
import agente_confirmacion
import agente_conector
import cerebro_planificador
import recordatorios
from respuesta_flujo import responder_flujo


class MemoriaFalsa:
    creador = "Moisés"
    nombre = "Lyris"


class AppFalsa:
    def __init__(self, canal="chat"):
        self.cola = queue.Queue()
        self.origen_entrada_actual = canal
        self.memoria = MemoriaFalsa()
        self.conversacion = True
        self.escuchando = False
        self.flujo = None
        self.cerebro = None
        self.recordatorios = SimpleNamespace(
            poner_recordatorio=lambda arg: f"Listo, recordatorio programado: {arg}")

    def decir(self, *_args, **_kwargs):
        return None

    def escuchar(self):
        return None

    def _dejar_de_escuchar(self):
        self.escuchando = False


class CerebroFalso:
    def __init__(self, app):
        self.app = app
        self.memoria = app.memoria
        self.historial = []
        app.cerebro = self

    def _podar_historial(self):
        self.historial = self.historial[-20:]


class TestSprint3BIntegracion(unittest.TestCase):
    def setUp(self):
        self.app = AppFalsa()
        self.cerebro = CerebroFalso(self.app)
        self.hilos = []
        self.resultado = None
        self.frases = []
        self._vivas = dict(acciones.VIVAS)
        self._con_texto = set(acciones.CON_TEXTO)
        self._ruta_rec = recordatorios.RUTA_JSON
        self.tmp_rec = os.path.join(
            tempfile.gettempdir(), f"test_s3b_rec_{os.getpid()}_{time.time()}.json")
        recordatorios.RUTA_JSON = self.tmp_rec
        with open(self.tmp_rec, "w", encoding="utf-8") as f:
            f.write("[]\n")
        self.archivo = "sprint3b_prueba.txt"
        self.ruta_archivo = os.path.join("workspace_lyris", self.archivo)
        self._limpiar_archivo()
        agente_conector.configurar(activo=True, ttl=2.0)

    def tearDown(self):
        for hilo in self.hilos:
            if hilo.is_alive():
                hilo.join(0.5)
        agente_confirmacion.cancelar(self.app)
        agente_conector.cancelar(self.app)
        agente_conector.configurar(activo=True, ttl=agente_confirmacion.TTL_CONFIRMACION_SEG)
        recordatorios.RUTA_JSON = self._ruta_rec
        acciones.VIVAS.clear()
        acciones.VIVAS.update(self._vivas)
        acciones.CON_TEXTO.clear()
        acciones.CON_TEXTO.update(self._con_texto)
        for ruta in (self.tmp_rec, self.ruta_archivo):
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except OSError:
                pass

    def _limpiar_archivo(self):
        try:
            if os.path.exists(self.ruta_archivo):
                os.remove(self.ruta_archivo)
        except OSError:
            pass

    def _registrar_borrado(self):
        self.borrados = []

        def borrar(arg=None):
            self.borrados.append(arg)
            return True, f"Borré {arg}"

        acciones.registrar("borrar_archivo", borrar, "borra archivos del sistema", con_texto=True)

    def _responder_en_hilo(self, texto):
        def destino():
            self.resultado = responder_flujo(self.cerebro, texto, self.frases.append)

        hilo = threading.Thread(target=destino, daemon=True)
        self.hilos.append(hilo)
        hilo.start()
        return hilo

    def _esperar_pregunta(self):
        limite = time.time() + 2.0
        while time.time() < limite:
            while not self.app.cola.empty():
                evento = self.app.cola.get()
                if evento[0] == "hablar" and "Confirmas" in str(evento[1][0]):
                    return evento
            time.sleep(0.01)
        self.fail("No se publicó la pregunta de confirmación")

    # 1. Charla pura: bypass sin construir el bucle.
    def test_charla_hace_bypass_sin_overhead(self):
        self.assertFalse(agente_conector.debe_intervenir("Hola, ¿cómo estás?"))
        self.assertFalse(agente_conector.debe_intervenir("Gracias"))
        self.assertTrue(agente_conector.debe_intervenir("Crea un archivo y recuérdame"))
        with patch.object(agente_bucle.BucleAgente, "ejecutar",
                          side_effect=AssertionError("El bucle no debe ejecutarse")):
            self.assertIsNone(agente_conector.atender(
                self.cerebro, "hola", app=self.app))

    # 2. Multi-paso real desde responder_flujo con recuperación del paso 1.
    def test_multipaso_con_recuperacion_y_voz_unica(self):
        real = acciones.ejecutar
        llamadas = []

        def ejecutar(nombre, arg=None):
            llamadas.append((nombre, arg))
            if nombre == "escribir_archivo" and len(
                    [x for x in llamadas if x[0] == nombre]) == 1:
                return False, "fallo temporal del paso 1"
            return real(nombre, arg)

        orden = (f"Crea el archivo {self.archivo} con notas de sprint 3B "
                 "y luego recuérdame revisarlo en cinco minutos")
        with patch.object(acciones, "ejecutar", side_effect=ejecutar):
            msg, accion, _emo = responder_flujo(self.cerebro, orden, self.frases.append)

        self.assertIsNone(accion)
        self.assertEqual(len(self.frases), 1, "La voz final debe emitirse una sola vez")
        self.assertEqual(self.frases[0], msg)
        self.assertIn(f"guardé '{self.archivo}'", msg)
        self.assertIn("programé tu recordatorio", msg)
        self.assertTrue(os.path.exists(self.ruta_archivo))
        escrituras = [x for x in llamadas if x[0] == "escribir_archivo"]
        self.assertEqual(len(escrituras), 2, "El paso 1 debe reintentarse tras el error")
        with open(self.ruta_archivo, "r", encoding="utf-8") as f:
            self.assertIn("sprint 3b", f.read().lower())

    # 3. Riesgo alto: aprobar, rechazar, timeout y canal no interactivo.
    def test_riesgo_alto_se_aprueba_con_si(self):
        self._registrar_borrado()
        hilo = self._responder_en_hilo("ACCION: borrar_archivo | workspace_lyris/dato.txt")
        self._esperar_pregunta()
        self.assertEqual(agente_confirmacion.resolver(self.app, "Sí."), "aprobado")
        hilo.join(3)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(self.borrados, ["workspace_lyris/dato.txt"])
        self.assertIn("completé borrar_archivo", self.resultado[0])

    def test_riesgo_alto_se_rechaza_con_no(self):
        self._registrar_borrado()
        hilo = self._responder_en_hilo("ACCION: borrar_archivo | workspace_lyris/dato.txt")
        self._esperar_pregunta()
        self.assertEqual(agente_confirmacion.resolver(self.app, "No."), "rechazado")
        hilo.join(3)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(self.borrados, [])
        self.assertIn("No ejecuté borrar_archivo", self.resultado[0])

    def test_riesgo_alto_caduca_por_timeout(self):
        self._registrar_borrado()
        agente_conector.configurar(ttl=0.05)
        hilo = self._responder_en_hilo("ACCION: borrar_archivo | workspace_lyris/dato.txt")
        hilo.join(3)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(self.borrados, [])
        self.assertIn("No ejecuté borrar_archivo", self.resultado[0])

    def test_canal_no_interactivo_bloquea_riesgo_alto(self):
        self._registrar_borrado()
        self.app.origen_entrada_actual = "movil_http"
        msg, accion, _emo = responder_flujo(
            self.cerebro, "ACCION: borrar_archivo | workspace_lyris/dato.txt", None)
        self.assertEqual(self.borrados, [])
        self.assertIn("No ejecuté borrar_archivo", msg)
        self.assertIsNone(accion)
        self.assertTrue(self.app.cola.empty())

    # 4. Cancelación limpia y salida hablada garantizada.
    def test_cancelacion_a_mitad_mantiene_respuesta_hablada(self):
        iniciado = threading.Event()
        detener = threading.Event()

        def larga(_arg=None):
            iniciado.set()
            while not detener.is_set():
                time.sleep(0.01)
            return True, "operación detenida"

        acciones.registrar("operacion_larga", larga, "proceso largo controlado")
        hilo = self._responder_en_hilo("ACCION: operacion_larga | proceso")
        self.assertTrue(iniciado.wait(2.0))
        self.assertTrue(agente_conector.cancelar(self.app))
        detener.set()
        hilo.join(3)
        self.assertFalse(hilo.is_alive())
        self.assertIn("Cancelé", self.resultado[0])
        self.assertEqual(len(self.frases), 1)
        self.assertEqual(self.frases[0], self.resultado[0])

    # 5. Retrocompatibilidad de fachadas y suites previas.
    def test_fachadas_heredadas_siguen_disponibles(self):
        self.assertTrue(callable(responder_flujo))
        self.assertTrue(callable(cerebro_planificador.detectar_intencion_multipaso))
        self.assertTrue(cerebro_planificador.detectar_intencion_multipaso(
            "Crea un archivo notas.txt y luego recuérdame revisarlo"))
        self.assertTrue(callable(agente_confirmacion.solicitar))
        self.assertTrue(callable(acciones.ejecutar))


if __name__ == "__main__":
    unittest.main()
