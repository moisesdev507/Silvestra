"""Autoguardado por transcripción, semántica, ciclo de sueño y seguimientos."""
import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ciclo_sueno_kaya
import estado
import estado_emocional_kaya
import live_herramientas
import live_motor
import live_webrtc
import memoria
import memoria_contexto
import memoria_semantica


class TestMemoriaSemanticaKaya(unittest.TestCase):
    UID = "prueba_semantica"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_db = os.path.join(self.tmp.name, "datos", "silvestra_memoria.db")
        os.makedirs(os.path.dirname(self.ruta_db), exist_ok=True)
        self.ahora = 1_000_000.0
        self.parches = [
            patch.object(memoria_semantica, "RUTA_DB", self.ruta_db),
            patch.object(memoria_semantica, "_clave_explicita", return_value=""),
            patch.object(ciclo_sueno_kaya, "RUTA_DB", self.ruta_db),
            patch.object(ciclo_sueno_kaya, "_ahora", side_effect=lambda: self.ahora),
            patch.object(estado_emocional_kaya, "RUTA_DB", self.ruta_db),
            patch.object(estado_emocional_kaya, "_ahora", side_effect=lambda: self.ahora),
            patch.object(estado, "RUTA", os.path.join(self.tmp.name, "estado.json")),
        ]
        for parche in self.parches:
            parche.start()
        self.instancia_original = memoria._memoria_instancia
        self.mem = memoria.Memoria(
            ruta_db=self.ruta_db,
            ruta_json=os.path.join(self.tmp.name, "memoria.json"),
            usuario_id=self.UID,
        )
        memoria_contexto.resetear_sesion()
        memoria_contexto._TURNOS.clear()

    def tearDown(self):
        self.mem.cerrar()
        memoria._memoria_instancia = self.instancia_original
        for parche in reversed(self.parches):
            parche.stop()
        self.tmp.cleanup()

    def test_busqueda_semantica_offline_sin_key(self):
        self.assertTrue(self.mem.recordar(
            "A Ana le gusta la comida italiana", origen="explicito",
            fuente="orden_explicita"))
        memoria_semantica._COLA.join()
        with closing(sqlite3.connect(self.ruta_db)) as con:
            fila = con.execute(
                "SELECT recuerdo_id,usuario_id,dim FROM kaya_embeddings").fetchone()
        self.assertIsNotNone(fila)
        self.assertEqual(fila[1], self.UID)
        self.assertEqual(int(fila[2]), memoria_semantica.DIM_OFFLINE)
        resultados = memoria_semantica.buscar_semantico_kaya(
            "Ana y su comida", usuario_id=self.UID, limite=3)
        self.assertTrue(resultados)
        self.assertIn("Ana", resultados[0][1])
        publicos = memoria_semantica.buscar_semantico(
            "Ana y su comida", usuario_id=self.UID, limite=3)
        self.assertEqual(publicos[0][0], resultados[0][0])

    def test_busqueda_semantica_online_con_gemini(self):
        fila = self.mem.almacen.guardar_recuerdo(
            "El perro de Ana se llama Firulais", origen="explicito")
        vector = [0.9, 0.1, 0.0]
        with patch.object(memoria_semantica, "_clave_explicita", return_value="fake-key"), \
                patch.object(memoria_semantica, "obtener_embedding", return_value=vector):
            self.assertTrue(memoria_semantica.indexar_recuerdo_kaya(
                str(fila["id"]), "El perro de Ana se llama Firulais",
                self.UID, ruta_db=self.ruta_db))
            resultados = memoria_semantica.buscar_semantico_kaya(
                "animal canino domestico", usuario_id=self.UID, limite=3)
        self.assertTrue(resultados)
        self.assertEqual(resultados[0][0], str(fila["id"]))
        self.assertGreaterEqual(resultados[0][2], 0.72)

    def test_transcripcion_real_configura_captura_y_acumula_turnos(self):
        configuraciones = []
        config_real = live_motor.types.LiveConnectConfig

        def espiar_config(**kwargs):
            configuraciones.append(kwargs)
            return config_real(**kwargs)

        vistos = []
        sesion = live_motor.SesionKayaLive(
            on_transcripcion=lambda rol, texto: vistos.append((rol, texto)))
        texto = "Me gusta estudiar fotografía"
        respuesta = SimpleNamespace(
            server_content=SimpleNamespace(
                input_audio_transcription=SimpleNamespace(text=texto),
                model_turn=None, turn_complete=False, interrupted=False),
            tool_call=None)

        async def recibir():
            yield respuesta
            sesion.activo = False

        class SesionFalsa:
            async def receive(self):
                async for item in recibir():
                    yield item

        class ContextoFalso:
            async def __aenter__(self):
                return SesionFalsa()

            async def __aexit__(self, *_args):
                return False

        cliente = MagicMock()
        cliente.aio.live.connect.return_value = ContextoFalso()
        sesion.activo = True
        sesion._puente_webrtc = None
        with patch.object(live_motor.live_audio, "obtener_api_key", return_value="fake"), \
                patch.object(live_motor.genai, "Client", return_value=cliente), \
                patch.object(live_motor.identidad_origen, "consumir_primer_despertar",
                             return_value=False), \
                patch.object(live_motor.types, "LiveConnectConfig", side_effect=espiar_config):
            asyncio.run(sesion._ejecutar_sesion())
        self.assertTrue(configuraciones)
        self.assertIsNotNone(configuraciones[0].get("input_audio_transcription"))
        self.assertEqual(vistos, [("usuario", texto)])
        self.assertTrue(any(t["role"] == "user" and "fotografía" in t["content"]
                            for t in memoria_contexto.turnos_recientes()))

    def test_senal_sleep_extrae_hechos_filtrados_y_llama_al_sueno(self):
        turnos = [
            {"role": "user", "content": "Estoy estudiando fotografía y practico fotografía"},
            {"role": "user", "content": "hola"},
        ]
        with patch.object(self.mem, "extraer_hechos_conversacion") as extraer, \
                patch.object(ciclo_sueno_kaya, "solicitar_sueno", return_value=True) as dormir:
            self.assertTrue(ciclo_sueno_kaya.al_dormir(turnos))
            dormir.assert_called_once()
            time.sleep(0.1)
            extraer.assert_called_once()
            self.assertEqual(len(extraer.call_args[0][0]), 1)

        sesion = live_motor.SesionKayaLive()
        sesion.activo = True
        cola = sesion.cola_audio_entrada
        cola.put(live_webrtc.SENAL_SLEEP)
        sesion._puente_webrtc = SimpleNamespace(cola_entrada=cola, dormida=False)

        async def enviar(**_kwargs):
            return None

        falsa = SimpleNamespace(send_realtime_input=enviar)
        with patch.object(sesion, "_al_dormir",
                          side_effect=lambda: setattr(sesion, "activo", False)) as gancho:
            asyncio.run(asyncio.wait_for(sesion._tarea_envio_audio(falsa), timeout=5))
            gancho.assert_called_once()

    def test_ciclo_sueno_cooldown_e_intuiciones_inferidas(self):
        turnos = [
            {"role": "user", "content": "Estoy estudiando fotografía y practico fotografía"},
            {"role": "user", "content": "Mi proyecto es sobre fotografía"},
        ]
        with patch.object(ciclo_sueno_kaya, "consolidar", return_value=0):
            self.assertTrue(ciclo_sueno_kaya.solicitar_sueno(turnos, self.UID))
            self.assertFalse(ciclo_sueno_kaya.solicitar_sueno(turnos, self.UID))
            self.ahora += 3 * 3600 + 1
            self.assertTrue(ciclo_sueno_kaya.solicitar_sueno(turnos, self.UID))

        self.assertGreaterEqual(ciclo_sueno_kaya.consolidar(turnos, self.UID), 1)
        intuiciones = [f for f in self.mem.almacen.listar_recuerdos(200, usuario_id=self.UID)
                       if "[INTUICION]" in f["contenido"]]
        self.assertEqual(len(intuiciones), 1)
        self.assertEqual(intuiciones[0]["origen"], "inferido")
        self.assertAlmostEqual(float(intuiciones[0]["confianza"]), 0.65)
        self.assertFalse(memoria_contexto.hechos_verificados(self.mem))
        self.assertGreater(estado_emocional_kaya.obtener_estado(self.UID)["energia"], 0.75)

    def test_seguimientos_y_presupuesto_en_resumen(self):
        nombres = [f.name for f in
                   live_herramientas.declarar_declaraciones_herramientas()[0].function_declarations]
        self.assertIn("agendar_seguimiento", nombres)
        respuesta = asyncio.run(live_herramientas.despachar_herramienta_asincrona(
            "agendar_seguimiento",
            {"tema": "Proyecto Atlas", "contexto": "charla de hoy", "horas_espera": 24}))
        self.assertIn("Listo", respuesta)
        self.assertEqual(
            ciclo_sueno_kaya.seguimiento_para_prompt(self.UID, ahora=self.ahora), "")
        self.assertTrue(ciclo_sueno_kaya.seguimiento_para_prompt(
            self.UID, ahora=self.ahora + 25 * 3600).startswith("Seguimiento:"))
        self.assertEqual(ciclo_sueno_kaya.seguimiento_para_prompt(
            self.UID, ahora=self.ahora + 25 * 3600), "")

        ciclo_sueno_kaya.agendar("Proyecto Atlas", "charla", 24, self.UID)
        for dato in ("A Ana le gusta la comida italiana",
                     "Ana estudia fotografía en la universidad",
                     "Mi hermana trabaja en el hospital de la ciudad",
                     "El usuario tiene un gato negro llamado Firulais"):
            self.assertTrue(self.mem.recordar(
                dato, origen="explicito", fuente="orden_explicita"))
        memoria_semantica._COLA.join()
        memoria_contexto.registrar_turno("user", "mascota gato Firulais")
        memoria_contexto.resetear_sesion()
        with patch.object(ciclo_sueno_kaya, "_ahora", return_value=self.ahora + 25 * 3600):
            bloque = memoria_contexto.resumen_para_prompt(self.mem)
        for esperado in ("Ánimo:", "Seguimiento:", "Recuerdo:", "Hecho:"):
            self.assertIn(esperado, bloque)
        self.assertLessEqual(len(bloque), 480)


if __name__ == "__main__":
    unittest.main()
