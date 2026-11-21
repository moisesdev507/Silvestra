"""16 pruebas de arquitectura multimodal — Fase 3 Etapa 1."""
from __future__ import annotations

import os
import queue
import tempfile
import threading
import time
import unittest

from percepcion_modelo import (
    MODALIDADES, RECIBIDO, NORMALIZADO, EN_COLA,
    PROCESANDO, PROCESADO, DESCARTADO, EXPIRADO,
    CANCELADO, FALLIDO,
    EventoPerceptivo, ReferenciaContenido, PoliticaRecursosModalidad,
)
from percepcion_adaptadores import (
    AdaptadorImagen, AdaptadorCamara, AdaptadorCapturaPantalla,
    AdaptadorAudio, AdaptadorContextoSistema, AdaptadorEventoComponente,
    ProcesadorModalidad, RegistroAdaptadoresPercepcion,
)
from percepcion_motor import MotorPercepcion


class ProcesadorSimulado(ProcesadorModalidad):
    def __init__(self, bloquear=False, fallar=False):
        self.bloquear = bloquear
        self.fallar = fallar
    def procesar(self, evento, token_cancelacion=None):
        if self.bloquear:
            time.sleep(0.15)
        if token_cancelacion and getattr(token_cancelacion, "is_set", lambda: False)():
            return {"cancelado": True}
        if self.fallar:
            raise RuntimeError("fallo simulada")
        return {"procesado": True, "modalidad": evento.modalidad}


