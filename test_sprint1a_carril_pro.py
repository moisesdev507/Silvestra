"""Pruebas del Sprint 1A: carril Pro verificado, clasificación unificada y tokens."""
import os
import sys
import unittest
from unittest.mock import patch

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import cerebro_dificultad as cd
import cerebro_enrutador as ce
import cerebro_enrutador_pro as cep
import proveedores_cadenas as pc

SIN_ENTORNO_PRO = {
    "NVIDIA_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "GROQ_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "GITHUB_TOKEN": "",
    "PRO_API_KEY": "",
    "PRO_MODELO": "",
    "PRO_BASE_URL": "",
}


def _sin_claves_config():
    return (
        patch.object(cep.config, "CLAVE_NVIDIA", ""),
        patch.object(cep.config, "CLAVE_OPENROUTER", ""),
        patch.object(cep.config, "CLAVE", ""),
        patch.object(cep.config, "CLAVE_GOOGLE", ""),
        patch.object(cep.config, "CLAVE_GITHUB", ""),
        patch.dict(os.environ, SIN_ENTORNO_PRO),
    )


class TestClasificacionUnificada(unittest.TestCase):
    def test_codigo_es_razonamiento(self):
        self.assertEqual(
            cd.clasificar_dificultad("def suma(a, b):\n    return a + b\n# revisa el bug"),
            "razonamiento",
        )

    def test_charla_cotidiana(self):
        self.assertEqual(cd.clasificar_dificultad("hola, ¿qué tal tu día?"), "charla")

    def test_prompt_complejo_elige_pro(self):
        texto = (
            "Necesito que analices la arquitectura de mi base de datos SQL y optimices "
            "las consultas del backend porque el rendimiento del endpoint se degradó "
            "tras el último refactor del servicio."
        )
        carril, motivo = cd.decidir_carril(texto, pro_disponible=True)
        self.assertEqual(carril, "pro")
        self.assertTrue(motivo)

    def test_sin_pro_configurado_siempre_rapido(self):
        texto = "analiza a fondo la arquitectura y optimiza el algoritmo"
        carril, motivo = cd.decidir_carril(texto, pro_disponible=False)
        self.assertEqual((carril, motivo), ("rapido", "sin_pro_configurado"))

    def test_saludo_corto_rapido_aunque_haya_pro(self):
        self.assertEqual(cd.decidir_carril("hola", pro_disponible=True)[0], "rapido")

    def test_peticion_explicita_pro(self):
        carril, motivo = cd.decidir_carril(
            "piénsalo bien: ¿conviene migrar a otra base de datos?", pro_disponible=True
        )
        self.assertEqual(carril, "pro")
        self.assertEqual(motivo, "solicitud_explicita_usuario")

    def test_enrutador_delega_en_dificultad(self):
        texto = "analiza a fondo el rendimiento del backend y propone una optimización"
        self.assertEqual(
            ce.decidir_carril(texto, pro_disponible=True),
            cd.decidir_carril(texto, pro_disponible=True),
        )


class TestCadenaPro(unittest.TestCase):
    def test_cadena_tiene_modelos_verificados(self):
        cadena = cep.obtener_cadena_pro()
        self.assertGreaterEqual(len(cadena), 3)
        self.assertEqual(cadena[0]["modelo"], "nvidia/nemotron-3-ultra-550b-a55b")

    def test_cadena_no_contiene_ids_muertos(self):
        modelos = [e["modelo"] for e in cep.obtener_cadena_pro()]
        for muerto in (
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "meta/llama-3.3-70b-instruct",
            "deepseek/deepseek-r1:free",
        ):
            self.assertNotIn(muerto, modelos)

    def test_verificar_pro_con_clave_openrouter(self):
        with patch.object(cep.config, "CLAVE_NVIDIA", ""), \
             patch.object(cep.config, "CLAVE_OPENROUTER", "clave-de-prueba"), \
             patch.object(cep.config, "CLAVE", ""), \
             patch.object(cep.config, "CLAVE_GOOGLE", ""), \
             patch.object(cep.config, "CLAVE_GITHUB", ""), \
             patch.dict(os.environ, SIN_ENTORNO_PRO):
            self.assertTrue(cep.verificar_pro_disponible())

    def test_verificar_pro_sin_claves(self):
        parches = _sin_claves_config()
        for p in parches:
            p.start()
        try:
            self.assertFalse(cep.verificar_pro_disponible())
        finally:
            for p in parches:
                p.stop()

    def test_env_override_gana_a_config(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "clave-entorno"}), \
             patch.object(cep.config, "CLAVE_NVIDIA", ""), \
             patch.object(cep.config, "CLAVE_OPENROUTER", ""), \
             patch.object(cep.config, "CLAVE_GOOGLE", ""), \
             patch.object(cep.config, "CLAVE_GITHUB", ""):
            cadena = cep.obtener_cadena_pro()
            self.assertEqual(len(cadena), 1)
            self.assertEqual(cadena[0]["clave"], "clave-entorno")


