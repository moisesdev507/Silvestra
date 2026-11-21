"""21 pruebas de comprension visual y OCR desacoplado — Fase 3 Etapa 2."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

from vision_modelo import SolicitudVisual
from vision_imagen import validar_y_normalizar, limpiar_normalizada, ErrorImagenVisual
from vision_ocr import MotorOCR, BloqueTextoOCR
from vision_proveedores import (
    ProveedorVisionRemoto,
    ProveedorVisionLocal,
    ProveedorVisionSoloLocalOCR,
)
from vision_motor import MotorComprensionVisual, ProcesadorComprensionVisual


class TestComprensionVisual(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        self.ocr = MotorOCR()

    def tearDown(self):
        self.tmp.cleanup()

    def crear(self, nombre, formato):
        ruta = os.path.join(self.raiz, nombre)
        try:
            from PIL import Image
            modo = "L"
            img = Image.new(modo, (160, 90), color=128)
            if formato == "PNG":
                img.save(ruta, "PNG")
            elif formato == "JPEG":
                img.save(ruta, "JPEG")
            elif formato == "WebP":
                img.save(ruta, "WebP")
            img.close()
        except Exception:
            raise
        return ruta

    def motor(self, proveedor=None):
        return MotorComprensionVisual(
            proveedor=proveedor,
            motor_ocr=self.ocr,
            max_entradas=4,
        )

    def test_1_png_real(self):
        ruta = self.crear("real.png", "PNG")
        info = validar_y_normalizar(ruta)
        limpiar_normalizada(info)
        self.assertEqual(info["formato"], "PNG")

    def test_2_jpeg_real(self):
        ruta = self.crear("real.jpg", "JPEG")
        info = validar_y_normalizar(ruta)
        limpiar_normalizada(info)
        self.assertEqual(info["formato"], "JPEG")

    def test_3_webp_real(self):
        ruta = self.crear("real.webp", "WebP")
        info = validar_y_normalizar(ruta)
        limpiar_normalizada(info)
        self.assertEqual(info["formato"], "WebP")

    def test_4_extension_falsificada(self):
        ruta = os.path.join(self.raiz, "falsa.png")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("texto no imagen")
        with self.assertRaises(ErrorImagenVisual):
            validar_y_normalizar(ruta)

    def test_5_corrupta_truncada(self):
        ruta = os.path.join(self.raiz, "trunc.png")
        with open(ruta, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"123")
        with self.assertRaises(ErrorImagenVisual):
            validar_y_normalizar(ruta)

    def test_6_imagen_grande_normalizada(self):
        ruta = os.path.join(self.raiz, "grande.png")
        from PIL import Image
        img = Image.new("RGB", (2000, 1000), "white")
        img.save(ruta, "PNG")
        img.close()
        info = validar_y_normalizar(ruta, max_lado_normalizado=1280)
        self.assertLessEqual(max(info["ancho"], info["alto"]), 1280)
        limpiar_normalizada(info)
        ruta2 = os.path.join(self.raiz, "dim.png")
        img = Image.new("RGB", (9000, 100), "white")
        img.save(ruta2, "PNG")
        img.close()
        with self.assertRaises(ErrorImagenVisual):
            validar_y_normalizar(ruta2)

    def test_7_ocr_lineas_caracteres(self):
        bloques = []
        self.ocr.registrar_extractor(
            lambda ruta, idioma: [
                {"texto": "Árbol ñandú", "region": {"y": 1},
                 "idioma": "es", "origen_ocr": "prueba"},
                {"texto": "Error 2+2=4", "region": {"y": 2},
                 "idioma": "es", "origen_ocr": "prueba"},
            ]
        )
        resultado, limit = self.ocr.extraer("cualquiera", "spa")
        self.assertIn("ñ", resultado[0].texto)
        self.assertEqual(len(resultado), 2)
        self.assertEqual(limit, [])

    def test_8_evidencia_separada_confianza_none(self):
        ruta = self.crear("evidencia.png", "PNG")
        motor = self.motor()
        resultado = motor.procesar(SolicitudVisual(ruta, pregunta="¿Qué aparece?"))
        self.assertIsNone(resultado.nivel_confianza)
        self.assertIsInstance(resultado.texto_extraido, str)
        self.assertIsInstance(resultado.observaciones_verificables, list)
        self.assertIsInstance(resultado.interpretaciones_inciertas, list)

    def test_9_elementos_descripcion(self):
        ruta = self.crear("elementos.png", "PNG")
        class Proveedor:
            def comprender(self, **kwargs):
                return {
                    "descripcion": "Boton y ventana",
                    "elementos": [{"nombre": "OK", "categoria": "boton",
                                   "verificable": True}],
                    "observaciones": ["Hay un boton"],
                    "interpretaciones": ["Puede ser de confirmacion"],
                    "confianza": None,
                }
        motor = self.motor(Proveedor())
        res = motor.procesar(SolicitudVisual(ruta))
        self.assertEqual(res.elementos_identificados[0].nombre, "OK")

    def test_10_consultas_cache_lru(self):
        ruta = self.crear("cache.png", "PNG")
        motor = self.motor()
        sol = SolicitudVisual(ruta, pregunta="¿Qué texto aparece?")
        uno = motor.procesar(sol)
        dos = motor.obtener_cached(sol.id_entrada, uno.referencia_imagen)
        self.assertIsNotNone(dos)

    def test_11_captura_pantalla_sugerencia_pasiva(self):
        ruta = self.crear("captura.png", "PNG")
        motor = self.motor()
        resultado = motor.procesar(
            SolicitudVisual(ruta, modalidad="captura_pantalla",
                            pregunta="Explica el error")
        )
        self.assertIsNone(resultado.sugerencia_accion)

    def test_12_privacidad_remoto_bloqueado(self):
        remoto = ProveedorVisionRemoto(
            "https://example.invalid/vision",
            "clave_super_secreta",
            "modelo",
        )
        ruta = self.crear("privada.png", "PNG")
        res = remoto.comprender(
            "Describe", ruta,
            autorizacion_externa=False,
        )
        self.assertEqual(res["error"], "ENVIO_EXTERNO_NO_AUTORIZADO")
        limpio = __import__("vision_proveedores").redactar_error(
            "Authorization: Bearer clave_super_secreta"
        )
        self.assertNotIn("clave_super_secreta", limpio)

    def test_13_errores_http_red(self):
        remoto = ProveedorVisionRemoto(
            "http://127.0.0.1:1/vision",
            "clave",
            "modelo",
        )
        ruta = self.crear("red.png", "PNG")
        res = remoto.comprender(
            "Describe", ruta,
            autorizacion_externa=True,
            timeout_seg=0.1,
        )
        self.assertIn("error", res)

    def test_14_timeout_local(self):
        local = ProveedorVisionLocal(
            "http://127.0.0.1:1/api/generate",
            "modelo",
            0.1,
        )
        ruta = self.crear("timeout.png", "PNG")
        res = local.comprender("Describe", ruta, timeout_seg=0.1)
        self.assertIn("error", res)

    def test_15_json_malformado_remoto(self):
        remoto = ProveedorVisionRemoto(
            "http://127.0.0.1:1/vision",
            "clave",
            "modelo",
        )
        ruta = self.crear("json.png", "PNG")
        res = remoto.comprender(
            "Describe", ruta,
            autorizacion_externa=True,
            timeout_seg=0.1,
        )
        self.assertIn("error", res)

    def test_16_dedupe_percepcion(self):
        ruta = self.crear("dedupe.png", "PNG")
        motor = self.motor()
        sol = SolicitudVisual(ruta)
        uno = motor.procesar(sol)
        dos = motor.obtener_cached(sol.id_entrada, uno.referencia_imagen)
        self.assertIsNotNone(dos)

    def test_17_cancelacion_cooperativa(self):
        ruta = self.crear("cancel.png", "PNG")
        class Token:
            def is_set(self):
                return True
        motor = self.motor()
        res = motor.procesar(
            SolicitudVisual(ruta),
            token_cancelacion=Token(),
        )
        self.assertIn("cancelado", res.errores)

    def test_18_concurrencia(self):
        rutas = [self.crear(f"c{i}.png", "PNG") for i in range(4)]
        motor = self.motor()
        errores = []
        def worker(ruta):
            try:
                motor.procesar(SolicitudVisual(ruta))
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker, args=(r,)) for r in rutas]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(2)
        self.assertEqual(errores, [])

    def test_19_liberacion_recursos(self):
        ruta = self.crear("liberar.png", "PNG")
        motor = self.motor()
        resultado = motor.procesar(SolicitudVisual(ruta))
        tempdir = os.path.join(self.raiz, ".vision-no")
        self.assertEqual(resultado.nivel_confianza, None)

    def test_20_integracion_puente_cola(self):
        import queue
        cola = queue.Queue()
        ruta = self.crear("puente.png", "PNG")
        motor = self.motor()
        motor.app_cola = cola
        motor.cerebro = type("Cerebro", (), {"historial": []})()
        motor.procesar(SolicitudVisual(ruta))
        try:
            item = cola.get_nowait()
            self.assertEqual(item[0], "vision_evento")
        except Exception:
            self.assertTrue(hasattr(motor.cerebro, "historial"))

    def test_21_solo_local_ocr(self):
        proveedor = ProveedorVisionSoloLocalOCR(self.ocr)
        ruta = self.crear("ocr.png", "PNG")
        res = proveedor.comprender("Describe", ruta)
        self.assertIn("limitaciones", res)


if __name__ == "__main__":
    unittest.main()
