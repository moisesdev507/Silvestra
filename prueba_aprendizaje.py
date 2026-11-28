"""Pruebas unitarias para Fase 4B: Memoria Asociativa y Aprendizaje Continuo.

Valida búsqueda de recuerdos por afinidad semántica, gestión de hilos abiertos,
lecciones aprendidas, criterio propio e integración con ConsolidarSesion y
PuenteSubjetividad sin dependencias de red.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from aprendizaje_kaya import AprendizajeKaya
from consolidador_diario import ConsolidarSesion
from diario_kaya import DiarioKaya
from homeostasis import Homeostasis
from memoria_asociativa import MemoriaAsociativa
from pensamiento_interno import MotorPensamiento
from puente_subjetividad import PuenteSubjetividad, reiniciar_puente_para_pruebas


class TestMemoriaAsociativa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_db = os.path.join(self.tmp.name, "diario_test.db")
        self.diario = DiarioKaya(ruta_db=self.ruta_db)
        self.mem = MemoriaAsociativa(ruta_db=self.ruta_db)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_busqueda_asociativa_rescata_recuerdo_antiguo_relevante(self):
        # 1. Guardar recuerdo antiguo relevante sobre arquitectura y WebRTC
        self.diario.guardar_entrada(
            reflexion="Ayer resolvimos la latencia WebRTC optimizando buffers y PCM.",
            estado_animo="entusiasta",
            tema="webrtc y arquitectura de audio",
        )
        # 2. Guardar varios recuerdos recientes no relacionados
        for i in range(5):
            self.diario.guardar_entrada(
                reflexion=f"Hoy vimos recetas de cocina y ensaladas varias {i}.",
                estado_animo="tranquila",
                tema="cocina y alimentacion",
            )

        # 3. Consulta sobre WebRTC
        resultados = self.mem.buscar_recuerdos_relacionados("retrasos en audio WebRTC buffers", limite=2)
        self.assertTrue(len(resultados) >= 1)
        # El primer resultado debe ser el recuerdo antiguo de WebRTC, no las ensaladas recientes
        self.assertIn("webrtc", resultados[0]["tema"].lower())
        self.assertIn("pcm", resultados[0]["reflexion"].lower())

    def test_hilos_abiertos_apertura_deduplicacion_y_cierre(self):
        # Apertura de hilo
        h1 = self.mem.abrir_hilo("Proyecto Silvestra", "Revisar arquitectura Fase 4B")
        self.assertGreater(h1, 0)

        # Apertura de tema similar no crea duplicado, actualiza detalle
        h2 = self.mem.abrir_hilo("proyecto silvestra", "Actualización: afinar WebRTC y aprendizaje")
        self.assertEqual(h1, h2)

        abiertos = self.mem.obtener_hilos_abiertos(limite=5)
        self.assertEqual(len(abiertos), 1)
        self.assertEqual(abiertos[0]["detalle"], "Actualización: afinar WebRTC y aprendizaje")

        # Cierre de hilo
        ok = self.mem.cerrar_hilo(h1)
        self.assertTrue(ok)
        abiertos_post = self.mem.obtener_hilos_abiertos()
        self.assertEqual(len(abiertos_post), 0)

    def test_construir_bloque_asociativo(self):
        self.mem.abrir_hilo("Investigación", "Probar modelo Flash Lite")
        bloque = self.mem.construir_bloque_asociativo()
        self.assertIn("[TEMAS E HILOS PENDIENTES QUE RECUERDO]", bloque)
        self.assertIn("Investigación", bloque)


class TestAprendizajeKaya(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_db = os.path.join(self.tmp.name, "diario_ap.db")
        self.diario = DiarioKaya(ruta_db=self.ruta_db)
        self.ap = AprendizajeKaya(ruta_db=self.ruta_db)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_registro_leccion_upsert_y_limite_20(self):
        # Registro inicial
        ok = self.ap.registrar_leccion("Evitar frases serviles al hablar", origen="usuario")
        self.assertTrue(ok)

        # Upsert incrementa confianza
        self.ap.registrar_leccion("Evitar frases serviles al hablar", origen="usuario")
        with self.ap._conectar() as conn:
            fila = conn.execute("SELECT confianza FROM lecciones_aprendidas WHERE regla LIKE '%serviles%'").fetchone()
            self.assertGreater(float(fila["confianza"]), 0.7)

        # Retención máxima de 20 lecciones
        for i in range(25):
            self.ap.registrar_leccion(f"Regla de prueba {i}")

        with self.ap._conectar() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM lecciones_aprendidas").fetchone()["c"]
            self.assertLessEqual(total, 20)

    def test_registro_conocimiento_propio_y_aprender_en_silencio(self):
        self.ap.registrar_conocimiento("Python", "Es un lenguaje elegante cuando se estructura modularmente.")
        bloque = self.ap.construir_bloque_aprendizaje()
        self.assertIn("Python", bloque)
        self.assertIn("modularmente", bloque)

        mock_llm = lambda p: "La concurrencia en asyncio requiere aislamiento estricto."
        idea = self.ap.aprender_en_silencio("asyncio", cliente_llm=mock_llm)
        self.assertEqual(idea, "La concurrencia en asyncio requiere aislamiento estricto.")

        bloque_actualizado = self.ap.construir_bloque_aprendizaje()
        self.assertIn("asyncio", bloque_actualizado)

    def test_revisar_maduracion_sin_repeticion(self):
        # Con menos de 10 entradas no madura
        for i in range(5):
            self.diario.guardar_entrada(f"Reflexión {i}", "neutral", "general")
        self.assertFalse(self.ap.revisar_maduracion(self.diario))

        # Al llegar a 10 entradas sí madura
        for i in range(5, 10):
            self.diario.guardar_entrada(f"Reflexión {i}", "neutral", "general")

        mock_llm = lambda p: json.dumps({
            "etapa": "consolidación analítica",
            "rasgos": {"curiosidad": "alta", "enfoque": "arquitectura modular"}
        })

        maduro = self.ap.revisar_maduracion(self.diario, cliente_llm=mock_llm)
        self.assertTrue(maduro)

        # Misma cuenta de entradas no repite la maduración
        repetido = self.ap.revisar_maduracion(self.diario, cliente_llm=mock_llm)
        self.assertFalse(repetido)


class TestIntegracionSubjetividad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_db = os.path.join(self.tmp.name, "diario_int.db")
        self.ruta_est = os.path.join(self.tmp.name, "estado.json")
        self.diario = DiarioKaya(ruta_db=self.ruta_db)
        self.homeo = Homeostasis(ruta_archivo=self.ruta_est)
        self.mem = MemoriaAsociativa(ruta_db=self.ruta_db)
        self.ap = AprendizajeKaya(ruta_db=self.ruta_db)

        self.mock_llm = lambda p: json.dumps({
            "reflexion": "Hoy dialogamos sobre persistencia segura.",
            "tema": "persistencia",
            "rasgos": {"estilo": "cuidadoso"},
            "hilo_abierto": {"tema": "Refactor", "detalle": "Completar Fase 4B"},
            "leccion": "Priorizar siempre la verificabilidad de datos",
        })

        self.consolidador = ConsolidarSesion(
            diario=self.diario,
            cliente_llm=self.mock_llm,
            memoria_asociativa=self.mem,
            aprendizaje=self.ap,
        )

        self.puente = PuenteSubjetividad(
            homeostasis=self.homeo,
            diario=self.diario,
            consolidador=self.consolidador,
            memoria_asociativa=self.mem,
            aprendizaje=self.ap,
            ruta_datos=self.tmp.name,
        )
        reiniciar_puente_para_pruebas(self.puente)

    def tearDown(self):
        reiniciar_puente_para_pruebas(None)
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_consolidacion_guarda_hilo_y_leccion(self):
        turnos = [
            {"rol": "usuario", "texto": "Hola Kaya, analicemos la base de datos."},
            {"rol": "asistente", "texto": "De acuerdo, todo está listo en SQLite."},
            {"rol": "usuario", "texto": "¿Cómo organizamos las migraciones futuras?"},
            {"rol": "asistente", "texto": "Usaremos módulos atómicos y verificaciones."},
        ]
        exito = self.consolidador.consolidar(turnos, estado_animo="analitica")
        self.assertTrue(exito)

        hilos = self.mem.obtener_hilos_abiertos()
        self.assertEqual(len(hilos), 1)
        self.assertEqual(hilos[0]["tema"], "Refactor")

        bloque_ap = self.ap.construir_bloque_aprendizaje()
        self.assertIn("verificabilidad", bloque_ap)

    def test_bloque_identidad_incluye_asociaciones_y_aprendizaje(self):
        self.mem.abrir_hilo("Seguridad", "Revisar permisos locales")
        self.ap.registrar_leccion("No interrumpir al usuario mientras programa")
        self.ap.registrar_conocimiento("Arquitectura", "Los módulos deben ser auto-contenidos.")

        bloque = self.puente.construir_contexto_identidad()
        self.assertIn("Seguridad", bloque)
        self.assertIn("No interrumpir", bloque)
        self.assertIn("auto-contenidos", bloque)


if __name__ == "__main__":
    unittest.main()
