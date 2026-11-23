"""Regresión: HTTP 410 desactiva modelo y HTTP 401 corta reintentos del proveedor.

Cubre las dos rutas reales (completar y streaming) sin red y sin credenciales
reales: solo se registran los modelos solicitados y los avisos emitidos.
"""
import contextlib
import io
import json
import queue
import threading
import unittest
from unittest.mock import patch

import config
import proveedores
import proveedores_cadenas as pc
import proveedores_stream as ps
import proveedores_validador as pv

GONE = "modelo-retirado"
OK = "modelo-correcto"
OK2 = "modelo-correcto-2"
S1 = "samba-modelo-1"
S2 = "samba-modelo-2"
M404 = "modelo-404"
M429 = "modelo-429"
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


class TestHotfixProveedores401410(unittest.TestCase):
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

    def _candidato_stream(self, nombre, modelos):
        prov = self._prov(nombre, modelos)
        prov["clave"] = "x"  # credencial ficticia mínima, nunca real
        prov["modelos_activos"] = list(modelos)
        return prov

    def _preparar(self, pila, proveedores_cfg, claves, orden):
        pila.enter_context(patch.object(config, "PROVEEDORES", proveedores_cfg))
        pila.enter_context(patch.object(config, "PROVEEDORES_EXTRA", []))
        pila.enter_context(patch.dict(pc.CADENAS_ORDEN, {"charla": list(orden)}))
        for atributo, valor in claves.items():
            pila.enter_context(patch.object(config, atributo, valor))

    @staticmethod
    def _capturar(funcion, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            resultado = funcion(*args, **kwargs)
        return resultado, salida.getvalue()

    @staticmethod
    def _drenar(cola):
        salida = []
        while not cola.empty():
            salida.append(cola.get_nowait())
        return salida

    def _stream(self, candidato, modelos, sesion, avisos):
        cola = queue.Queue()
        with patch.object(ps, "obtener_sesion", lambda: sesion), \
             contextlib.redirect_stdout(io.StringIO()):
            ps._intentar_stream_proveedor(
                candidato, modelos, MENSAJES, 0.2, threading.Event(), cola,
                proveedores.marcar_enfriamiento, avisos.append)
        return self._drenar(cola)

    def test_410_normal_desactiva_modelo_y_no_repite_http(self):
        sesion = Sesion({GONE: Respuesta(410, error="Gone"), OK: Respuesta(200)})
        with contextlib.ExitStack() as pila:
            self._preparar(pila, [self._prov("NVIDIA", [GONE, OK])],
                           {"CLAVE_NVIDIA": "x"}, ["NVIDIA"])
            with patch.object(proveedores, "obtener_sesion", lambda: sesion), \
                 patch.object(proveedores, "_lanzar_reintento", lambda tarea: None):
                resultado, log1 = self._capturar(
                    proveedores.completar, MENSAJES, "charla")
                self._capturar(proveedores.completar, MENSAJES, "charla")

        self.assertEqual(resultado, TEXTO_OK)
        self.assertEqual(sesion.llamadas, [GONE, OK, OK])
        self.assertTrue(pv.esta_desactivado("NVIDIA", GONE))
        self.assertIn("HTTP 410 en NVIDIA", log1)
        self.assertIn("retirado y desactivado", log1)

    def test_410_streaming_desactiva_modelo_y_no_repite_http(self):
        sesion = Sesion({GONE: Respuesta(410, error="Gone"), OK: Respuesta(200)})
        candidato = self._candidato_stream("NVIDIA", [GONE, OK])
        avisos = []

        eventos1 = self._stream(candidato, [GONE, OK], sesion, avisos)
        eventos2 = self._stream(candidato, [GONE, OK], sesion, avisos)

        self.assertEqual(sesion.llamadas, [GONE, OK, OK])
        self.assertTrue(any(e[0] == "fin" for e in eventos1), eventos1)
        self.assertTrue(any(e[0] == "fin" for e in eventos2), eventos2)
        self.assertTrue(pv.esta_desactivado("NVIDIA", GONE))
        self.assertTrue(any("HTTP 410" in m and "retirado y desactivado" in m
                            for m in avisos), avisos)

    def test_401_normal_corta_turno_y_siguientes(self):
        cfg = [self._prov("SambaNova", [S1, S2]), self._prov("NVIDIA", [OK])]
        sesion = Sesion({
            S1: Respuesta(401, texto="detalle-sensible"),
            S2: Respuesta(401, texto="detalle-sensible"),
            OK: Respuesta(200),
        })
        with contextlib.ExitStack() as pila:
            self._preparar(pila, cfg,
                           {"CLAVE_SAMBANOVA": "x", "CLAVE_NVIDIA": "x"},
                           ["SambaNova", "NVIDIA"])
            with patch.object(proveedores, "obtener_sesion", lambda: sesion), \
                 patch.object(proveedores, "_lanzar_reintento", lambda tarea: None):
                resultado1, log1 = self._capturar(
                    proveedores.completar, MENSAJES, "charla")
                resultado2, log2 = self._capturar(
                    proveedores.completar, MENSAJES, "charla")

        self.assertEqual(resultado1, TEXTO_OK)
        self.assertEqual(resultado2, TEXTO_OK)
        self.assertEqual(sesion.llamadas, [S1, OK, OK])
        self.assertTrue(pv.esta_desactivado("SambaNova", S1))
        self.assertTrue(pv.esta_desactivado("SambaNova", S2))
        self.assertIn("HTTP 401 en SambaNova", log1)
        self.assertIn("fuera de rotación", log1)
        self.assertNotIn("detalle-sensible", log1 + log2)

    def test_401_streaming_corta_turno_y_siguientes(self):
        sesion = Sesion({
            S1: Respuesta(401, texto="detalle-sensible"),
            S2: Respuesta(401, texto="detalle-sensible"),
        })
        candidato = self._candidato_stream("SambaNova", [S1, S2])
        avisos = []

        eventos1 = self._stream(candidato, [S1, S2], sesion, avisos)
        eventos2 = self._stream(candidato, [S1, S2], sesion, avisos)

        self.assertEqual(sesion.llamadas, [S1])
        self.assertTrue(any(e[0] == "error" for e in eventos1), eventos1)
        self.assertTrue(any(e[0] == "error" for e in eventos2), eventos2)
        self.assertTrue(pv.esta_desactivado("SambaNova", S2))
        self.assertTrue(any("HTTP 401 en SambaNova" in m and "fuera de rotación" in m
                            for m in avisos), avisos)
        self.assertFalse(any("detalle-sensible" in m for m in avisos), avisos)

        with contextlib.ExitStack() as pila:
            self._preparar(pila, [self._prov("SambaNova", [S1, S2])],
                           {"CLAVE_SAMBANOVA": "x"}, ["SambaNova"])
            self.assertEqual(pc.obtener_candidatos_tarea("charla", {}), [])

    def test_404_y_429_conservan_comportamiento_normal(self):
        sesion = Sesion({
            M404: Respuesta(404, error="No existe"),
            M429: Respuesta(429, error="límite"),
            OK2: Respuesta(200),
        })
        with contextlib.ExitStack() as pila:
            self._preparar(pila, [self._prov("NVIDIA", [M404, M429, OK2])],
                           {"CLAVE_NVIDIA": "x"}, ["NVIDIA"])
            with patch.object(proveedores, "obtener_sesion", lambda: sesion), \
                 patch.object(proveedores, "_lanzar_reintento", lambda tarea: None):
                _, log = self._capturar(proveedores.completar, MENSAJES, "charla")
                self._capturar(proveedores.completar, MENSAJES, "charla")

        self.assertEqual(sesion.llamadas, [M404, M429, OK2, OK2])
        self.assertTrue(pv.esta_desactivado("NVIDIA", M404))
        self.assertFalse(pv.esta_desactivado("NVIDIA", M429))
        self.assertIn(f"NVIDIA::{M429}", proveedores._enfriamientos)
        self.assertIn("HTTP 404 en NVIDIA", log)
        self.assertIn("cerebro 429 en NVIDIA", log)
        self.assertIn("pasando al siguiente modelo de la misma cuenta", log)

    def test_404_y_429_conservan_comportamiento_streaming(self):
        sesion = Sesion({
            M404: Respuesta(404, error="No existe"),
            M429: Respuesta(429, error="límite"),
            OK2: Respuesta(200),
        })
        candidato = self._candidato_stream("NVIDIA", [M404, M429, OK2])
        avisos = []

        eventos = self._stream(candidato, [M404, M429, OK2], sesion, avisos)

        self.assertEqual(sesion.llamadas, [M404, M429, OK2])
        self.assertTrue(any(e[0] == "fin" for e in eventos), eventos)
        self.assertTrue(pv.esta_desactivado("NVIDIA", M404))
        self.assertFalse(pv.esta_desactivado("NVIDIA", M429))
        self.assertIn(f"NVIDIA::{M429}", proveedores._enfriamientos)
        self.assertTrue(any("HTTP 404" in m and "desactivado" in m for m in avisos), avisos)
        self.assertTrue(any("cerebro 429 en NVIDIA" in m
                            and "pasando al siguiente modelo" in m
                            for m in avisos), avisos)


if __name__ == "__main__":
    unittest.main()
