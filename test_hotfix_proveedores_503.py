"""Regresión: HTTP 503 y fallo total enfrían 75s sin desactivar proveedores.

Sin red y sin credenciales reales: comprueba el salto inmediato al respaldo,
que no se aplica el TPD de 4 horas y que la rotación se recupera al expirar.
"""
import contextlib
import io
import json
import queue
import threading
import time
import unittest
from unittest.mock import patch

import config
import proveedores
import proveedores_cadenas as pc
import proveedores_stream as ps
import proveedores_validador as pv

CAIDO = "modelo-503"
FALLO = "modelo-fallo-total"
OK = "modelo-ok"
TEXTO_OK = "Listo, ya estoy aquí."
MENSAJES = [{"role": "user", "content": "hola"}]


class Respuesta:
    """Respuesta HTTP falsa; nunca guarda ni muestra encabezados de autorización."""

    def __init__(self, codigo, error=None, texto=""):
        self.status_code = codigo
        self.headers = {}
        self.text = texto
        self.encoding = None
        self._error = error

    def json(self):
        if self.status_code == 200:
            return {"choices": [{"message": {"content": TEXTO_OK}}]}
        if self._error is not None:
            return {"error": {"message": self._error}}
        return {}

    def iter_lines(self, decode_unicode=False):
        if self.status_code != 200:
            return
        dato = {"choices": [{"delta": {"content": TEXTO_OK}}]}
        yield ("data: " + json.dumps(dato, ensure_ascii=False)).encode("utf-8")
        yield b"data: [DONE]"


class Sesion:
    """Sesión falsa que solo cuenta a qué modelo se golpeó."""

    def __init__(self, reglas):
        self.reglas = reglas
        self.llamadas = []

    def post(self, url, headers=None, json=None, **kwargs):
        modelo = (json or {}).get("model", "?")
        self.llamadas.append(modelo)
        return self.reglas.get(modelo, Respuesta(200))