class _Respuesta:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class _SesionFalsa:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.llamadas.append(json.get("model"))
        item = self.respuestas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestFallbackPro(unittest.TestCase):
    def test_completar_pro_cae_al_siguiente(self):
        cadena = [
            {"proveedor": "A", "base_url": "https://a.example/v1", "modelo": "muerto", "clave": "x", "stream": True},
            {"proveedor": "B", "base_url": "https://b.example/v1", "modelo": "vivo", "clave": "y", "stream": True},
        ]
        sesion = _SesionFalsa([
            _Respuesta(500),
            _Respuesta(200, {"choices": [{"message": {"content": "respuesta buena"}}]}),
        ])
        with patch.object(cep, "obtener_cadena_pro", return_value=cadena), \
             patch("sesion_http.obtener_sesion", return_value=sesion):
            texto = cep.completar_pro([{"role": "user", "content": "hola"}])
        self.assertEqual(texto, "respuesta buena")
        self.assertEqual(sesion.llamadas, ["muerto", "vivo"])

    def test_completar_pro_sin_cadena_falla_claro(self):
        with patch.object(cep, "obtener_cadena_pro", return_value=[]):
            with self.assertRaises(RuntimeError):
                cep.completar_pro([{"role": "user", "content": "hola"}])

    def test_completar_pro_flujo_sin_streaming_falla_claro(self):
        cadena = [
            {"proveedor": "GitHub", "base_url": "https://x/v1", "modelo": "m", "clave": "k", "stream": False},
        ]
        with patch.object(cep, "obtener_cadena_pro", return_value=cadena):
            with self.assertRaises(RuntimeError):
                cep.completar_pro_flujo([{"role": "user", "content": "hola"}])


class TestTokensYModelos(unittest.TestCase):
    def test_max_tokens_por_carril(self):
        self.assertEqual(pc.resolver_max_tokens("charla", "rapido"), 500)
        self.assertEqual(pc.resolver_max_tokens("charla", "pro"), 1500)
        self.assertEqual(pc.resolver_max_tokens("razonamiento", "rapido"), 1500)
        self.assertEqual(pc.resolver_max_tokens("fondo", "rapido"), 800)

    def test_groq_prioriza_modelos_vivos(self):
        prov = {
            "nombre": "Groq",
            "modelos": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
            "modelos_charla": ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"],
        }
        with patch("proveedores_validador.esta_desactivado", return_value=False):
            mods = pc.obtener_modelos_tarea(prov, "charla")
        self.assertEqual(mods[0], "openai/gpt-oss-120b")
        self.assertEqual(set(mods), set(prov["modelos_charla"]))

    def test_groq_excluye_desactivados(self):
        prov = {
            "nombre": "Groq",
            "modelos": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
        }
        with patch("proveedores_validador.esta_desactivado", side_effect=lambda n, m: m == "qwen/qwen3.8-27b"):
            mods = pc.obtener_modelos_tarea(prov, "charla")
        self.assertEqual(mods, ["openai/gpt-oss-120b"])

    def test_completar_acepta_max_tokens(self):
        import inspect
        import proveedores
        sig = inspect.signature(proveedores.completar)
        self.assertIn("max_tokens", sig.parameters)
        self.assertIn("carril", sig.parameters)

    def test_timeout_rapido_menor_que_pro(self):
        import proveedores_stream as ps
        self.assertLess(ps.LIMITE_RAPIDO, ps.LIMITE_PRO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