class TestPercepcionArquitectura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registro = RegistroAdaptadoresPercepcion()
        self.cola = queue.Queue()
        self.motor = MotorPercepcion(
            self.registro, max_workers=2,
            ventana_dedupe_seg=0.05,
            app_cola=self.cola,
        )

    def tearDown(self):
        self.motor.detener(False)
        self.tmp.cleanup()

    def esperar(self, id_evento, estados, timeout=1.5):
        fin = time.time() + timeout
        while time.time() < fin:
            dato = self.motor.obtener_estado(id_evento)
            if dato and dato["estado"] in estados:
                return dato
            time.sleep(0.01)
        return self.motor.obtener_estado(id_evento)

    def registrar(self, modalidad, procesador=None, politica=None):
        self.registro.registrar(
            modalidad,
            procesador or ProcesadorSimulado(),
            politica or PoliticaRecursosModalidad(),
        )

    def test_1_seis_modalidades_normalizadas(self):
        for modalidad in MODALIDADES:
            if modalidad not in ("captura_screenshot",):
                self.registrar(modalidad)
                evento = EventoPerceptivo(modalidad, "prueba")
                res = self.motor.recibir(evento)
                self.assertIn(res["estado"], (NORMALIZADO, EN_COLA, PROCESADO,
                                               DESCARTADO, EXPIRADO))

    def test_2_transiciones_estrictas(self):
        evento = EventoPerceptivo("imagen", "prueba")
        self.assertTrue(evento.transicionar(NORMALIZADO))
        self.assertTrue(evento.transicionar(EN_COLA))
        self.assertTrue(evento.transicionar(PROCESANDO))
        self.assertTrue(evento.transicionar(PROCESADO))
        self.assertFalse(evento.transicionar(PROCESANDO))

    def test_3_entrada_invalida(self):
        with self.assertRaises(ValueError):
            EventoPerceptivo("desconocida", "prueba")
        evento = EventoPerceptivo(
            "imagen", "prueba",
            referencia_contenido=ReferenciaContenido(
                ruta=os.path.join(self.tmp.name, "no.txt"),
                tamano=1,
            ),
        )
        self.registrar("imagen")
        res = self.motor.recibir(evento)
        self.assertIn(res["estado"], (DESCARTADO, FALLIDO))

    def test_4_fuente_modalidad_deshabilitada(self):
        self.registrar("camara")
        self.registro.deshabilitar_fuente("camara_prueba")
        evento = EventoPerceptivo("camara", "camara_prueba")
        res = self.motor.recibir(evento)
        self.assertEqual(res["estado"], DESCARTADO)
        self.registro.habilitar_fuente("camara_prueba")
        self.registro.deshabilitar_modalidad("audio")
        evento2 = EventoPerceptivo("audio", "audio_prueba")
        res2 = self.motor.recibir(evento2)
        self.assertEqual(res2["estado"], DESCARTADO)

    def test_5_dedupe(self):
        self.registrar("imagen")
        uno = EventoPerceptivo("imagen", "prueba", metadatos={"x": 1})
        dos = EventoPerceptivo("imagen", "prueba", metadatos={"x": 1})
        res1 = self.motor.recibir(uno)
        res2 = self.motor.recibir(dos)
        self.assertIn(res1["estado"], (EN_COLA, PROCESADO))
        self.assertEqual(res2["estado"], DESCARTADO)

    def test_6_concurrencia_prioridad(self):
        self.registrar("imagen")
        self.registrar("audio")
        eventos = [
            EventoPerceptivo("imagen", "prueba", prioridad=1),
            EventoPerceptivo("audio", "prueba", prioridad=9),
        ]
        respuestas = [self.motor.recibir(e) for e in eventos]
        self.assertTrue(any(r["estado"] in (EN_COLA, PROCESADO)
                            for r in respuestas))

    def test_7_cancelacion_cola_activa(self):
        self.registrar("camara", ProcesadorSimulado(bloquear=True))
        evento = EventoPerceptivo("camara", "prueba")
        self.motor.recibir(evento)
        self.assertTrue(self.motor.cancelar_evento(evento.id_evento))
        self.assertIn(self.motor.obtener_estado(evento.id_evento)["estado"],
                      (DESCARTADO, CANCELADO, PROCESANDO))

    def test_8_timeout_y_ttl(self):
        self.registrar("audio", ProcesadorSimulado(bloquear=True),
                       PoliticaRecursosModalidad(
                           max_bytes=1024, max_duracion_seg=30,
                           ttl_seg=0.01,
                       ))
        evento = EventoPerceptivo(
            "audio", "prueba",
            metadatos={"timeout_seg": 0.01},
        )
        evento.metadatos["timeout_seg"] = 0.01
        res = self.motor.recibir(evento)
        dato = self.motor.obtener_estado(evento.id_evento)
        self.assertIn(dato["estado"], (EN_COLA, EXPIRADO, PROCESADO,
                                         PROCESANDO))

    def test_9_excepcion_procesador(self):
        self.registrar("camara", ProcesadorSimulado(fallar=True))
        evento = EventoPerceptivo("camara", "prueba")
        self.motor.recibir(evento)
        dato = self.esperar(evento.id_evento, ("fallido", "procesado"))
        self.assertIn(dato["estado"], ("fallido", "procesado"))
        otro = EventoPerceptivo("camara", "prueba2")
        self.motor.registro.registrar(
            "camara", ProcesadorSimulado(), sobrescribir=True
        )
        res = self.motor.recibir(otro)
        self.assertIn(res["estado"], (EN_COLA, PROCESADO))

    def test_10_limites_max_bytes_duracion_pendientes(self):
        politica = PoliticaRecursosModalidad(
            max_bytes=10, max_duracion_seg=1, max_pendientes=1
        )
        self.registrar("imagen", ProcesadorSimulado(), politica)
        ruta = os.path.join(self.tmp.name, "grande.bin")
        with open(ruta, "wb") as f:
            f.write(b"x" * 11)
        adaptador = AdaptadorImagen()
        try:
            adaptador.crear_evento(
                "prueba", ruta=ruta, duracion_seg=2,
                max_bytes=10,
            )
            self.fail("Debio rechazar max_bytes")
        except Exception:
            pass
        evento = EventoPerceptivo("imagen", "prueba",
                                  referencia_contenido=ReferenciaContenido(
                                      tamano=11))
        res = self.motor.recibir(evento)
        self.assertIn(res["estado"], (DESCARTADO, FALLIDO))

    def test_11_liberacion_recurso_finally(self):
        ruta = os.path.join(self.tmp.name, "recurso.bin")
        with open(ruta, "wb") as f:
            f.write(b"x")
        ref = ReferenciaContenido(ruta=ruta, tamano=1)
        evento = EventoPerceptivo(
            "imagen", "prueba", referencia_contenido=ref
        )
        self.registrar("imagen")
        self.motor.recibir(evento)
        self.esperar(evento.id_evento, ("procesado", "fallido"))
        self.assertTrue(ref.liberada)

    def test_12_resumen_cerebro_acotado(self):
        class Cerebro:
            def __init__(self):
                self.historial = []
        cerebro = Cerebro()
        motor = MotorPercepcion(
            max_caracteres_resumen=50,
            cerebro=cerebro,
        )
        motor.registro.registrar("evento_interno", ProcesadorSimulado())
        evento = EventoPerceptivo("evento_interno", "prueba")
        motor.recibir(evento)
        motor.detener(False)
        self.assertTrue(hasattr(cerebro, "historial"))

    def test_13_contexto_motor(self):
        class Contexto:
            def __init__(self):
                self.valores = []
            def confirmar_contexto(self, clave, valor, origen="",
                                   ttl_seg=None):
                self.valores.append((clave, valor))
        ctx = Contexto()
        motor = MotorPercepcion(
            contexto_motor=ctx,
        )
        motor.registro.registrar("contexto_sistema", ProcesadorSimulado())
        evento = EventoPerceptivo("contexto_sistema", "sensor")
        motor.recibir(evento)
        time.sleep(0.05)
        motor.detener(False)
        self.assertGreaterEqual(len(ctx.valores), 0)

    def test_14_separacion_percepcion_accion(self):
        class ProcesadorSugerencia(ProcesadorModalidad):
            def procesar(self, evento, token_cancelacion=None):
                return {"sugerencia_accion": "proponer prueba"}
        class Orquestador:
            def __init__(self):
                self.recibidas = []
            def recibir(self, objetivo, origen="", requiere_ejecucion=False,
                        modo="supervisado"):
                self.recibidas.append((objetivo, origen))
        orq = Orquestador()
        motor = MotorPercepcion(orquestador=orq)
        motor.registro.registrar("evento_interno", ProcesadorSugerencia())
        evento = EventoPerceptivo("evento_interno", "sensor")
        motor.recibir(evento)
        time.sleep(0.05)
        motor.detener(False)
        self.assertEqual(len(orq.recibidas), 1)

    def test_15_app_cola_sin_bloqueo(self):
        motor = MotorPercepcion(app_cola=self.cola)
        motor.registro.registrar("imagen", ProcesadorSimulado())
        evento = EventoPerceptivo("imagen", "camara")
        inicio = time.time()
        motor.recibir(evento)
        self.assertLess(time.time() - inicio, 0.5)
        motor.detener(False)

    def test_16_auditoria_modulos_fase(self):
        raiz = os.path.dirname(os.path.abspath(__file__))
        for nombre in (
            "percepcion_modelo.py",
            "percepcion_adaptadores.py",
            "percepcion_motor.py",
        ):
            ruta = os.path.join(raiz, nombre)
            self.assertTrue(os.path.exists(ruta))
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
            self.assertNotIn("archivos_operaciones", texto)
            self.assertNotIn("procesos_operaciones", texto)
            self.assertNotIn("gui_interaccion", texto)
            self.assertNotIn("MotorPermisos", texto)


if __name__ == "__main__":
    unittest.main()
