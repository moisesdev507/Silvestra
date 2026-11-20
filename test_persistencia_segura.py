"""Suite de pruebas para persistencia atómica y resiliente (Fase 1)."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest

import memoria
import persistencia_segura as ps
import recordatorios


class ObjetoNoSerializable:
    pass


class TestPersistenciaSegura(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_escritura_atomica_y_lectura(self):
        ruta = os.path.join(self.temp_dir, "test.json")
        datos = {"clave": "valor", "numero": 42, "lista": [1, 2, 3]}
        ok = ps.guardar_json_atomico(ruta, datos)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(ruta))

        cargado = ps.cargar_json_seguro(ruta)
        self.assertEqual(cargado, datos)

    def test_preservacion_archivo_previo_si_falla_escritura(self):
        ruta = os.path.join(self.temp_dir, "previo.json")
        datos_originales = {"estado": "intacto", "version": 1}
        self.assertTrue(ps.guardar_json_atomico(ruta, datos_originales))

        # Intentar guardar un objeto no serializable para provocar fallo a mitad de proceso
        fallo_datos = {"invalido": ObjetoNoSerializable()}
        ok = ps.guardar_json_atomico(ruta, fallo_datos)
        self.assertFalse(ok)

        # El archivo original debe seguir intacto
        cargado = ps.cargar_json_seguro(ruta)
        self.assertEqual(cargado, datos_originales)

    def test_recuperacion_json_corrupto_o_vacio(self):
        ruta_corrupta = os.path.join(self.temp_dir, "corrupto.json")
        with open(ruta_corrupta, "w", encoding="utf-8") as f:
            f.write("{ json truncado...")

        # Debe retornar defecto sin lanzar excepción
        resultado = ps.cargar_json_seguro(ruta_corrupta, defecto={"recuperado": True})
        self.assertEqual(resultado, {"recuperado": True})

        # Archivo vacío
        ruta_vacia = os.path.join(self.temp_dir, "vacio.json")
        with open(ruta_vacia, "w", encoding="utf-8") as f:
            f.write("")
        self.assertIsNone(ps.cargar_json_seguro(ruta_vacia))

    def test_concurrencia_multihilo_memoria(self):
        ruta_mem = os.path.join(self.temp_dir, "memoria_concurrente.json")
        orig = memoria.ARCHIVO_MEMORIA
        memoria.ARCHIVO_MEMORIA = ruta_mem
        try:
            mem = memoria.Memoria()
            mem.guardar()
            errores = []

            def worker(idx: int):
                try:
                    for i in range(20):
                        mem.recordar(f"Dato hilo {idx} iter {i}")
                except Exception as e:
                    errores.append(e)

            hilos = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()

            self.assertEqual(len(errores), 0)
            mem_recargada = memoria.Memoria()
            self.assertGreater(len(mem_recargada.hechos), 0)
        finally:
            memoria.ARCHIVO_MEMORIA = orig

    def test_concurrencia_multihilo_recordatorios(self):
        ruta_rec = os.path.join(self.temp_dir, "recordatorios_concurrente.json")
        orig = recordatorios.RUTA_JSON
        recordatorios.RUTA_JSON = ruta_rec
        try:
            errores = []

            def worker(idx: int):
                try:
                    for i in range(15):
                        datos = recordatorios._cargar()
                        datos.append({"id": idx * 100 + i, "texto": f"Rec {idx}-{i}"})
                        recordatorios._guardar(datos)
                except Exception as e:
                    errores.append(e)

            hilos = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()

            self.assertEqual(len(errores), 0)
            datos_finales = recordatorios._cargar()
            self.assertIsInstance(datos_finales, list)
            self.assertGreater(len(datos_finales), 0)
        finally:
            recordatorios.RUTA_JSON = orig


if __name__ == "__main__":
    unittest.main()
