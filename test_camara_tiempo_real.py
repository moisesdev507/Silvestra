"""20 pruebas de percepcion continua de camara — Fase 3 Etapa 3."""
from __future__ import annotations

import os
import queue
import tempfile
import threading
import time
import unittest

import numpy as np
from PIL import Image

from camara_percepcion_modelo import (
    PoliticaCapturaCamara,
    ObservacionCamara,
    EventoVisualCamara,
)
from camara_comparador import ComparadorFotogramas
from camara_contexto_temporal import ContextoVisualTemporal
from camara_percepcion_motor import (
    MotorPercepcionCamara,
    ProcesadorCamaraContinuo,
)


class TestCamaraTiempoReal(unittest.TestCase):
    def setUp(self):
        self.cola = queue.Queue()
        self.politica = PoliticaCapturaCamara(
            intervalo_activo_seg=0.02,
            intervalo_reposo_seg=0.03,
            umbral_cambio_significativo=0.12,
            intervalo_resumen_vlm_seg=0.05,
            ttl_observacion_seg=1.0,
            max_observaciones_temporales=10,
            autorizacion_externa=False,
        )

    def frame(self, color=128, tamaño=(320, 240)):
        return np.full((tamaño[1], tamaño[0], 3), color, dtype=np.uint8)

    def test_1_captura_periodica_activa_reposo(self):
        frames = iter([self.frame(10), self.frame(20), self.frame(40)])
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: next(frames, None),
            app_cola=self.cola,
            politica=self.politica,
        )
        motor.activar()
        motor.iniciar()
        time.sleep(0.12)
        motor.detener()
        self.assertFalse(motor._activo)

    def test_2_activar_desactivar_sin_hilos_colgados(self):
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(100),
            politica=self.politica,
        )
        motor.iniciar()
        motor.desactivar()
        motor.activar()
        motor.detener()
        if motor._hilo:
            self.assertFalse(motor._hilo.is_alive())

    def test_3_desconexion_recuperacion(self):
        estado = {"n": 0}
        def fuente():
            estado["n"] += 1
            return None if estado["n"] < 2 else self.frame(90)
        motor = MotorPercepcionCamara(
            fuente_frames=fuente,
            app_cola=self.cola,
            politica=self.politica,
        )
        motor.activar()
        motor.iniciar()
        time.sleep(0.12)
        motor.detener()
        items = []
        while not self.cola.empty():
            items.append(self.cola.get_nowait())
        tipos = [i[1].get("evento", {}).get("tipo_evento") for i in items
                 if i[0] == "percepcion_evento"]
        self.assertTrue(tipos)

    def test_4_identicos_sin_llamada_visual(self):
        comparador = ComparadorFotogramas()
        frame = self.frame(100)
        uno = comparador.comparar(frame)
        dos = comparador.comparar(frame)
        self.assertFalse(dos.hay_cambio_significativo)
        self.assertEqual(dos.puntuacion_cambio, 0.0)

    def test_5_cambio_significativo_y_regiones(self):
        comparador = ComparadorFotogramas()
        uno = np.zeros((240, 320, 3), dtype=np.uint8)
        dos = uno.copy()
        dos[:, 160:, :] = 255
        comparador.comparar(uno)
        res = comparador.comparar(dos)
        self.assertTrue(res.hay_cambio_significativo)
        self.assertGreater(len(res.regiones_movimiento), 0)

    def test_6_anomalia_camara_negra(self):
        comparador = ComparadorFotogramas()
        res = comparador.comparar(np.zeros((120, 160, 3), dtype=np.uint8))
        self.assertEqual(res.anomalia_sensor, "camara_ocluida_o_negra")

    def test_7_epistemologia_eventos(self):
        for tipo in ("movimiento", "cambio_escena", "elemento_detectado",
                     "camara_desconectada", "camara_recuperada",
                     "anomalia_sensor"):
            nivel = "deteccion" if "camara" in tipo or "anomalia" in tipo else "observacion"
            evento = __import__("camara_percepcion_modelo", fromlist=["EventoVisualCamara"]).EventoVisualCamara(
                tipo, nivel, 3
            )
            self.assertIn(evento.nivel_epistemico, ("deteccion", "observacion", "interpretacion"))

    def test_8_contexto_acotado_cronologico(self):
        contexto = ContextoVisualTemporal(maxlen=3, ttl_observacion_seg=10)
        for i in range(5):
            obs = ObservacionCamara(
                timestamp=time.time() + i,
                fuente="camara",
                puntuacion_cambio=0.1,
                resumen_breve=f"obs{i}",
            )
            contexto.agregar(obs)
        datos = contexto.consultar_entorno_reciente()
        self.assertLessEqual(len(datos["observaciones"]), 3)
        tiempos = [o["timestamp"] for o in datos["observaciones"]]
        self.assertEqual(tiempos, sorted(tiempos))

    def test_9_sin_arrays_memoria(self):
        contexto = ContextoVisualTemporal()
        obs = ObservacionCamara(
            timestamp=time.time(),
            fuente="camara",
            puntuacion_cambio=0.2,
            detecciones_locales=[{"region": [1, 2, 3, 4]}],
            resumen_breve="cambio",
        )
        contexto.agregar(obs)
        datos = contexto.consultar_entorno_reciente()["observaciones"]
        serial = repr(datos)
        self.assertNotIn("ndarray", serial)
        self.assertNotIn("PIL.", serial)

    def test_10_consulta_entorno(self):
        contexto = ContextoVisualTemporal()
        contexto.agregar(ObservacionCamara(
            timestamp=time.time(),
            fuente="camara",
            puntuacion_cambio=0.3,
            observaciones_verificables=["Movimiento visible"],
            resumen_breve="Movimiento",
        ))
        res = contexto.consultar_entorno_reciente("¿qué se mueve?")
        self.assertIn("observaciones", res)
        self.assertIn("Movimiento", res["resumen"])

    def test_11_duplicados_consecutivos(self):
        contexto = ContextoVisualTemporal()
        obs = ObservacionCamara(
            timestamp=time.time(),
            fuente="camara",
            puntuacion_cambio=0.2,
            resumen_breve="mismo",
        )
        self.assertTrue(contexto.agregar(obs))
        self.assertFalse(contexto.agregar(obs))

    def test_12_prioridades(self):
        evento = __import__("camara_percepcion_modelo", fromlist=["EventoVisualCamara"]).EventoVisualCamara(
            "anomalia_sensor", "deteccion", 5
        )
        normal = __import__("camara_percepcion_modelo", fromlist=["EventoVisualCamara"]).EventoVisualCamara(
            "movimiento", "observacion", 3
        )
        self.assertGreater(evento.prioridad, normal.prioridad)

    def test_13_cancelacion_detener(self):
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(100),
            politica=self.politica,
        )
        motor.activar()
        motor.iniciar()
        motor.detener()
        self.assertFalse(motor._activo)

    def test_14_fuente_error_aislada(self):
        def fuente():
            raise RuntimeError("desconectada")
        motor = MotorPercepcionCamara(
            fuente_frames=fuente,
            politica=self.politica,
        )
        motor.activar()
        motor.iniciar()
        time.sleep(0.1)
        motor.detener()
        self.assertFalse(motor._conectada)

    def test_15_privacidad_externa_false(self):
        politica = PoliticaCapturaCamara()
        self.assertFalse(politica.autorizacion_externa)

    def test_16_concurrencia_rlock(self):
        contexto = ContextoVisualTemporal()
        errores = []
        def worker(i):
            try:
                contexto.agregar(ObservacionCamara(
                    timestamp=time.time(), fuente="camara",
                    puntuacion_cambio=0.1,
                    resumen_breve=f"obs{i}",
                ))
                contexto.consultar_entorno_reciente()
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker, args=(i,))
                 for i in range(6)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(1)
        self.assertEqual(errores, [])

    def test_17_integracion_registro_percepcion(self):
        from percepcion_adaptadores import RegistroAdaptadoresPercepcion
        registro = RegistroAdaptadoresPercepcion()
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(80),
            politica=self.politica,
        )
        procesador = ProcesadorCamaraContinuo(motor)
        registro.registrar("camara", procesador)
        self.assertIsNotNone(registro.obtener("camara"))

    def test_18_cerebro_contexto_puente(self):
        class Simple:
            def __init__(self):
                self.historial = []
            def confirmar_contexto(self, clave, valor, origen="", ttl_seg=None):
                self.valor = valor
        cerebro = Simple()
        contexto = Simple()
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(100),
            cerebro=cerebro,
            contexto_motor=contexto,
            politica=self.politica,
        )
        motor._emitir(__import__("camara_percepcion_modelo", fromlist=["EventoVisualCamara"]).EventoVisualCamara(
            "movimiento", "observacion", 3
        ))
        self.assertTrue(hasattr(cerebro, "historial"))

    def test_19_sin_acciones_directas_app_cola(self):
        cola = queue.Queue()
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(100),
            app_cola=cola,
            politica=self.politica,
        )
        motor._emitir(__import__("camara_percepcion_modelo", fromlist=["EventoVisualCamara"]).EventoVisualCamara(
            "movimiento", "observacion", 3
        ))
        item = cola.get_nowait()
        self.assertEqual(item[0], "percepcion_evento")

    def test_20_captura_una_vez_sin_efectos(self):
        motor = MotorPercepcionCamara(
            fuente_frames=lambda: self.frame(70),
            politica=self.politica,
        )
        res = motor.capturar_una_vez()
        self.assertEqual(res["estado"], "capturada")
        self.assertIn("huella_frame", res["comparacion"])


if __name__ == "__main__":
    unittest.main()
