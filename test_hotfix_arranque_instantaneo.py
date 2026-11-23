"""Regresión: saludo de arranque local, variado e instantáneo (sin HTTP)."""
import queue
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import estado
import nacimiento


def _hora(hora):
    return time.struct_time((2026, 11, 23, hora, 0, 0, 0, 0, 0))


class TestHotfixArranqueInstantaneo(unittest.TestCase):
    def setUp(self):
        self.estado_falso = {"ultima_vez": None, "ultimo_saludo": ""}

    @staticmethod
    def _app():
        return SimpleNamespace(
            cola=queue.Queue(),
            memoria=SimpleNamespace(creador="Moisés", nombre="Lyris"),
        )

    def _generar(self, hora):
        app = self._app()
        with patch("time.localtime", return_value=_hora(hora)), \
             patch.object(estado, "cargar", lambda: self.estado_falso), \
             patch.object(estado, "guardar", lambda datos: None), \
             patch("proveedores.completar",
                   side_effect=AssertionError("El saludo no debe llamar a la red")):
            t0 = time.perf_counter()
            nacimiento.generar_saludo(app)
            duracion = time.perf_counter() - t0
        self.assertFalse(app.cola.empty())
        evento = app.cola.get_nowait()
        self.assertEqual(evento[0], "saludo_inicial")
        return duracion, evento[1]

    def test_saludo_local_menos_de_50_ms_y_sin_http(self):
        duracion, (texto, emocion) = self._generar(9)
        self.assertLess(duracion, 0.05, f"saludo tardó {duracion:.4f}s")
        self.assertTrue(texto.startswith("Buenos días"), texto)
        self.assertEqual(emocion, "alegre")
        self.assertLessEqual(len(texto.split()), 25)
        self.assertEqual(self.estado_falso["ultimo_saludo"], texto)
        self.assertIsNotNone(self.estado_falso["ultima_vez"])

    def test_saludo_varia_segun_franja_horaria(self):
        manana = self._generar(9)[1][0]
        tarde = self._generar(15)[1][0]
        noche = self._generar(22)[1][0]
        self.assertTrue(manana.startswith("Buenos días"), manana)
        self.assertTrue(tarde.startswith("Buenas tardes"), tarde)
        self.assertTrue(noche.startswith("Buenas noches"), noche)
        self.assertEqual(len({manana, tarde, noche}), 3)
        self.assertEqual(self._generar(15)[1][1], "calida")
        self.assertEqual(self._generar(22)[1][1], "calida")

    def test_no_repite_el_ultimo_saludo_guardado(self):
        primero = nacimiento.SALUDOS["manana"][0].format(creador="Moisés", nombre="Lyris")
        self.estado_falso["ultimo_saludo"] = primero
        with patch("time.localtime", return_value=_hora(9)), \
             patch.object(estado, "cargar", lambda: self.estado_falso), \
             patch.object(estado, "guardar", lambda datos: None), \
             patch.object(nacimiento.random, "choice", lambda opciones: opciones[0]):
            app = self._app()
            nacimiento.generar_saludo(app)
        _, (texto, _emocion) = app.cola.get_nowait()
        self.assertNotEqual(texto, primero)
        self.assertIn(texto, [
            frase.format(creador="Moisés", nombre="Lyris")
            for frase in nacimiento.SALUDOS["manana"]
        ])

    def test_banco_cubre_todas_las_franjas(self):
        self.assertEqual(set(nacimiento.SALUDOS), {"manana", "tarde", "noche"})
        total = sum(len(frases) for frases in nacimiento.SALUDOS.values())
        self.assertGreaterEqual(total, 6)
        self.assertLessEqual(total, 8)
        for frases in nacimiento.SALUDOS.values():
            for frase in frases:
                self.assertIn("{creador}", frase)
                self.assertNotIn("{", frase.format(creador="Moisés", nombre="Lyris"))


if __name__ == "__main__":
    unittest.main()
