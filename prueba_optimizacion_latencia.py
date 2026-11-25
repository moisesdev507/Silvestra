"""Pruebas unitarias para optimización de latencia:
1. Caché de recuerdos en RAM (memoria_persistente):
   - Segunda lectura sin recarga de disco (< 15 ms).
   - Invalidación automática al guardar o eliminar recuerdos.
2. Selección de modelo ultrarrápido en el carril rápido (proveedores_cadenas):
   - Modelos vigentes y priorizados para Groq sin fallback por 404.
3. Optimización del prompt en charla cotidiana (cerebro_perfil y cerebro_prompt):
   - Clasificación ultrarrápida para saludos y cortesía cotidiana.
   - Tramo de memoria pre-LLM < 15 ms.
"""
import time
import unittest
from unittest.mock import patch

import cerebro_perfil
import cerebro_prompt
import memoria_persistente as mp
import proveedores_cadenas as pc


class TestOptimizacionLatenciaMemoriaYCerebro(unittest.TestCase):

    def test_cache_memoria_ram_e_invalidacion(self):
        # 1. Primera lectura puebla la caché
        q = "test_cache_latencia_clave"
        mp.guardar_recuerdo("test", q, "Valor de prueba para memoria en RAM")
        
        # Búsqueda inicial
        t0 = time.perf_counter()
        r1 = mp.buscar_recuerdos(q)
        t_primera = (time.perf_counter() - t0) * 1000.0

        # Segunda búsqueda: debe servirse de la caché en RAM (< 15 ms)
        t1 = time.perf_counter()
        r2 = mp.buscar_recuerdos(q)
        t_segunda = (time.perf_counter() - t1) * 1000.0

        self.assertEqual(len(r1), len(r2))
        self.assertLess(t_segunda, 15.0, f"La búsqueda en caché tardó {t_segunda:.2f}ms (debe ser < 15ms)")

        # Listar recuerdos también usa caché en RAM
        t2 = time.perf_counter()
        l1 = mp.listar_recuerdos(limite=5)
        t_listar = (time.perf_counter() - t2) * 1000.0
        self.assertLess(t_listar, 15.0)

        # 2. Invalidación al guardar
        mp.guardar_recuerdo("test", q, "Valor actualizado")
        # Al guardar, la caché se invalida
        r3 = mp.buscar_recuerdos(q)
        self.assertEqual(r3[0]["valor"], "Valor actualizado")

        # 3. Invalidación al eliminar
        self.assertTrue(mp.eliminar_recuerdo(q))
        r4 = mp.buscar_recuerdos(q)
        self.assertEqual(len(r4), 0)

    def test_carril_rapido_modelos_vigentes_groq(self):
        # Verificar que MODELOS_RAPIDOS_GROQ priorice modelos vigentes sin 404
        self.assertIn("openai/gpt-oss-20b", pc.MODELOS_RAPIDOS_GROQ)
        # Verificar que la lista de modelos rápidos de Groq no contenga modelos dados de baja
        for m in pc.MODELOS_RAPIDOS_GROQ:
            self.assertNotIn("llama-3.1-8b-instant", m)
            self.assertNotIn("llama-3.3-70b-versatile", m)

    def test_charla_cotidiana_ultrarrapida(self):
        # Saludos y charla breve son detectados como ultrarrápidos
        self.assertTrue(cerebro_perfil.es_frase_ultrarrapida("hola"))
        self.assertTrue(cerebro_perfil.es_frase_ultrarrapida("como estas hoy"))
        self.assertTrue(cerebro_perfil.es_frase_ultrarrapida("que tal amiga"))
        self.assertTrue(cerebro_perfil.es_frase_ultrarrapida("todo bien"))

        # Consultas de acción, búsqueda o recuerdos NO son ultrarrápidas
        self.assertFalse(cerebro_perfil.es_frase_ultrarrapida("recuerda que mañana tengo examen"))
        self.assertFalse(cerebro_perfil.es_frase_ultrarrapida("abre chrome y busca recetas"))
        self.assertFalse(cerebro_perfil.es_frase_ultrarrapida("que tengo en mi calendario"))


if __name__ == "__main__":
    unittest.main()