class TestHotfixProveedores503(unittest.TestCase):
    def setUp(self):
        pv._modelos_desactivados.clear()
        pv._proveedores_desactivados.clear()
        proveedores._enfriamientos.clear()
        proveedores._claves_anteriores.clear()
        proveedores._aviso_respaldo_pendiente = False
        pc._avisados_clave_vacia.clear()

    @staticmethod
    def _prov(nombre, modelos):
        return {
            "nombre": nombre,
            "base_url": "https://ejemplo.invalid/v1",
            "modelos": list(modelos),
            "modelos_charla": list(modelos),
        }

    def _preparar(self, pila, configuracion, claves, orden):
        pila.enter_context(patch.object(config, "PROVEEDORES", configuracion))
        pila.enter_context(patch.object(config, "PROVEEDORES_EXTRA", []))
        pila.enter_context(patch.dict(pc.CADENAS_ORDEN, {"charla": list(orden)}))
        for atributo, valor in claves.items():
            pila.enter_context(patch.object(config, atributo, valor))

    @staticmethod
    def _capturar(funcion, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            resultado = funcion(*args, **kwargs)
        return resultado, salida.getvalue()

    def _assert_enfriamiento_breve(self, clave):
        fin = proveedores._enfriamientos.get(clave)
        self.assertIsNotNone(fin, clave)
        restante = fin - time.time()
        self.assertGreaterEqual(restante, 60.0, clave)
        self.assertLessEqual(restante, 90.0, clave)

    def test_503_enfria_modelo_y_proveedor_y_salta_al_respaldo(self):
        sesion = Sesion({
            CAIDO: Respuesta(503, error="Service Unavailable"),
            OK: Respuesta(200),
        })
        configuracion = [self._prov("Google", [CAIDO]), self._prov("NVIDIA", [OK])]
        with contextlib.ExitStack() as pila:
            self._preparar(pila, configuracion,
                           {"CLAVE_GOOGLE": "x", "CLAVE_NVIDIA": "x"},
                           ["Google", "NVIDIA"])
            with patch.object(proveedores, "obtener_sesion", lambda: sesion), \
                 patch.object(proveedores, "_lanzar_reintento", lambda tarea: None):
                resultado1, log = self._capturar(proveedores.completar, MENSAJES, "charla")
                sesion.llamadas.clear()
                resultado2, _ = self._capturar(proveedores.completar, MENSAJES, "charla")

                self._assert_enfriamiento_breve("Google")
                self._assert_enfriamiento_breve(f"Google::{CAIDO}")
                vencido = time.time() - 1
                proveedores._enfriamientos["Google"] = vencido
                proveedores._enfriamientos[f"Google::{CAIDO}"] = vencido
                sesion.llamadas.clear()
                resultado3, _ = self._capturar(proveedores.completar, MENSAJES, "charla")

        self.assertEqual(resultado1, TEXTO_OK)
        self.assertEqual(resultado2, TEXTO_OK)
        self.assertEqual(resultado3, TEXTO_OK)
        self.assertEqual(sesion.llamadas, [CAIDO, OK])
        self.assertIn("HTTP 503 en Google", log)
        self.assertIn("enfriamiento breve", log)
        self.assertFalse(pv.esta_desactivado("Google", CAIDO))
        self.assertNotIn("Google", pv._proveedores_desactivados)

    def test_fallo_total_de_modelos_enfria_proveedor_y_salta_al_respaldo(self):
        sesion = Sesion({
            FALLO: Respuesta(500, texto="sobrecarga"),
            OK: Respuesta(200),
        })
        configuracion = [self._prov("Mistral", [FALLO]), self._prov("NVIDIA", [OK])]
        with contextlib.ExitStack() as pila:
            self._preparar(pila, configuracion,
                           {"CLAVE_MISTRAL": "x", "CLAVE_NVIDIA": "x"},
                           ["Mistral", "NVIDIA"])
            with patch.object(proveedores, "obtener_sesion", lambda: sesion), \
                 patch.object(proveedores, "_lanzar_reintento", lambda tarea: None):
                resultado1, log = self._capturar(proveedores.completar, MENSAJES, "charla")
                sesion.llamadas.clear()
                resultado2, _ = self._capturar(proveedores.completar, MENSAJES, "charla")

                self._assert_enfriamiento_breve("Mistral")
                proveedores._enfriamientos["Mistral"] = time.time() - 1
                sesion.llamadas.clear()
                resultado3, _ = self._capturar(proveedores.completar, MENSAJES, "charla")

        self.assertEqual(resultado1, TEXTO_OK)
        self.assertEqual(resultado2, TEXTO_OK)
        self.assertEqual(resultado3, TEXTO_OK)
        self.assertEqual(sesion.llamadas, [FALLO, OK])
        self.assertIn("fallo_total_modelos en Mistral", log)
        self.assertNotIn("Mistral", pv._proveedores_desactivados)

    def test_streaming_503_enfria_y_no_desactiva(self):
        sesion = Sesion({
            CAIDO: Respuesta(503, error="Service Unavailable"),
            OK: Respuesta(200),
        })
        candidato = self._prov("Google", [CAIDO, OK])
        candidato["clave"] = "x"
        candidato["modelos_activos"] = [CAIDO, OK]
        avisos = []

        def ejecutar():
            cola = queue.Queue()
            with patch.object(ps, "obtener_sesion", lambda: sesion), \
                 contextlib.redirect_stdout(io.StringIO()):
                ps._intentar_stream_proveedor(
                    candidato, [CAIDO, OK], MENSAJES, 0.2, threading.Event(),
                    cola, proveedores.marcar_enfriamiento, avisos.append)
            eventos = []
            while not cola.empty():
                eventos.append(cola.get_nowait())
            return eventos

        eventos = ejecutar()
        self.assertEqual(sesion.llamadas, [CAIDO])
        self.assertTrue(any(e[0] == "error" for e in eventos), eventos)
        self._assert_enfriamiento_breve("Google")
        self._assert_enfriamiento_breve(f"Google::{CAIDO}")
        self.assertTrue(any("HTTP 503 en Google" in m for m in avisos), avisos)
        self.assertFalse(pv.esta_desactivado("Google", CAIDO))

        vencido = time.time() - 1
        proveedores._enfriamientos["Google"] = vencido
        proveedores._enfriamientos[f"Google::{CAIDO}"] = vencido
        sesion.llamadas.clear()
        eventos = ejecutar()
        self.assertEqual(sesion.llamadas, [CAIDO])
        self.assertTrue(any(e[0] == "error" for e in eventos), eventos)


if __name__ == "__main__":
    unittest.main()
