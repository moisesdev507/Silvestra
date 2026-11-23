"""Regresión: Groq no inyecta IDs 404 y el validador descarta los ausentes.

Sin red real: se falsifica GET /models y se comprueba que el primer turno no
intente modelos que no existen, sin romper proveedores sin ese endpoint.
"""
import contextlib
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import config
import proveedores_cadenas as pc
import proveedores_validador as pv

QWEN = "qwen/qwen3.8-27b"
GPT = "openai/gpt-oss-20b"
RAPIDO = "llama-3.1-8b-instant"
RAPIDO2 = "llama-3.3-70b-versatile"
AUSENTE = "modelo-404-del-catalogo"
VALIDO = "modelo-valido"
TAREAS = ("charla", "razonamiento", "vision")


class Catalogo:
    """Respuesta falsa de GET /models; nunca guarda credenciales."""

    def __init__(self, ids=None, codigo=200):
        self.ids = list(ids or [])
        self.status = codigo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"data": [{"id": m} for m in self.ids]}).encode("utf-8")


class FallaModels:
    """urlopen falso para proveedores que no exponen /models o están caídos."""

    def __init__(self, error):
        self.error = error

    def __call__(self, req, timeout=None):
        raise self.error


class TestHotfixProveedores404(unittest.TestCase):
    def setUp(self):
        pv._modelos_desactivados.clear()
        pv._proveedores_desactivados.clear()
        pc._avisados_clave_vacia.clear()

    @staticmethod
    def _prov(nombre, modelos, tareas=("charla",)):
        prov = {
            "nombre": nombre,
            "base_url": "https://ejemplo.invalid/v1",
            "clave": "credencial-ficticia",
            "modelos": list(modelos),
        }
        for tarea in tareas:
            prov[f"modelos_{tarea}"] = list(modelos)
        return prov

    def _preparar(self, pila, configuracion, tareas=("charla",)):
        pila.enter_context(patch.object(config, "PROVEEDORES", configuracion))
        pila.enter_context(patch.object(config, "PROVEEDORES_EXTRA", []))
        pila.enter_context(patch.object(config, "CLAVE", "x"))
        pila.enter_context(patch.dict(
            pc.CADENAS_ORDEN, {tarea: [configuracion[0]["nombre"]] for tarea in tareas}))

    def test_groq_no_inyecta_rapidos_ausentes_y_conserva_candidatos(self):
        prov = self._prov("Groq", [QWEN, GPT])
        with contextlib.ExitStack() as pila:
            self._preparar(pila, [prov])
            mods = pc.obtener_modelos_tarea(prov, "charla")
            candidatos = pc.obtener_candidatos_tarea("charla", {})

        self.assertEqual(mods, [QWEN, GPT])
        self.assertNotIn(RAPIDO, mods)
        self.assertNotIn(RAPIDO2, mods)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["modelos_activos"], [QWEN, GPT])

    def test_groq_prioriza_rapidos_si_estan_configurados(self):
        prov = self._prov("Groq", [QWEN, RAPIDO2, GPT, RAPIDO])
        mods = pc.obtener_modelos_tarea(prov, "charla")
        self.assertEqual(mods, [RAPIDO, RAPIDO2, QWEN, GPT])

    def test_groq_solo_usa_respaldo_sin_modelos_configurados(self):
        prov = self._prov("Groq", [])
        self.assertEqual(pc.obtener_modelos_tarea(prov, "charla"), [RAPIDO, RAPIDO2])

        prov["modelos_vision"] = [VALIDO]
        self.assertEqual(pc.obtener_modelos_tarea(prov, "charla"), [])

    def test_validador_desactiva_ausentes_de_la_lista_efectiva(self):
        prov = self._prov("Groq", [VALIDO, AUSENTE, QWEN], TAREAS)

        def urlopen(req, timeout=None):
            self.assertTrue(req.full_url.endswith("/models"), req.full_url)
            return Catalogo([VALIDO, QWEN])

        with contextlib.ExitStack() as pila:
            pila.enter_context(patch.object(pv.urllib.request, "urlopen", urlopen))
            with contextlib.redirect_stdout(io.StringIO()):
                pv.validar_proveedor(prov)
            self._preparar(pila, [prov], TAREAS)
            candidatos = {
                t: pc.obtener_candidatos_tarea(t, {}) for t in TAREAS
            }

        self.assertTrue(pv.esta_desactivado("Groq", AUSENTE))
        self.assertFalse(pv.esta_desactivado("Groq", VALIDO))
        for tarea, lista in candidatos.items():
            activos = lista[0]["modelos_activos"]
            self.assertNotIn(AUSENTE, activos, tarea)
            self.assertEqual(activos, [VALIDO, QWEN], tarea)

    def test_validador_desactiva_rapido_configurado_ausente(self):
        prov = self._prov("Groq", [RAPIDO, QWEN])
        urlopen = lambda req, timeout=None: Catalogo([QWEN])

        with contextlib.ExitStack() as pila:
            pila.enter_context(patch.object(pv.urllib.request, "urlopen", urlopen))
            with contextlib.redirect_stdout(io.StringIO()):
                pv.validar_proveedor(prov)
            self._preparar(pila, [prov])
            candidatos = pc.obtener_candidatos_tarea("charla", {})

        self.assertTrue(pv.esta_desactivado("Groq", RAPIDO))
        self.assertEqual(candidatos[0]["modelos_activos"], [QWEN])

    def test_validador_no_rompe_proveedores_sin_endpoint_models(self):
        prov = self._prov("Groq", [VALIDO, AUSENTE])
        urlopens = (
            FallaModels(urllib.error.URLError("sin soporte")),
            lambda req, timeout=None: Catalogo(codigo=404),
        )
        for urlopen in urlopens:
            with self.subTest(urlopen=type(urlopen).__name__):
                with patch.object(pv.urllib.request, "urlopen", urlopen):
                    with contextlib.redirect_stdout(io.StringIO()):
                        pv.validar_proveedor(prov)
                self.assertFalse(pv.esta_desactivado("Groq", VALIDO))
                self.assertFalse(pv.esta_desactivado("Groq", AUSENTE))
                with contextlib.ExitStack() as pila:
                    self._preparar(pila, [prov])
                    candidatos = pc.obtener_candidatos_tarea("charla", {})
                self.assertEqual(candidatos[0]["modelos_activos"], [VALIDO, AUSENTE])


if __name__ == "__main__":
    unittest.main()
