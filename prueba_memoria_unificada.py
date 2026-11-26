"""Pruebas de memoria unificada: Live, voz clásica, contexto y Supabase."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import estado
import kaya_live_nucleo
import live_audio
import live_herramientas
import live_herramientas_extra
import memoria
import memoria_adaptadores as adapt
import memoria_contexto
import memoria_filtro
import memoria_supabase
import memoria_unificada


class TestMemoriaUnificada(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_estado = os.path.join(self.tmp.name, "estado.json")
        self.parche_estado = patch.object(estado, "RUTA", self.ruta_estado)
        self.parche_estado.start()
        estado.guardar({})
        self.instancia_original = memoria._memoria_instancia
        self.mem = memoria.Memoria(
            ruta_db=os.path.join(self.tmp.name, "memoria.db"),
            ruta_json=os.path.join(self.tmp.name, "memoria.json"),
            usuario_id="prueba_unificada",
        )
        self.mem.nacer("Kaya", "Ana", "ayudar")
        memoria_supabase.reiniciar_para_pruebas()
        memoria_contexto.resetear_sesion()

    def tearDown(self):
        memoria_supabase.reiniciar_para_pruebas()
        self.mem.cerrar()
        memoria._memoria_instancia = self.instancia_original
        self.parche_estado.stop()
        self.tmp.cleanup()

    def test_instancia_principal_y_declaraciones(self):
        self.assertIs(memoria.instancia_principal(), self.mem)
        tools = live_herramientas.declarar_declaraciones_herramientas()
        nombres = [f.name for f in tools[0].function_declarations]
        for esperado in ("recordar_dato", "consultar_memoria", "olvidar_dato"):
            self.assertIn(esperado, nombres)
        respuesta = live_herramientas_extra.recordar_dato("A Ana le gusta la comida italiana")
        self.assertIn("guardé", respuesta.lower())
        self.assertIn("italiana", live_herramientas_extra.consultar_memoria(""))

    def test_despacho_asincrono_comparte_memoria(self):
        async def coro():
            r1 = await live_herramientas.despachar_herramienta_asincrona(
                "recordar_dato", {"hecho": "El hermano de Ana vive en David"})
            r2 = await live_herramientas.despachar_herramienta_asincrona(
                "consultar_memoria", {"tema": ""})
            r3 = await live_herramientas.despachar_herramienta_asincrona(
                "olvidar_dato", {"tema": "hermano"})
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(coro())
        self.assertIn("guardé", r1.lower())
        self.assertIn("David", r2)
        self.assertIn("olvidado", r3.lower())
        self.assertFalse(any("hermano" in h for h in self.mem.hechos))

    def test_resumen_dinamico_no_repite_datos(self):
        self.assertTrue(self.mem.recordar(
            "A Ana le gusta la comida italiana", origen="explicito", fuente="orden_explicita"))
        memoria_contexto.resetear_sesion()
        primero = memoria_contexto.resumen_para_prompt(self.mem)
        self.assertIn("Hecho:", primero)
        self.assertLess(len(primero), 420)
        segundo = memoria_contexto.resumen_para_prompt(self.mem)
        self.assertNotIn("Hecho:", segundo)
        self.assertIn("Ánimo:", segundo)
        self.assertLessEqual(len(segundo), 450)
        registro = estado.cargar().get("memoria_contexto_sesion")
        self.assertTrue(registro["vistos"])
        self.assertGreaterEqual(registro["despertares"], 1)

    def test_extractor_rechaza_ruido_suposiciones_y_comandos(self):
        for texto in ("Parece que a Ana le interesa el fútbol",
                      "Supongo que Ana tendrá un gato",
                      "Ejecuta el comando para abrir el archivo",
                      "mm, hola"):
            self.assertTrue(memoria_filtro.es_ruido_extraccion(texto), texto)
        historial = [
            {"role": "user", "content": "Hola, cuéntame"},
            {"role": "assistant", "content": "Claro, dime"},
        ]
        rechazo = adapt.procesar_extraccion(self.mem, "Parece que a Ana le interesa el fútbol", historial)
        self.assertEqual(rechazo["motivo"], "ruido_extraccion")

        def pedir(mensajes, tarea=None):
            return (
                "HECHO: Parece que a Ana le interesa el fútbol.\n"
                "HECHO: A Ana le gusta la comida italiana.\n"
                "HECHO: Ejecuta el comando para abrir el archivo."
            )

        self.mem.extraer_hechos_conversacion(historial, pedir_fn=pedir)
        self.assertEqual(len(self.mem.hechos), 1)
        self.assertIn("italiana", self.mem.hechos[0])

    def test_supabase_sin_claves_es_no_op(self):
        with patch.object(memoria_supabase, "_leer_env", return_value={}):
            memoria_supabase.reiniciar_para_pruebas()
            self.assertFalse(memoria_supabase.configurar(url="", clave="", forzar=True))
            self.assertFalse(memoria_supabase.notificar_guardado(
                {"id": 1, "contenido": "dato", "usuario_id": "u"}))
            self.assertEqual(memoria_supabase.estado()["pendientes"], 0)

    def test_supabase_encola_upsert_y_borrado(self):
        with patch.object(memoria_supabase.httpx, "request") as req, \
             patch.object(memoria_supabase, "_leer_env", return_value={}):
            memoria_supabase.reiniciar_para_pruebas()
            self.assertTrue(memoria_supabase.configurar(
                "https://ejemplo.supabase.co", "clave-falsa", forzar=True, iniciar_hilo=False))
            self.assertTrue(self.mem.recordar(
                "A Ana le gusta la comida italiana", origen="explicito", fuente="orden_explicita"))
            self.assertGreaterEqual(memoria_supabase.sincronizar_pendientes(), 1)
            metodos = [llamada.args[0] for llamada in req.call_args_list]
            self.assertIn("POST", metodos)
            self.assertTrue(any(
                llamada.kwargs.get("json") and "comida italiana" in str(llamada.kwargs["json"])
                for llamada in req.call_args_list if llamada.args[0] == "POST"))
            self.assertIn("1 recuerdo", self.mem.olvidar("italiana"))
            memoria_supabase.sincronizar_pendientes()
            self.assertIn("DELETE", [llamada.args[0] for llamada in req.call_args_list])

    def test_consultar_incluye_respaldo_supabase(self):
        with patch.object(memoria_supabase.httpx, "request") as req, \
             patch.object(memoria_supabase, "_leer_env", return_value={}):
            memoria_supabase.reiniciar_para_pruebas()
            self.assertTrue(memoria_supabase.configurar(
                "https://ejemplo.supabase.co", "clave-falsa", forzar=True,
                iniciar_hilo=False))
            req.return_value.status_code = 200
            req.return_value.json.return_value = [{"contenido": "Dato remoto de Ana"}]
            memoria_unificada._sincronizados.clear()
            texto = memoria_unificada.consultar("remoto")
            self.assertIn("Dato remoto de Ana", texto)
            self.assertTrue(any(llamada.args[0] == "GET"
                                for llamada in req.call_args_list))

    def test_prompts_live_usan_memoria_y_herramientas(self):
        self.assertTrue(self.mem.recordar(
            "A Ana le gusta la comida italiana", origen="explicito", fuente="orden_explicita"))
        memoria_contexto.resetear_sesion()
        instr = live_audio.construir_instruccion_sistema()
        for herramienta in ("recordar_dato", "consultar_memoria", "olvidar_dato"):
            self.assertIn(herramienta, instr)
        self.assertIn("Hecho:", instr)
        memoria_contexto.resetear_sesion()
        self.assertIn("Hecho:", kaya_live_nucleo.construir_instruccion_sistema())


if __name__ == "__main__":
    unittest.main()
