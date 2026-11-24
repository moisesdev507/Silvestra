"""Regresión: voz anticipada por oraciones y memoria persistente SQLite."""
import os
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import cerebro as cerebro_mod
import memoria_persistente as mp
import voz_stream


class FlujoFalso:
    def __init__(self, al_terminar=None):
        self.bloques = []
        self.cerrado = False
        self.al_terminar = al_terminar

    def agregar(self, frase, emocion=None):
        self.bloques.append(frase)

    def cerrar(self):
        self.cerrado = True


class VozFalsa:
    def __init__(self):
        self.flujos = []

    def flujo(self, al_terminar=None, emocion="neutral", **opciones):
        flujo = FlujoFalso(al_terminar)
        self.flujos.append(flujo)
        return flujo


class TestMemoriaPersistente(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.ruta = os.path.join(temporal.name, "memoria_jarvis.db")
        parche = patch.object(mp, "RUTA_DB", self.ruta)
        parche.start()
        self.addCleanup(parche.stop)

    def test_persistencia_real_tras_reinstanciar(self):
        guardado = mp.guardar_recuerdo(
            "tarea", "entrega_prog", "Mañana tengo entrega de Programación I")
        self.assertIsNotNone(guardado)
        # Conexión nueva: simula un reinicio del proceso.
        with closing(mp._conectar()) as con:
            fila = con.execute(
                "SELECT valor FROM recuerdos WHERE clave=?", ("entrega_prog",)
            ).fetchone()
        self.assertIsNotNone(fila)
        self.assertIn("Programación I", fila["valor"])
        self.assertEqual(len(mp.buscar_recuerdos("Programación")), 1)
        mp.guardar_recuerdo("tarea", "entrega_prog", "Entrega reprogramada")
        mp.guardar_recuerdo("tarea", "entrega_prog", "Entrega confirmada")
        self.assertEqual(len(mp.listar_recuerdos()), 1)
        self.assertEqual(mp.listar_recuerdos()[0]["valor"], "Entrega confirmada")
        self.assertTrue(mp.eliminar_recuerdo("entrega_prog"))
        self.assertEqual(mp.listar_recuerdos(), [])

    def test_deteccion_automatica_incluye_manana_y_no_guardar(self):
        guardados = mp.extraer_y_guardar_automatico(
            "Lyris, recuerda que mañana tengo entrega de Programación I")
        self.assertEqual(len(guardados), 1)
        self.assertIn("entrega de Programación I", guardados[0]["valor"])
        self.assertEqual(guardados[0]["categoria"], "tarea")
        self.assertEqual(mp.extraer_y_guardar_automatico(
            "Lyris, no guardes mi contraseña"), [])
        self.assertEqual(len(mp.extraer_y_guardar_automatico(
            "No olvides que la reunión es a las diez")), 1)

    def test_inyeccion_contexto_en_cerebro(self):
        mp.guardar_recuerdo(
            "tarea", "entrega_prog", "Entrega de Programación I mañana")
        contexto = mp.contexto_para_prompt("Programación")
        self.assertIn("Programación I", contexto)
        self.assertLessEqual(len(contexto), mp.LIMITE_CONTEXTO)

        capturado = {}

        def falso_prompt(memoria, texto, historial, **kw):
            capturado.update(kw)
            return "prompt-de-prueba"

        cerebro = object.__new__(cerebro_mod.Cerebro)
        cerebro.turno_invitado = False
        cerebro.app = None
        cerebro._seguimiento_visual_pendiente = False
        cerebro.memoria = object()
        cerebro._obtener_historial_podado = lambda: []
        with patch.object(cerebro_mod, "construir_prompt", falso_prompt):
            salida = cerebro.instrucciones("¿Qué tengo mañana?")
        self.assertEqual(salida, "prompt-de-prueba")
        self.assertIn("Programación I", capturado.get("contexto_adicional", ""))

        capturado.clear()
        cerebro.turno_invitado = True
        with patch.object(cerebro_mod, "construir_prompt", falso_prompt):
            cerebro.instrucciones("¿Qué tengo mañana?")
        self.assertNotIn("Programación I", capturado.get("contexto_adicional", ""))

    def test_contexto_nunca_excede_550_caracteres(self):
        for i in range(40):
            mp.guardar_recuerdo("general", "clave_%02d" % i,
                                "Dato de prueba número %d con texto suficientemente largo." % i)
        contexto = mp.contexto_para_prompt("prueba")
        self.assertTrue(contexto.startswith("[RECUERDOS PERSISTENTES]"))
        self.assertLessEqual(len(contexto), 550)


class TestVozEnBloques(unittest.TestCase):
    def test_reproduccion_en_bloques_sin_bloquear(self):
        voz = VozFalsa()
        texto = ("Primera oración de prueba. Segunda oración de prueba. "
                 "Tercera oración de prueba.")
        inicio = time.perf_counter()
        flujo = voz_stream.hablar_en_bloques(voz, texto)
        transcurrido = time.perf_counter() - inicio
        self.assertLess(transcurrido, 0.2)
        self.assertEqual(len(voz.flujos), 1)
        self.assertEqual(flujo.bloques, [
            "Primera oración de prueba.",
            "Segunda oración de prueba.",
            "Tercera oración de prueba.",
        ])
        self.assertTrue(flujo.cerrado)
        self.assertEqual(voz_stream.primera_oracion(texto),
                         "Primera oración de prueba.")

    def test_streaming_encola_cada_oracion_por_separado(self):
        flujo = FlujoFalso()
        bloques = voz_stream.agregar_bloques(
            flujo, "Primera oración larga de prueba. Segunda oración larga de prueba.")
        self.assertEqual(len(bloques), 2)
        self.assertEqual(flujo.bloques, bloques)
        self.assertFalse(flujo.cerrado)


if __name__ == "__main__":
    unittest.main()
