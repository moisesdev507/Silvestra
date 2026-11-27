"""prueba_bienvenida_y_naturalidad.py - Validación de bienvenida persistente y ritmo conversacional adaptable."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import identidad_origen
import live_audio
import live_motor
import live_prompt
import modo_compartido


class TestBienvenidaYNaturalidad(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kaya_test_bienvenida_")
        self.datos_dir = os.path.join(self.temp_dir, "datos")
        os.makedirs(self.datos_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bienvenida_persistente_primer_arranque_y_posteriores(self):
        # 1. En un directorio limpio sin bienvenida completada
        self.assertFalse(live_prompt.bienvenida_ya_completada(base=self.temp_dir))
        self.assertTrue(live_prompt.debe_dar_primer_saludo(base=self.temp_dir))

        # 2. Registrar que la bienvenida se completó
        ok = live_prompt.registrar_bienvenida_completada(base=self.temp_dir)
        self.assertTrue(ok)
        self.assertTrue(live_prompt.bienvenida_ya_completada(base=self.temp_dir))
        self.assertFalse(live_prompt.debe_dar_primer_saludo(base=self.temp_dir))

        # Verificar que el JSON en datos/ tiene el formato esperado
        ruta_json = live_prompt.ruta_estado_bienvenida(base=self.temp_dir)
        self.assertTrue(os.path.isfile(ruta_json))
        with open(ruta_json, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertTrue(datos.get("bienvenida_completada"))

    def test_usuario_previamente_registrado_no_recibe_bienvenida(self):
        # Si el usuario ya tiene perfil y primer_despertar está en False
        ruta_perfil = os.path.join(self.datos_dir, "perfil_usuario.json")
        with open(ruta_perfil, "w", encoding="utf-8") as f:
            json.dump({"nombre": "Carlos", "primer_despertar": False}, f)

        with patch.object(identidad_origen, "ruta_perfil", return_value=ruta_perfil):
            debe = live_prompt.debe_dar_primer_saludo(base=self.temp_dir)
            self.assertFalse(debe)
            # Debe haber guardado automáticamente estado_bienvenida.json
            self.assertTrue(live_prompt.bienvenida_ya_completada(base=self.temp_dir))

    def test_sesion_live_respeta_bienvenida_persistente(self):
        # Simulamos que la bienvenida ya se completó previamente
        live_prompt.registrar_bienvenida_completada(base=self.temp_dir)
        with patch.object(live_prompt, "debe_dar_primer_saludo", return_value=False):
            sesion = live_motor.SesionKayaLive()
            self.assertFalse(sesion._primer_saludo_live)

    def test_bloque_version_compartida_condicional(self):
        with patch.object(modo_compartido, "es_version_compartida", return_value=True):
            bloque_con_saludo = live_prompt._bloque_version_compartida(primer_saludo=True)
            self.assertIn("dé la bienvenida mencionando de forma natural", bloque_con_saludo)

            bloque_sin_saludo = live_prompt._bloque_version_compartida(primer_saludo=False)
            self.assertIn("NO menciones que es una versión compartida ni de prueba", bloque_sin_saludo)
            self.assertNotIn("dé la bienvenida", bloque_sin_saludo)

    def test_guia_vocal_sin_limite_rigido_y_con_ritmo_adaptable(self):
        guia = live_prompt.guia_vocal(primer_saludo=False)
        # No debe contener el límite rígido anterior
        self.assertNotIn("1 o 2 frases cortas", guia)
        # Debe contener la nueva guía de ritmo adaptable
        self.assertIn("Poco / directo", guia)
        self.assertIn("Medio", guia)
        self.assertIn("Bastante / detallado", guia)
        self.assertIn("Tono humano", guia)

    def test_live_audio_prompts_adaptables_y_sin_oraciones_fijas(self):
        # 1. Arranque rápido
        prompt_rapido = live_audio.construir_instruccion_arranque_rapido(
            primer_despertar=False, nombre_usuario="Ana", primer_saludo=False
        )
        self.assertNotIn("1 frase.", prompt_rapido)
        self.assertIn("ritmo natural", prompt_rapido)
        self.assertIn("como alguien que ya te conoce", prompt_rapido)

        # 2. Instrucción sistema completa
        prompt_sistema = live_audio.construir_instruccion_sistema(
            rapido=False, primer_despertar=False, nombre_usuario="Ana", primer_saludo=False
        )
        self.assertNotIn("1 a 2 frases por defecto", prompt_sistema)
        self.assertNotIn("1 o 2 frases cortas", prompt_sistema)
        self.assertIn("Estilo adaptable y hablado", prompt_sistema)
        self.assertIn("expláyate con claridad", prompt_sistema)


if __name__ == "__main__":
    unittest.main()
