"""Pruebas del motor de formación, directivas y adaptadores de memoria."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cerebro
import memoria
import memoria_adaptadores as adapt
import memoria_formacion as form
from memoria_gestor import GestorMemoria
from memoria_almacen import AlmacenMemoriaCognitiva


class TestFormacionMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mem = memoria.Memoria(ruta_json=os.path.join(self.tmp.name, "memoria.json"),
            ruta_db=os.path.join(self.tmp.name, "recuerdos.db"), usuario_id="ana")

    def tearDown(self):
        self.mem.cerrar()
        self.tmp.cleanup()

    def test_01_guardado_explicito_y_relevancia(self):
        texto = "Prefiero trabajar con música clásica durante mis proyectos"
        r = adapt.procesar_candidato(self.mem, texto, "Recuerda que " + texto,
                                     "orden_explicita", explicito=True)
        self.assertTrue(r["aceptado"])
        self.assertEqual(r["recuerdo"].origen, "explicito")
        self.assertGreaterEqual(r["relevancia"], .36)
        self.assertTrue({"importancia", "utilidad_futura", "contexto", "persistencia",
            "frecuencia", "temporalidad", "calidad_fuente", "claridad"} <= set(r["criterios"]))

    def test_02_clasifica_los_cuatro_tipos(self):
        casos = (("episodica", "Ayer terminé la mudanza de mi oficina"),
            ("semantica", "Mi idioma preferido para estudiar es francés"),
            ("procedimental", "Paso 1: abrir el proyecto y luego revisar los cambios"),
            ("trabajo", "Hoy debo preparar la reunión de esta tarde"))
        for tipo, texto in casos:
            r = form.evaluar_candidato(texto, usuario_id="ana", fuente="conversacion")
            self.assertTrue(r["aceptado"], (tipo, r))
            self.assertEqual(r["recuerdo"].tipo_memoria, tipo)
            adapt.procesar_candidato(self.mem, texto, fuente="conversacion")
        self.assertEqual(self.mem.gestor.buscar("oficina")[0]["tipo_memoria"], "episodica")

    def test_03_ruido_y_ambiguedad(self):
        self.assertFalse(form.evaluar_candidato("Hola", fuente="conversacion")["aceptado"])
        incierto = form.evaluar_candidato("Tal vez me mude a Quito el próximo año", fuente="extraccion")
        self.assertFalse(incierto["aceptado"])
        temporal = form.evaluar_candidato("Quizá hoy cambie el plan del equipo", fuente="extraccion")
        if temporal["aceptado"]:
            self.assertEqual(temporal["recuerdo"].tipo_memoria, "trabajo")
            self.assertLessEqual(temporal["recuerdo"].confianza, .4)

    def test_04_origen_confianza_y_contexto(self):
        directo = form.evaluar_candidato("Mi hermana vive en una ciudad costera", "ana",
            "orden_explicita", True, contexto="turno", canal="voz")
        inferred = form.evaluar_candidato("Mi hermana vive en una ciudad costera", "ana",
            "extraccion", False, canal="texto")
        self.assertEqual(directo["recuerdo"].origen, "explicito")
        self.assertEqual(inferred["recuerdo"].origen, "inferido")
        self.assertGreater(directo["recuerdo"].confianza, inferred["recuerdo"].confianza)
        self.assertEqual(directo["recuerdo"].metadatos["canal"], "voz")

    def test_05_directiva_explicita_y_no_guardar(self):
        d = adapt.atender_turno(cerebro.Cerebro(None, self.mem),
            "Recuerda que prefiero trabajar temprano cada día")
        self.assertIn("recordaré", d[0])
        antes = len(self.mem.hechos)
        turno = "No guardes esto: estoy visitando una tienda hoy"
        respuesta = adapt.atender_turno(cerebro.Cerebro(None, self.mem), turno)
        self.assertIn("No guardaré", respuesta[0])
        self.assertEqual(len(self.mem.hechos), antes)

    def test_06_no_store_bloquea_extraccion_background(self):
        historial = [{"role": "user", "content": "No recuerdes esto, es temporal"},
                     {"role": "assistant", "content": "Entendido"}]
        self.assertTrue(adapt.historial_prohibido(historial))
        r = adapt.procesar_extraccion(self.mem, "El usuario usa una tienda", historial)
        self.assertEqual(r["motivo"], "directiva_no_guardar")
        self.assertEqual(self.mem.hechos, [])

    def test_07_persistencia_en_disco(self):
        self.assertTrue(self.mem.recordar("Mi objetivo es aprender fotografía", origen="explicito"))
        ruta = self.mem.almacen.ruta
        self.mem.cerrar()
        reopened = AlmacenMemoriaCognitiva(ruta, "ana")
        try:
            encontrados = reopened.buscar_texto("fotografía")
            self.assertEqual(len(encontrados), 1)
            self.assertEqual(encontrados[0]["origen"], "explicito")
        finally:
            reopened.cerrar()

    def test_08_integracion_cerebro_etiqueta_y_gestor(self):
        bot = cerebro.Cerebro(None, self.mem)
        with patch.object(bot, "instrucciones", return_value="sistema"), \
             patch("cerebro_enrutador.ejecutar_con_enrutador",
                   return_value="RESPUESTA: Entendido.\nRECUERDO: El usuario prefiere leer historia"), \
             patch("aprendizaje.registrar_interaccion", return_value=None):
            respuesta = bot.responder("Me gusta leer historia")
        self.assertEqual(respuesta[0], "Entendido.")
        filas = self.mem.gestor.buscar("leer historia")
        self.assertEqual(filas[0]["origen"], "inferido")
        self.assertEqual(filas[0]["usuario_id"], "ana")

    def test_09_adaptadores_temporales_y_privacidad(self):
        evento = {"resumen": "Ventana de aplicación temporal observada", "nivel_epistemico": "confirmado"}
        r = adapt.adaptar_evento(self.mem, evento)
        self.assertEqual(r["motivo"], "solo_contexto_temporal")
        self.assertFalse(self.mem.gestor.buscar("ventana temporal"))
        tarea = adapt.adaptar_resultado_tarea(self.mem, {"resultado": "Se completó una tarea temporal"})
        self.assertEqual(tarea["motivo"], "solo_contexto_temporal")
        with self.assertRaises(ValueError):
            self.mem.gestor.guardar("La contraseña de acceso es 987654")

    def test_10_correccion_errores_y_regresion(self):
        self.assertEqual(adapt.detectar_directiva("Corrige el recuerdo francés por italiano")["accion"], "corregir")
        self.assertEqual(adapt.detectar_directiva("¿Qué recuerdas de mis gustos?")["accion"], "revisar")
        self.assertFalse(self.mem.recordar("Hola"))
        self.assertEqual(self.mem.almacen.contar_recuerdos(), 0)
        self.mem.recordar("Mi color favorito es azul")
        resultado = adapt.atender_turno(cerebro.Cerebro(None, self.mem),
            "Corrige el recuerdo color favorito es azul por mi color favorito actual es verde")
        self.assertIn("corregido", resultado[0])
        self.assertTrue(self.mem.gestor.buscar("color favorito actual es verde"))
        self.assertEqual(os.listdir(self.tmp.name).count("recuerdos.db"), 1)


if __name__ == "__main__":
    unittest.main()
