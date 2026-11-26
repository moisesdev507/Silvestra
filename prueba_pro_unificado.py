"""Pruebas del núcleo unificado: correo, contexto ambiental, iniciativa y PCM."""
import asyncio
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cerebro_proactivo as proactivo
import correo_unificado as correo
import contexto_ambiental as ambiente
import iniciativa_unificada as iniciativa


class PruebaCorreo(unittest.TestCase):
    def setUp(self):
        correo.cancelar_correo()
        self.enviados = []
        servicio = MagicMock()
        envio = servicio.users.return_value.messages.return_value.send.return_value
        envio.execute.side_effect = self._registrar_envio
        self.servicios = {"gmail": servicio}
        self.parche = patch(
            "google_workspace_oauth.conectar", return_value=(self.servicios, ""))
        self.parche.start()

    def tearDown(self):
        self.parche.stop()
        correo.cancelar_correo()

    def _registrar_envio(self):
        self.enviados.append(True)
        return {"id": "mensaje-enviado"}

    def test_preparar_no_envia_y_confirmar_exige_confirmacion(self):
        r = correo.preparar_correo("ana@example.com", "Avance", "Listo el informe.")
        self.assertTrue(r["ok"])
        self.assertTrue(correo.hay_borrador())
        self.assertFalse(self.enviados)
        self.assertFalse(correo.confirmar_envio_correo()["ok"])
        self.assertFalse(correo.confirmar_envio_correo("quizá")["ok"])
        self.assertFalse(self.enviados)
        self.assertTrue(correo.confirmar_envio_correo("sí")["ok"])
        self.assertEqual(len(self.enviados), 1)
        self.assertFalse(correo.hay_borrador())

    def test_cancelar_descarta_sin_enviar(self):
        correo.preparar_correo("ana@example.com", "Avance", "Texto.")
        self.assertTrue(correo.cancelar_correo()["ok"])
        self.assertFalse(correo.hay_borrador())
        self.assertFalse(correo.confirmar_envio_correo("confirma")["ok"])
        self.assertFalse(self.enviados)

    def test_validacion_de_destinatario_y_cuerpo(self):
        self.assertFalse(correo.preparar_correo("no-es-correo", "A", "B")["ok"])
        self.assertFalse(correo.preparar_correo("ana@example.com", "", "B")["ok"])
        self.assertFalse(correo.hay_borrador())

    def test_herramienta_live_y_texto_clasico(self):
        self.assertIn("Listo", correo.gestionar(
            "preparar", "ana@example.com", "Avance", "Mensaje."))
        self.assertFalse(self.enviados)
        self.assertIn("enviado", correo.gestionar("confirmar").lower())
        self.assertEqual(len(self.enviados), 1)
        texto = ("envía un correo a ana@example.com, asunto Avance, "
                 "mensaje listo el informe")
        self.assertIn("Listo", correo.gestionar_desde_texto(texto))
        self.assertEqual(len(self.enviados), 1)
        self.assertIn("cancelado", correo.gestionar_desde_texto("cancela").lower())

    def test_registro_en_motor_y_scope(self):
        from ejecucion_registro import RegistroHerramientas
        import google_workspace_oauth as oauth
        registro = RegistroHerramientas()
        self.assertTrue(correo.registrar_en_motor(registro))
        self.assertTrue(registro.obtener("confirmar_envio_correo").requiere_confirmacion)
        self.assertIn("https://www.googleapis.com/auth/gmail.send", oauth.SCOPES)


class PruebaContexto(unittest.TestCase):
    def setUp(self):
        ambiente.limpiar()

    def tearDown(self):
        ambiente.limpiar()

    def test_captura_filtra_secretos_y_recorta(self):
        secreto = "password: supersecreto token " + "a" * 240
        datos = ambiente.capturar(
            ventana="La ventana activa es: Gmail - Informe",
            portapapeles=secreto,
        )
        self.assertLessEqual(len(datos["clipboard"]), 180)
        self.assertNotIn("supersecreto", datos["clipboard"])
        self.assertNotIn("a" * 32, datos["clipboard"])
        resumen = ambiente.resumen_para_prompt()
        self.assertIn("[CONTEXTO AMBIENTAL]", resumen)
        self.assertIn("Gmail", resumen)

    def test_inyeccion_en_prompts_y_referencias(self):
        ambiente.capturar(ventana="La ventana activa es: Gmail", portapapeles="responder este correo")
        self.assertIn("[CONTEXTO AMBIENTAL]", ambiente.añadir("base"))
        self.assertIn("[CONTEXTO AMBIENTAL]", ambiente.resolver_referencias("arregla esto"))
        self.assertEqual(ambiente.resolver_referencias("buenos días"), "buenos días")
        import live_prompt
        import live_audio
        self.assertIn("[CONTEXTO AMBIENTAL]", live_prompt.contexto_ambiental())
        self.assertIn("[CONTEXTO AMBIENTAL]", live_prompt.contexto_memoria())
        self.assertIn("[CONTEXTO AMBIENTAL]",
                      live_audio.construir_instruccion_sistema(rapido=True))
        import agente_herramientas
        self.assertIn("[CONTEXTO AMBIENTAL]",
                      agente_herramientas.contexto_para_cerebro("buenos días"))


