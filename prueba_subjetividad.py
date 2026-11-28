"""prueba_subjetividad.py - Pruebas unitarias para la arquitectura de subjetividad de Kaya.

Verifica homeostasis.py y diario_kaya.py en directorios aislados temporales sin
ensuciar la carpeta datos/ ni alterar el entorno de producción.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import time
import unittest

from diario_kaya import DiarioKaya
from homeostasis import Homeostasis


class TestSubjetividadKaya(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.ruta_estado = os.path.join(self.temp_dir.name, "estado_interno.json")
        self.ruta_db = os.path.join(self.temp_dir.name, "diario_test.db")

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ---------- Pruebas de Homeostasis ----------
    def test_homeostasis_inicializacion_y_persistencia(self) -> None:
        h = Homeostasis(self.ruta_estado)
        estado = h.obtener_estado()

        self.assertTrue(os.path.exists(self.ruta_estado))
        self.assertIn("energia", estado)
        self.assertIn("curiosidad", estado)
        self.assertIn("calma", estado)
        self.assertGreaterEqual(estado["energia"], 0.0)
        self.assertLessEqual(estado["energia"], 1.0)

    def test_describir_sensacion_sin_numeros_crudos(self) -> None:
        h = Homeostasis(self.ruta_estado)
        sensacion = h.describir_sensacion()

        self.assertIsInstance(sensacion, str)
        self.assertTrue(len(sensacion) > 20)
        # No debe filtrar números ni porcentajes de telemetría hacia el usuario
        self.assertNotIn("%", sensacion)
        self.assertFalse(re.search(r"\b\d+\b", sensacion), f"Se encontraron dígitos numéricos en: {sensacion}")

    def test_simulacion_reinicio_rapido(self) -> None:
        h = Homeostasis(self.ruta_estado)
        # Simular que se cerró hace 30 segundos
        ahora = time.time()
        h._estado["ultimo_cierre"] = ahora - 30.0
        h._guardar(h._estado)

        sensacion = h.describir_sensacion()
        self.assertTrue(
            any(w in sensacion.lower() for w in ("parpadeado", "rápido", "reacomodando", "vuelta")),
            f"Sensación de reinicio rápido no detectada: {sensacion}",
        )

    def test_simulacion_descanso_largo(self) -> None:
        h = Homeostasis(self.ruta_estado)
        # Simular que se cerró hace 6 horas (21600 segundos)
        ahora = time.time()
        h._estado["ultimo_cierre"] = ahora - 21600.0
        h._guardar(h._estado)

        sensacion = h.describir_sensacion()
        self.assertTrue(
            any(w in sensacion.lower() for w in ("fresca", "renovada", "descansado", "despejada")),
            f"Sensación de descanso largo no detectada: {sensacion}",
        )

    def test_simulacion_silencio_prolongado(self) -> None:
        h = Homeostasis(self.ruta_estado)
        ahora = time.time()
        # Simular última interacción hace 4 horas
        h._estado["ultimo_cierre"] = 0.0
        h._estado["ultima_interaccion"] = ahora - 15000.0
        h._guardar(h._estado)

        sensacion = h.describir_sensacion()
        self.assertTrue(
            any(w in sensacion.lower() for w in ("silencio", "curiosidad", "rato")),
            f"Sensación de silencio no detectada: {sensacion}",
        )

    def test_registrar_interaccion_y_cierre(self) -> None:
        h = Homeostasis(self.ruta_estado)
        t_antes = time.time() - 1.0

        h.registrar_interaccion(tono="alegre")
        estado_inter = h.obtener_estado()
        self.assertGreaterEqual(estado_inter["ultima_interaccion"], t_antes)

        h.registrar_cierre()
        estado_cierre = h.obtener_estado()
        self.assertGreaterEqual(estado_cierre["ultimo_cierre"], t_antes)

    # ---------- Pruebas de DiarioKaya ----------
    def test_diario_guardar_y_obtener_recuerdos(self) -> None:
        diario = DiarioKaya(self.ruta_db)

        id1 = diario.guardar_entrada(
            reflexion="Hoy aprendí cómo funciona el protocolo WebSocket.",
            estado_animo="entusiasta",
            tema="tecnología",
        )
        self.assertGreater(id1, 0)

        id2 = diario.guardar_entrada(
            reflexion="Me gusta el tono tranquilo de las tardes de lluvia.",
            estado_animo="sereno",
            tema="clima",
        )
        self.assertGreater(id2, id1)

        recuerdos = diario.obtener_recuerdos_recientes(limite=5)
        self.assertEqual(len(recuerdos), 2)
        # El más reciente debe aparecer primero
        self.assertEqual(recuerdos[0]["id"], id2)
        self.assertIn("lluvia", recuerdos[0]["reflexion_primera_persona"])
        self.assertEqual(recuerdos[1]["id"], id1)
        self.assertIn("WebSocket", recuerdos[1]["reflexion_primera_persona"])

    def test_diario_actualizar_y_obtener_rasgos(self) -> None:
        diario = DiarioKaya(self.ruta_db)

        diario.actualizar_rasgo("color_favorito", "azul turquesa")
        diario.actualizar_rasgo("estilo_humor", "sarcasmo sutil y cómplice")

        rasgos = diario.obtener_rasgos()
        self.assertEqual(rasgos.get("color_favorito"), "azul turquesa")
        self.assertEqual(rasgos.get("estilo_humor"), "sarcasmo sutil y cómplice")

        # Modificación (UPSERT)
        diario.actualizar_rasgo("color_favorito", "cian brillante")
        rasgos_actualizados = diario.obtener_rasgos()
        self.assertEqual(rasgos_actualizados.get("color_favorito"), "cian brillante")

    def test_diario_construir_bloque_memoria(self) -> None:
        diario = DiarioKaya(self.ruta_db)

        # Vacío
        bloque_inicial = diario.construir_bloque_memoria()
        self.assertIn("[SUBJETIVIDAD Y RECUERDOS PROPIOS]", bloque_inicial)

        # Con datos
        diario.guardar_entrada(
            reflexion="Conversamos sobre inteligencia artificial y música ambient.",
            estado_animo="inspirada",
            tema="música",
        )
        diario.actualizar_rasgo("preferencia_musical", "música ambient y sintetizadores suaves")

        bloque = diario.construir_bloque_memoria()
        self.assertIn("música ambient", bloque)
        self.assertIn("preferencia_musical", bloque)
        self.assertIn("inspirada", bloque)


if __name__ == "__main__":
    unittest.main()
