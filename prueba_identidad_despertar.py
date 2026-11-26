"""Identidad raíz de Kaya y primer despertar con paridad Live/clásica."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cerebro_prompt
import habla_espontanea
import identidad_origen
import live_audio
import live_motor
import nacimiento
import onboarding_qt
import persistencia_segura
import saludo_dinamico
import tts_aura_stream
import voz_rapida

CLAVES_PRUEBA = {
    "GEMINI_API_KEY": "AIzaFakeKeyParaPruebas123456789012345",
    "GROQ_API_KEY": "gsk_FakeGroqKeyParaPruebas1234567890",
    "DEEPGRAM_API_KEY": "0123456789abcdef0123456789abcdef01234567",
}


class _ContextoLive:
    """Contexto asíncrono mínimo para client.aio.live.connect."""

    def __init__(self, sesion):
        self.sesion = sesion

    async def __aenter__(self):
        return self.sesion

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ClienteLive:
    def __init__(self, sesion):
        self.sesion = sesion
        self.aio = MagicMock()
        self.aio.live.connect = MagicMock(return_value=_ContextoLive(sesion))


class IdentidadDespertarTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = self.temporal.name
        self.perfil = os.path.join(self.base, "datos", "perfil_usuario.json")
        self.ruta_env = os.path.join(self.base, ".env")

    def tearDown(self):
        self.temporal.cleanup()

    def _ruta_parcheada(self):
        return patch.object(identidad_origen, "ruta_perfil", return_value=self.perfil)

    def test_identidad_en_prompts_de_ambos_motores(self):
        textos = (
            cerebro_prompt.SOBRE_MI,
            live_audio.construir_instruccion_sistema(),
            live_audio.construir_instruccion_arranque_rapido(),
        )
        for texto in textos:
            self.assertIn(identidad_origen.NOMBRE, texto)
            self.assertIn(identidad_origen.CREADOR, texto)
            self.assertIn(identidad_origen.FECHA_INICIO, texto)
            self.assertIn(identidad_origen.prompt_identidad(), texto)

        self.assertIn("datos/perfil_usuario.json", cerebro_prompt.SOBRE_MI)
        self.assertIn("datos/perfil_usuario.json", textos[1])
        self.assertIn("revisar_pantalla", textos[1])
        self.assertIn("revisar_pantalla", textos[2])
        self.assertLess(len(textos[2]), 800)
        self.assertTrue(all(
            "Lyris" not in frase
            for frases in saludo_dinamico.FALLBACKS_FRANJAS.values()
            for frase in frases
        ))

    def test_distincion_creador_y_usuario_actual(self):
        with self._ruta_parcheada():
            self.assertTrue(identidad_origen.preparar_perfil_usuario("Alex"))
            self.assertEqual(identidad_origen.nombre_usuario(), "Alex")
            saludo = identidad_origen.saludo_primer_despertar()
            instruccion = identidad_origen.instruccion_primer_despertar()
        self.assertIn("Alex", saludo)
        self.assertIn("Alex", instruccion)
        for texto in (saludo, instruccion):
            self.assertIn(identidad_origen.CREADOR, texto)
            self.assertIn(identidad_origen.FECHA_INICIO, texto)
        self.assertIn("nunca lo llames creador", identidad_origen.BLOQUE_IDENTIDAD)
        self.assertIn("datos/perfil_usuario.json", identidad_origen.BLOQUE_IDENTIDAD)

    def test_onboarding_marca_despertar_solo_en_perfil_nuevo(self):
        with patch.dict(os.environ):
            ok, mensaje = onboarding_qt.guardar_configuracion(
                "Alex", CLAVES_PRUEBA, base=self.base, ruta_env=self.ruta_env)
        self.assertTrue(ok, mensaje)
        with self._ruta_parcheada():
            self.assertTrue(identidad_origen.primer_despertar_activo())
            identidad_origen.guardar_primer_despertar(False)
            with patch.dict(os.environ):
                onboarding_qt.guardar_configuracion(
                    "Alex", CLAVES_PRUEBA, base=self.base, ruta_env=self.ruta_env)
            self.assertFalse(identidad_origen.primer_despertar_activo())
            self.assertEqual(identidad_origen.nombre_usuario(), "Alex")

    def test_despertar_clasico_dispara_una_sola_vez(self):
        with self._ruta_parcheada():
            identidad_origen.preparar_perfil_usuario("Alex")
            app = MagicMock()
            app.coordinador_live.es_modo_principal.return_value = False
            with patch("habla_espontanea.generar_saludo_espontaneo") as generar:
                nacimiento.saludar(app)
                nacimiento.saludar(app)
                generar.assert_called_once()

        self.assertEqual(app.cola.put.call_count, 1)
        evento = app.cola.put.call_args[0][0]
        self.assertEqual(evento[0], "saludo_inicial")
        saludo = evento[1][0]
        self.assertIn("Alex", saludo)
        self.assertIn(identidad_origen.CREADOR, saludo)
        self.assertIn(identidad_origen.FECHA_INICIO, saludo)
        with self._ruta_parcheada():
            self.assertFalse(identidad_origen.primer_despertar_activo())

    def test_despertar_live_consume_flag_y_personaliza_primer_turno(self):
        sesion_falsa = MagicMock()
        sesion_falsa.send_client_content = AsyncMock()
        cliente = _ClienteLive(sesion_falsa)
        captura = {}

        def _config(**kwargs):
            captura.update(kwargs)
            return kwargs

        with self._ruta_parcheada():
            identidad_origen.preparar_perfil_usuario("Alex")
            sesion = live_motor.SesionKayaLive(
                orden_inicial="¡Hola Kaya! Ya encendió el equipo, saluda breve.")
            sesion.activo = True

            async def _receive_vacio():
                sesion.activo = False
                if False:
                    yield None

            sesion_falsa.receive = MagicMock(return_value=_receive_vacio())
            sesion._tarea_envio_audio = AsyncMock()
            sesion._tarea_watchdog = AsyncMock()
            with patch.object(live_motor.live_audio, "obtener_api_key", return_value="clave-falsa"), \
                 patch.object(live_motor.live_herramientas,
                              "declarar_declaraciones_herramientas", return_value=[]), \
                 patch.object(live_motor.live_herramientas, "registrar_callback_reposo"), \
                 patch.object(live_motor.types, "LiveConnectConfig", side_effect=_config), \
                 patch.object(live_motor.genai, "Client", return_value=cliente):
                asyncio.run(sesion._ejecutar_sesion())

        instruccion = captura["system_instruction"].parts[0].text
        primer_turno = sesion_falsa.send_client_content.call_args.kwargs["turns"].parts[0].text
        for texto in (instruccion, primer_turno):
            self.assertIn("Alex", texto)
            self.assertIn(identidad_origen.CREADOR, texto)
            self.assertIn(identidad_origen.FECHA_INICIO, texto)
        with self._ruta_parcheada():
            self.assertFalse(identidad_origen.primer_despertar_activo())

    def test_usuario_abrahan_nunca_se_confunde_con_kaya(self):
        esperado = (
            "Tu nombre es Kaya. Eres una asistente de inteligencia artificial creada por "
            "Moisés Abrahan Guerrero Reyes el martes 17 de noviembre de 2026 en Panamá. "
            "El usuario con el que estás hablando actualmente se llama Abrahan. "
            "NUNCA digas que eres Abrahan ni que eres tu creador; "
            "tú eres Kaya y te diriges a Abrahan."
        )
        self.assertEqual(identidad_origen.prompt_identidad("Abrahan"), esperado)

        class MemoriaCorrupta:
            nombre = "Abrahan"  # valor legado que antes se copiaba del usuario
            creador = "Abrahan"
            proposito = "ayudarte"
            hechos = []

        with self._ruta_parcheada():
            identidad_origen.preparar_perfil_usuario("Abrahan")
            textos = (
                identidad_origen.bloque_identidad(identidad_origen.nombre_usuario()),
                identidad_origen.instruccion_primer_despertar(),
                identidad_origen.saludo_primer_despertar(),
                live_audio.construir_instruccion_sistema(nombre_usuario="Abrahan"),
                live_audio.construir_instruccion_arranque_rapido(nombre_usuario="Abrahan"),
                cerebro_prompt.construir_prompt(MemoriaCorrupta()),
            )
        prompts_sistema = (textos[0], textos[3], textos[4], textos[5])
        for texto in prompts_sistema:
            self.assertIn("Tu nombre es Kaya", texto)
            self.assertIn("se llama Abrahan", texto)
            self.assertIn("NUNCA digas que eres Abrahan", texto)
            self.assertIn("tú eres Kaya y te diriges a Abrahan", texto)
            self.assertIn("Moisés Abrahan Guerrero Reyes", texto)
            self.assertIn("martes 17 de noviembre de 2026", texto)
        for texto in (textos[1], textos[2]):  # primer turno y saludo hablado
            self.assertIn("Abrahan", texto)
            self.assertIn("Kaya", texto)
            self.assertNotIn("soy Abrahan", texto.lower())

    def test_voz_oficial_de_kaya_reemplaza_celeste(self):
        self.assertEqual(identidad_origen.VOZ_KAYA_LIVE, "Achernar")
        self.assertEqual(identidad_origen.VOZ_KAYA_CLASICA, "aura-2-gloria-es")
        self.assertEqual(live_motor.VOZ_DEFECTO, identidad_origen.VOZ_KAYA_LIVE)
        self.assertEqual(live_motor.SesionKayaLive().voz, identidad_origen.VOZ_KAYA_LIVE)
        self.assertEqual(voz_rapida.MODELO_AURA, identidad_origen.VOZ_KAYA_CLASICA)
        self.assertEqual(tts_aura_stream.MODELO_DEFECTO, identidad_origen.VOZ_KAYA_CLASICA)
        for valor in (live_motor.VOZ_DEFECTO, voz_rapida.MODELO_AURA,
                      tts_aura_stream.MODELO_DEFECTO):
            self.assertNotIn("celeste", str(valor).lower())

    def test_onboarding_guarda_usuario_sin_alterar_identidad_de_kaya(self):
        with patch.dict(os.environ):
            ok, mensaje = onboarding_qt.guardar_configuracion(
                "Abrahan", CLAVES_PRUEBA, base=self.base, ruta_env=self.ruta_env)
        self.assertTrue(ok, mensaje)
        memoria = persistencia_segura.cargar_json_seguro(
            os.path.join(self.base, "memoria.json"), {})
        self.assertEqual(memoria.get("nombre"), "Kaya")
        self.assertEqual(memoria.get("creador"), identidad_origen.CREADOR)
        self.assertEqual(memoria.get("usuario"), "Abrahan")
        with self._ruta_parcheada():
            self.assertEqual(identidad_origen.nombre_usuario(), "Abrahan")

    def test_clasico_no_toma_turno_con_live_activo(self):
        app = MagicMock()
        app.coordinador_live.esta_live_activo.return_value = True
        app.coordinador_live.es_modo_principal.return_value = True
        original = habla_espontanea.generar_saludo_espontaneo
        with self._ruta_parcheada():
            identidad_origen.preparar_perfil_usuario("Abrahan")
            with patch("habla_espontanea.generar_saludo_espontaneo") as generar:
                nacimiento.saludar(app)
                original(app, lambda *_a: None)
        generar.assert_not_called()
        app.cola.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
