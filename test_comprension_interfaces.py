"""18 pruebas de comprension visual de interfaces — Fase 3 Etapa 4."""
from __future__ import annotations

import os
import queue
import tempfile
import threading
import time
import unittest

from PIL import Image

from ui_visual_modelo import (
    TipoComponenteUI, RegionVisualUI, ElementoInterfazVisual,
    FormularioVisualUI, AlertaInterfazUI, MapaInterfazVisual,
)
from ui_visual_analizador import AnalizadorEstructuraUI, sanitizar_nombre_valor
from ui_visual_comparador import ComparadorInterfazVisual
from ui_visual_motor import MotorComprensionInterfaces, ProcesadorInterfazVisual
from percepcion_adaptadores import AdaptadorCapturaPantalla, RegistroAdaptadoresPercepcion
from vision_ocr import MotorOCR


class TestComprensionInterfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def crear(self, nombre="captura.png", texto=""):
        ruta = os.path.join(self.raiz, nombre)
        img = Image.new("RGB", (640, 480), "white")
        img.save(ruta, "PNG")
        img.close()
        return ruta

    def test_1_identificacion_app_ventana_activa(self):
        ruta = self.crear()
        analizador = AnalizadorEstructuraUI()
        mapa = analizador.analizar(ruta, metadatos={
            "hwnd": 42, "aplicacion": "calc.exe",
            "ventana_activa": "Calculadora", "clase": "Calc",
        })
        self.assertEqual(mapa.aplicacion, "calc.exe")
        self.assertEqual(mapa.ventana_activa, "Calculadora")

    def test_2_extraccion_ocr_regiones_orden(self):
        ocr = MotorOCR()
        ocr.registrar_extractor(lambda ruta, idioma: [
            {"texto": "Primero", "region": {"x": 10, "y": 20,
                                            "ancho": 80, "alto": 20}},
            {"texto": "Segundo", "region": {"x": 10, "y": 60,
                                            "ancho": 90, "alto": 20}},
        ])
        mapa = AnalizadorEstructuraUI(motor_ocr=ocr).analizar(
            self.crear(), metadatos={"hwnd": 42, "titulo": "Demo",
                                     "ejecutable": "demo.exe"})
        textos = [e.nombre for e in mapa.elementos if e.origen == "ocr"]
        self.assertEqual(textos, ["Primero", "Segundo"])
        self.assertIsNotNone(mapa.elementos[0].region)

    def test_3_componentes_jerarquia_padre_hijo(self):
        elementos = [
            ElementoInterfazVisual("Panel", TipoComponenteUI.PANEL,
                                   padre="", ruta_control="42"),
            ElementoInterfazVisual("Abrir", TipoComponenteUI.BOTON,
                                   padre="42", ruta_control="42/7"),
        ]
        mapa = MapaInterfazVisual(elementos=elementos)
        self.assertEqual(mapa.elementos[1].padre, "42")
        self.assertEqual(mapa.elementos[0].tipo, TipoComponenteUI.PANEL)

    def test_4_formularios_campos_sensibles(self):
        mapa = MapaInterfazVisual(
            elementos=[
                ElementoInterfazVisual("password", TipoComponenteUI.CAMPO_TEXTO,
                                       valor="secreto", es_sensible=True),
                ElementoInterfazVisual("token", TipoComponenteUI.CAMPO_TEXTO,
                                       valor="1234", es_sensible=True),
            ],
        )
        for campo in mapa.elementos:
            self.assertTrue(campo.valor.startswith("***"))
            self.assertNotIn("secreto", campo.valor)
            self.assertNotIn("1234", campo.valor)

    def test_5_dialogos_alertas_errores(self):
        alerta = AlertaInterfazUI("error", "Error al guardar")
        mapa = MapaInterfazVisual(alertas=[alerta])
        self.assertEqual(mapa.alertas[0].tipo, "error")
        self.assertIn("Error", mapa.alertas[0].texto)

    def test_6_capturas_identicas_y_cambios(self):
        comparador = ComparadorInterfazVisual()
        uno = MapaInterfazVisual(aplicacion="demo", ventana_activa="Uno",
                                 elementos=[ElementoInterfazVisual("OK",
                                                   TipoComponenteUI.BOTON)])
        dos = MapaInterfazVisual(aplicacion="demo", ventana_activa="Uno",
                                 elementos=[ElementoInterfazVisual("OK",
                                                   TipoComponenteUI.BOTON)])
        igual = comparador.comparar(uno, dos)
        self.assertTrue(igual.pantalla_identica)
        tres = MapaInterfazVisual(aplicacion="demo", ventana_activa="Dos",
                                  alertas=[AlertaInterfazUI("error", "Fallo")])
        cambio = comparador.comparar(dos, tres)
        self.assertTrue(cambio.ventana_cambio)
        self.assertGreater(len(cambio.alertas_nuevas), 0)

    def test_7_localizacion_coordenadas_normalizadas(self):
        region = RegionVisualUI(100, 50, 80, 30, 0.15625, 0.104,
                                0.125, 0.0625)
        boton = ElementoInterfazVisual("Aceptar", TipoComponenteUI.BOTON,
                                       region=region)
        self.assertGreaterEqual(region.x_normalizado, 0)
        self.assertLessEqual(region.x_normalizado, 1)
        self.assertEqual(len(boton.region.centro), 2)

    def test_8_respuesta_aplicacion(self):
        motor = MotorComprensionInterfaces()
        mapa = MapaInterfazVisual(aplicacion="notepad.exe")
        motor._cache["m1"] = mapa
        motor._cache_tiempos["m1"] = time.time()
        motor._cache.move_to_end("m1")
        motor._limpiar_vencidos()
        respuesta = motor.responder_pregunta_interfaz("Que aplicacion esta abierta")
        self.assertIn("notepad.exe", respuesta)

    def test_9_respuesta_ventana_menu(self):
        motor = MotorComprensionInterfaces()
        mapa = MapaInterfazVisual(ventana_activa="Editor",
                                  elementos=[ElementoInterfazVisual(
                                      "Archivo", TipoComponenteUI.MENU)])
        motor._cache["m"] = mapa
        motor._cache_tiempos["m"] = time.time()
        self.assertIn("Editor", motor.responder_pregunta_interfaz(
            "Cual es la ventana activa"))
        self.assertIn("Archivo", motor.responder_pregunta_interfaz(
            "Que opciones de menu hay"))

    def test_10_respuesta_botones_sin_accion(self):
        motor = MotorComprensionInterfaces()
        mapa = MapaInterfazVisual(elementos=[
            ElementoInterfazVisual("Aceptar", TipoComponenteUI.BOTON,
                                   region=RegionVisualUI(50, 40, 60, 20,
                                                         0.078, 0.083, 0.094, 0.042))
        ])
        motor._cache["m"] = mapa
        motor._cache_tiempos["m"] = time.time()
        texto = motor.responder_pregunta_interfaz("Donde esta el boton")
        self.assertIn("sin ejecutar acciones", texto)
        self.assertIn("50", texto)

    def test_11_respuesta_formulario_errores(self):
        motor = MotorComprensionInterfaces()
        campo = ElementoInterfazVisual("clave", TipoComponenteUI.CAMPO_TEXTO,
                                       valor="***6", es_sensible=True)
        mapa = MapaInterfazVisual(
            formularios=[FormularioVisualUI("Acceso", [campo])],
            alertas=[AlertaInterfazUI("advertencia", "Datos incompletos")],
        )
        motor._cache["m"] = mapa
        motor._cache_tiempos["m"] = time.time()
        formulario = motor.responder_pregunta_interfaz("Contenido del formulario")
        alertas = motor.responder_pregunta_interfaz("Que errores hay")
        self.assertIn("***", formulario)
        self.assertIn("advertencia", alertas)

    def test_12_sin_captura_y_elemento_inexistente(self):
        motor = MotorComprensionInterfaces()
        self.assertIn("No hay capturas", motor.responder_pregunta_interfaz(
            "Que aplicacion hay"))
        mapa = MapaInterfazVisual()
        motor._cache["m"] = mapa
        motor._cache_tiempos["m"] = time.time()
        self.assertIn("ningun boton", motor.responder_pregunta_interfaz(
            "Donde esta el boton"))

    def test_13_privacidad_ventanas_bloqueadas(self):
        analizador = AnalizadorEstructuraUI()
        mapa = analizador.analizar(self.crear(), metadatos={
            "hwnd": 0, "clase": "Progman", "ventana_activa": "Escritorio",
        })
        self.assertTrue(mapa.protegida)
        limpio, sensible = sanitizar_nombre_valor("api_key", "secreto")
        self.assertTrue(sensible)
        self.assertEqual(limpio, "***7")

    def test_14_remoto_bloqueado(self):
        class Remoto:
            def comprender(self, **kwargs):
                if not kwargs.get("autorizacion_externa", False):
                    return {"error": "ENVIO_EXTERNO_NO_AUTORIZADO"}
                return {"descripcion": "ok"}
        analizador = AnalizadorEstructuraUI(
            proveedor=Remoto(), autorizacion_externa=False,
        )
        mapa = analizador.analizar(self.crear(), metadatos={
            "hwnd": 10, "titulo": "Demo", "aplicacion": "demo.exe",
        })
        self.assertFalse(mapa.protegida)

    def test_15_revision_estatica_sin_ejecutores(self):
        raiz = os.path.dirname(os.path.abspath(__file__))
        for nombre in (
            "ui_visual_modelo.py", "ui_visual_analizador.py",
            "ui_visual_comparador.py", "ui_visual_motor.py",
        ):
            with open(os.path.join(raiz, nombre), "r", encoding="utf-8") as f:
                texto = f.read()
            self.assertNotIn("gui_interaccion", texto)
            self.assertNotIn("procesos_operaciones", texto)
            self.assertNotIn("archivos_operaciones", texto)
        with open(os.path.join(raiz, "ui_visual_motor.py"),
                  "r", encoding="utf-8") as archivo:
            motor_texto = archivo.read()
        self.assertIn("requiere_ejecucion=False", motor_texto)

    def test_16_cancelacion_concurrencia_y_liberacion(self):
        motor = MotorComprensionInterfaces(max_entradas=3)
        errores = []
        def worker(i):
            try:
                motor.analizar_captura(
                    self.crear("c" + str(i) + ".png"),
                    metadatos={"hwnd": i + 1, "titulo": "Demo",
                               "aplicacion": "demo.exe"},
                )
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker, args=(i,))
                 for i in range(4)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(2)
        self.assertEqual(errores, [])
        class Cancelado:
            def is_set(self):
                return True
        mapa = motor.analizar_captura(
            self.crear("cancel.png"),
            metadatos={"hwnd": 99, "titulo": "Demo"},
            token_cancelacion=Cancelado(),
        )
        self.assertIsInstance(mapa, MapaInterfazVisual)
        for mapa_cache in motor._cache.values():
            if isinstance(mapa_cache, tuple):
                mapa_cache = mapa_cache[1]
            serial = repr(mapa_cache)
            self.assertNotIn("numpy", serial)
            self.assertNotIn("PIL.", serial)

    def test_17_integracion_percepcion_cola_contexto(self):
        cola = queue.Queue()
        contexto = type("Contexto", (), {
            "confirmar_contexto": lambda self, *a, **k: None,
        })()
        cerebro = type("Cerebro", (), {"historial": []})()
        motor = MotorComprensionInterfaces(app_cola=cola, cerebro=cerebro,
                                           contexto_motor=contexto)
        mapa = motor.analizar_captura(
            self.crear(), metadatos={"hwnd": 12, "titulo": "Demo",
                                     "aplicacion": "demo.exe"},
        )
        tipo, payload = cola.get_nowait()
        self.assertEqual(tipo, "ui_visual_evento")
        self.assertIn("mapa", payload)
        registro = RegistroAdaptadoresPercepcion()
        registro.registrar("captura_pantalla",
                           ProcesadorInterfazVisual(motor))
        adaptador = AdaptadorCapturaPantalla()
        evento = adaptador.crear_evento(
            "prueba", ruta=self.crear("evento.png"),
        )
        self.assertTrue(registro.obtener("captura_pantalla"))

    def test_18_presupuesto_archivos(self):
        import os
        raiz = os.path.dirname(os.path.abspath(__file__))
        nombres = (
            "ui_visual_modelo.py", "ui_visual_analizador.py",
            "ui_visual_comparador.py", "ui_visual_motor.py",
            "test_comprension_interfaces.py",
        )
        for nombre in nombres:
            ruta = os.path.join(raiz, nombre)
            self.assertLessEqual(os.path.getsize(ruta), 15360)
        traspaso = os.path.join(raiz, "TRASPASO.md")
        self.assertLessEqual(os.path.getsize(traspaso), 6656)


if __name__ == "__main__":
    unittest.main()