class PruebaIniciativa(unittest.TestCase):
    def setUp(self):
        iniciativa.reiniciar()
        self.cola = MagicMock()
        self.app = SimpleNamespace(cola=self.cola, coordinador_live=None, memoria=None)
        self.aviso = {"tipo": "recordatorio", "mensaje": "Tomar agua ahora", "emocion": "neutral"}
        self.parche_aviso = patch.object(iniciativa, "obtener_aviso", return_value=dict(self.aviso))
        self.parche_aviso.start()
        motor = MagicMock()
        motor.puede_intervenir.return_value = (True, "")
        motor.evaluar_oportunidad.return_value = None
        motor.ultimo_aviso = 0.0
        self.parche_motor = patch.object(
            proactivo, "obtener_motor_proactivo", return_value=motor)
        self.parche_motor.start()

    def tearDown(self):
        if getattr(self, "parche_aviso", None):
            self.parche_aviso.stop()
        self.parche_motor.stop()
        iniciativa.reiniciar()

    def _coordinador(self, activo=False, principal=False):
        cl = MagicMock()
        cl.esta_live_activo.return_value = activo
        cl.es_modo_principal.return_value = principal
        cl.enviar_orden.return_value = True
        cl.intentar_activar_live.return_value = True
        cl.sesion_live = SimpleNamespace(_puente_webrtc=SimpleNamespace(dormida=True))
        self.app.coordinador_live = cl
        return cl

    def test_live_activo_despierta_reposo_e_inyecta(self):
        cl = self._coordinador(activo=True)
        self.assertTrue(iniciativa.emitir(self.app))
        self.assertFalse(cl.sesion_live._puente_webrtc.dormida)
        orden = cl.enviar_orden.call_args.args[0]
        self.assertIn("Tomar agua ahora", orden)
        self.cola.put.assert_not_called()

    def test_live_inactivo_pero_principal_intenta_activar(self):
        cl = self._coordinador(activo=False, principal=True)
        self.assertTrue(iniciativa.emitir(self.app))
        self.assertIn("Tomar agua ahora", cl.intentar_activar_live.call_args.args[0])
        self.cola.put.assert_not_called()

    def test_clasico_habla_por_celeste(self):
        self._coordinador(activo=False, principal=False)
        self.assertTrue(iniciativa.emitir(self.app))
        self.cola.put.assert_called_once_with(("hablar", ("Tomar agua ahora", "neutral")))

    def test_privado_y_cooldown_bloquean(self):
        cp = proactivo
        with patch.object(cp, "es_modo_privado", return_value=True):
            self.assertFalse(iniciativa.emitir(self.app))
        self.cola.put.assert_not_called()
        motor = MagicMock()
        motor.puede_intervenir.return_value = (False, "cooldown_activo")
        with patch.object(cp, "obtener_motor_proactivo", return_value=motor):
            permitido, motivo = iniciativa.puede_emitir(self.app, self.aviso)
        self.assertFalse(permitido)
        self.assertEqual(motivo, "cooldown_activo")

    def test_aviso_no_se_repite(self):
        self._coordinador(activo=False, principal=False)
        self.assertTrue(iniciativa.emitir(self.app))
        self.assertFalse(iniciativa.emitir(self.app))
        self.cola.put.assert_called_once()

    def test_fuentes_reales(self):
        self.parche_aviso.stop()
        self.parche_aviso = None
        with patch("ciclo_sueno_kaya.seguimiento_para_prompt", return_value="Seguimiento: informe"):
            self.assertEqual(iniciativa.obtener_aviso(self.app)["tipo"], "seguimiento")
        with patch("ciclo_sueno_kaya.seguimiento_para_prompt", return_value=""):
            with patch("recordatorios._cargar", return_value=[
                    {"texto": "Llamar a Ana", "timestamp": time.time() - 60,
                     "completado": False}]):
                self.assertEqual(iniciativa.obtener_aviso(self.app)["tipo"], "recordatorio")


class PruebaPcm(unittest.TestCase):
    def test_frames_vacios_no_se_envian(self):
        import live_motor_audio as audio

        class Cola:
            def __init__(self, datos):
                self.datos = list(datos)
                self.indice = 0

            def get(self, timeout=0):
                if self.indice >= len(self.datos):
                    raise queue.Empty()
                valor = self.datos[self.indice]
                self.indice += 1
                return valor

        class Sesion:
            def __init__(self, capa):
                self.capa = capa
                self.llamadas = []

            async def send_realtime_input(self, audio=None):
                self.llamadas.append(audio.data)
                self.capa.activo = False

        capa = audio.CapaAudioLive()
        capa.activo = True
        capa._puente_webrtc = None
        capa.cola_audio_entrada = Cola([b"", None, 123, bytearray(b"\x01\x02")])
        capa.puerta = SimpleNamespace(reproduciendo=False)
        capa.compuerta = SimpleNamespace(esta_en_ventana_eco=lambda: False)
        sesion = Sesion(capa)
        asyncio.run(capa._tarea_envio_audio(sesion))
        self.assertEqual(sesion.llamadas, [b"\x01\x02"])

    def test_stream_continuo_en_amarillo(self):
        with open("live_webrtc.py", "r", encoding="utf-8") as f:
            codigo = f.read()
        self.assertIn("Math.max(0.0065,piso*1.65)", codigo)
        self.assertIn("new Int16Array(pcm.length).buffer", codigo)
        self.assertIn("if(dormida){preroll.push(pcm.buffer)", codigo)
        self.assertIn('sendCtrl({type:"estado",v:"reposo"})', codigo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
