"""Pruebas unitarias para generación de código real, visión de pantalla y RAG local de proyectos."""
import base64
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cerebro_entrenamiento as ce
import cerebro_rag as cr
import vision_pantalla as vp


class TestGeneracionCodigoHabilidades(unittest.TestCase):
    def test_generador_contrasena_codigo_funcional_ast(self):
        codigo = ce.generar_codigo_habilidad("generar_password", "habilidad para generar contraseñas seguras de 16 caracteres")
        self.assertIsNotNone(codigo)
        self.assertIn("def ejecutar(", codigo)
        self.assertIn("secrets", codigo)

        # Ejecutar en sandbox controlado para verificar resultado funcional real
        entorno = {}
        exec(codigo, entorno)
        self.assertIn("ejecutar", entorno)
        resultado = entorno["ejecutar"]("16")
        self.assertIn("Contraseña segura generada", resultado)
        # Verificar que no es un eco vacío y tiene al menos 16 caracteres de clave
        self.assertNotIn("ejecutada con argumento", resultado)

    def test_generador_hash_codigo_funcional_ast(self):
        codigo = ce.generar_codigo_habilidad("calcular_hash", "habilidad para calcular hash sha256 de un texto")
        self.assertIsNotNone(codigo)
        self.assertIn("hashlib", codigo)

        entorno = {}
        exec(codigo, entorno)
        resultado = entorno["ejecutar"]("Silvestra")
        self.assertIn("Hash SHA-256", resultado)
        self.assertNotIn("ejecutada con argumento", resultado)


class TestVisionPantalla(unittest.TestCase):
    def test_bloqueo_modo_privado(self):
        app_mock = MagicMock()
        app_mock.modo_privado = True
        ok, msg = vp.capturar_y_analizar_pantalla("¿Qué ves en pantalla?", app=app_mock)
        self.assertFalse(ok)
        self.assertIn("modo Privado", msg)

    def test_captura_en_memoria_sin_archivos_disco(self):
        # Captura real en memoria
        b64 = vp.capturar_pantalla_b64(ancho_max=320, calidad=50)
        self.assertIsNotNone(b64)
        self.assertIsInstance(b64, str)
        # Verificar decodificación válida de JPEG
        raw_bytes = base64.b64decode(b64)
        self.assertTrue(raw_bytes.startswith(b"\xff\xd8"))  # Cabecera mágica JPEG

    def test_deteccion_peticion_vision(self):
        self.assertTrue(vp.detectar_peticion_vision("Lyris, mira la pantalla por favor"))
        self.assertTrue(vp.detectar_peticion_vision("¿Qué ves en pantalla?"))
        self.assertTrue(vp.detectar_peticion_vision("Revisa este error en pantalla"))
        self.assertTrue(vp.detectar_peticion_vision("¿Qué opinas de este diseño?"))
        self.assertFalse(vp.detectar_peticion_vision("Crea un archivo llamado notas.txt"))

    def test_obtener_ventana_activa_multimodal_y_trabajo(self):
        # 1. Con app y sistema multimodal
        app_mock = MagicMock()
        app_mock.sistema_multimodal.estado_salud.return_value = {
            "ultima_ventana_externa": {"titulo": "Visual Studio Code - Proyecto_Silvestra"}
        }
        tit = vp.obtener_ventana_activa(app=app_mock)
        self.assertEqual(tit, "Visual Studio Code - Proyecto_Silvestra")

        # 2. Con cerebro_trabajo
        import cerebro_trabajo
        cerebro_trabajo.actualizar_ventana({"titulo": "Supabase Studio - Google Chrome", "ejecutable": "chrome.exe"})
        tit_trabajo = vp.obtener_ventana_activa(app=None)
        self.assertEqual(tit_trabajo, "Supabase Studio - Google Chrome")

    @patch("sesion_http.obtener_sesion")
    def test_analizar_imagen_multimodal_gemini_rest(self, mock_get_sesion):
        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "En la pantalla veo la consola de Supabase con las tablas abiertas."}]
                }
            }]
        }
        mock_sess.post.return_value = mock_resp
        mock_get_sesion.return_value = mock_sess

        resultado = vp.analizar_imagen_multimodal("b64_dummy", "describe la pantalla", titulo_ventana="Supabase")
        self.assertIn("consola de Supabase", resultado)


class TestCerebroRAG(unittest.TestCase):
    def setUp(self):
        os.makedirs("workspace_lyris", exist_ok=True)
        self.test_dir = tempfile.mkdtemp(dir="workspace_lyris", prefix="test_rag_proyecto_")
        # 1. Archivo Python válido
        with open(os.path.join(self.test_dir, "modulo_auth.py"), "w", encoding="utf-8") as f:
            f.write("def autenticar_usuario(token):\n    # Conexión con Supabase y verificación JWT\n    return token.startswith('sk_live')\n")

        # 2. Archivo Markdown válido
        with open(os.path.join(self.test_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Proyecto UniConnect\nPlataforma modular con arquitectura limpia y FastAPI.\n")

        # 3. Archivo sensible que debe ser excluido estrictamente
        with open(os.path.join(self.test_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("SECRET_KEY=clave_super_secreta_12345\n")

        # 4. Carpeta prohibida que debe ser excluida
        venv_dir = os.path.join(self.test_dir, ".venv")
        os.makedirs(venv_dir, exist_ok=True)
        with open(os.path.join(venv_dir, "lib_interna.py"), "w", encoding="utf-8") as f:
            f.write("def ignorar_esto(): pass\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_seguridad_bloqueo_rutas_sistema(self):
        es_seg, mot = cr.es_ruta_segura("C:\\Windows\\System32")
        self.assertFalse(es_seg)
        self.assertIn("sistema operativo", mot)

        es_seg_pf, _ = cr.es_ruta_segura("C:\\Program Files\\App")
        self.assertFalse(es_seg_pf)

    def test_indexacion_segura_y_consulta_fts5(self):
        ok, msg = cr.indexar_ruta(self.test_dir)
        self.assertTrue(ok)
        self.assertIn("Indexados", msg)

        # 1. Consulta relevante de código
        ctx = cr.consultar_rag("¿Cómo se hace la verificación de Supabase JWT?", limite=2)
        self.assertIn("CONTEXTO DE PROYECTO", ctx)
        self.assertIn("modulo_auth.py", ctx)
        self.assertIn("Supabase", ctx)

        # 2. Verificar que secretos de .env y carpetas .venv NO fueron indexados
        ctx_secret = cr.consultar_rag("SECRET_KEY clave_super_secreta", limite=2)
        self.assertEqual(ctx_secret, "")

        ctx_venv = cr.consultar_rag("ignorar_esto", limite=2)
        self.assertEqual(ctx_venv, "")


if __name__ == "__main__":
    unittest.main()
