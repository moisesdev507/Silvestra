"""Sprint 2A: embeddings, backfill, recuperación semántica, calidad e historial."""
import os
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

import cerebro_historial
import memoria_calidad
import memoria_embeddings as me
import memoria_filtro
import memoria_formacion
import memoria_indice_vectorial as miv
from memoria import Memoria
from memoria_almacen import AlmacenMemoriaCognitiva


class TestSprint2AMemoriaSemantica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._n = 0
        self._env = os.environ.get("SILVESTRA_EMBEDDINGS_OFFLINE")
        os.environ["SILVESTRA_EMBEDDINGS_OFFLINE"] = "1"
        self.addCleanup(self._restaurar_env)
        me._CACHE.clear()

    def _restaurar_env(self):
        if self._env is None:
            os.environ.pop("SILVESTRA_EMBEDDINGS_OFFLINE", None)
        else:
            os.environ["SILVESTRA_EMBEDDINGS_OFFLINE"] = self._env

    def _ruta(self):
        self._n += 1
        return os.path.join(self.tmp.name, f"db_{self._n}.db")

    def _memoria(self, usuario="s2a"):
        memoria = Memoria(ruta_db=self._ruta(), usuario_id=usuario)
        self.addCleanup(memoria.cerrar)
        return memoria

    def test_01_fallback_determinista_y_cuantizacion(self):
        a = me.vector("hola mundo panama", "documento", False)
        b = me.vector("hola mundo panama", "documento", False)
        self.assertEqual(a.shape, (me.DIM_FALLBACK,))
        np.testing.assert_allclose(a, b)
        blob = me.cuantizar(a, me.TIPO_FALLBACK)
        leido, tipo = me.desquantizar(blob)
        self.assertEqual(tipo, me.TIPO_FALLBACK)
        self.assertGreater(me.coseno(a, leido), 0.99)
        self.assertIsNone(me.desquantizar(b"corto"))

    def test_02_cache_evita_segunda_llamada_api(self):
        os.environ.pop("SILVESTRA_EMBEDDINGS_OFFLINE", None)
        llamadas = []

        def falso(texto, modo):
            llamadas.append(modo)
            return np.ones(8, dtype=np.float32)

        with mock.patch.object(me, "_vector_api", side_effect=falso):
            primero, tipo = me.vector_con_tipo("texto unico cache s2a", "documento", True)
            segundo, tipo2 = me.vector_con_tipo("texto unico cache s2a", "documento", True)
        self.assertEqual((tipo, tipo2), (me.TIPO_API, me.TIPO_API))
        self.assertEqual(len(llamadas), 1)
        np.testing.assert_allclose(primero, segundo)

    def test_03_guardado_asegura_embedding_en_bd_temporal(self):
        memoria = self._memoria()
        guardado = memoria.gestor.guardar("Mi color favorito es azul",
                                          usuario_id="s2a")
        rid = guardado["id"]
        with memoria.almacen._lock:
            fila = memoria.almacen.conexion.execute(
                "SELECT embedding FROM recuerdos WHERE id=?", (rid,)).fetchone()
        self.assertIsNotNone(fila[0])
        leido = miv.leer_embedding(memoria.almacen, rid, "s2a")
        self.assertIsNotNone(leido)
        self.assertEqual(leido[1], me.TIPO_FALLBACK)

    def test_04_backfill_lotificado_y_cancelable(self):
        almacen = AlmacenMemoriaCognitiva(self._ruta(), "s2a")
        self.addCleanup(almacen.cerrar)
        for i in range(5):
            almacen.guardar_recuerdo(f"Recuerdo antiguo número {i} sobre el proyecto",
                                     usuario_id="s2a")
        resultado = miv.backfill(almacen, "s2a", limite=2, max_segundos=5)
        self.assertEqual(resultado["procesados"], 2)
        with almacen._lock:
            con_vector = almacen.conexion.execute(
                "SELECT count(*) FROM recuerdos WHERE embedding IS NOT NULL").fetchone()[0]
        self.assertEqual(con_vector, 2)
        token = threading.Event()
        token.set()
        cancelado = miv.backfill(almacen, "s2a", token_cancelacion=token)
        self.assertTrue(cancelado["cancelado"])
        self.assertEqual(cancelado["procesados"], 0)

    def test_05_recuperacion_semantica_por_sinonimo(self):
        memoria = self._memoria()
        memoria.gestor.guardar("I-Field desplegado en producción", usuario_id="s2a")
        paquete = memoria.recuperar("¿cómo va el despliegue?")
        self.assertTrue(paquete["resultados"])
        self.assertTrue(any("desplegado" in r["contenido"]
                            for r in paquete["resultados"]))
        self.assertGreater(paquete["resultados"][0]["puntuacion"], 0.22)
        self.assertTrue(paquete["vectorial_disponible"])

    def test_06_calidad_rechaza_autorreferencia_ruido_y_duplicado(self):
        valido, razon = memoria_filtro.es_recuerdo_valido(
            "Fui desarrollada por primera vez por un equipo")
        self.assertFalse(valido)
        self.assertIn("autorreferencia", razon)
        candidato = memoria_formacion.evaluar_candidato("gracias")
        self.assertFalse(candidato["aceptado"])

        def vector_fn(texto):
            return np.array([1.0, 0.0] if "azul" in texto.lower() else [0.0, 1.0])

        self.assertTrue(memoria_calidad.es_duplicado_semantico(
            "Mi color favorito es azul", ["El azul me encanta"], vector_fn=vector_fn))
        self.assertFalse(memoria_calidad.es_duplicado_semantico(
            "Mi color favorito es azul", ["El cielo es gris"], vector_fn=vector_fn))

    def test_07_ventana_unificada_rapido_vs_pro(self):
        historial = []
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            historial.append({"role": role, "content": f"turno {i} " + "detalle " * 60})
        self.assertEqual(len(cerebro_historial.podar(historial)), 10)
        rapido = cerebro_historial.ventana(historial, "rapido")
        pro = cerebro_historial.ventana(historial, "pro")
        self.assertLessEqual(len(rapido), 8)
        self.assertGreater(len(pro), len(rapido))
        self.assertTrue(all(len(m["content"]) <= 600 for m in rapido))
        self.assertLessEqual(sum(len(m["content"]) + 16 for m in rapido), 3100)
        completa = cerebro_historial.construir_ventana(historial, "rapido", "SYS")
        self.assertEqual(completa[0], {"role": "system", "content": "SYS"})

    def test_08_carril_calculado_antes_de_la_ventana(self):
        with open("respuesta_flujo.py", "r", encoding="utf-8") as archivo:
            fuente = archivo.read()
        self.assertLess(fuente.index("decidir_carril"), fuente.index("construir_ventana"))
        self.assertNotIn("cerebro.historial[-8:]", fuente)


if __name__ == "__main__":
    unittest.main()
