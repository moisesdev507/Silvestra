"""Pruebas del almacén cognitivo, FTS5 y migración JSON no destructiva."""
import hashlib
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO

import memoria
from memoria_almacen import AlmacenMemoriaCognitiva
from memoria_migrador import migrar_legado_a_sqlite


class TestAlmacenCognitivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "prueba.db")
        self.store = AlmacenMemoriaCognitiva(self.db)

    def tearDown(self):
        self.store.cerrar()
        self.tmp.cleanup()

    def test_esquema_wal_y_fts5(self):
        self.assertEqual(self.store.conexion.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        nombres = {r[0] for r in self.store.conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"recuerdos", "recuerdos_fts", "entidades", "relaciones", "migraciones_estado"} <= nombres)
        self.assertEqual(self.store.conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertTrue(self.store.conexion.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()[0])

    def test_insercion_deduplicacion_y_busqueda_segura(self):
        uno = self.store.guardar_recuerdo("Le gusta el café de altura", origen="explicito")
        dos = self.store.guardar_recuerdo("LE GUSTA EL CAFÉ, DE ALTURA.", origen="inferido")
        self.assertEqual(uno["id"], dos["id"])
        self.assertEqual(self.store.contar_recuerdos(), 1)
        resultados = self.store.buscar_texto('¿qué "café" OR [altura] (*):?', limite=5)
        self.assertTrue(any(r["id"] == uno["id"] for r in resultados))
        self.assertEqual(self.store.buscar_texto("!!!???"), [])

    def test_actualizacion_reemplazo_y_borrados(self):
        viejo = self.store.guardar_recuerdo("El proyecto usa una base anterior")
        act = self.store.actualizar_recuerdo(viejo["id"], confianza=0.55, categoria="proyecto")
        self.assertEqual(act["confianza"], 0.55)
        nuevo = self.store.reemplazar_recuerdo(viejo["id"], "El proyecto usa SQLite")
        self.assertEqual(nuevo["reemplaza_a_id"], viejo["id"])
        self.assertEqual(self.store.listar_recuerdos(solo_activos=False)[0]["estado"], "obsoleto")
        self.assertTrue(self.store.eliminar_recuerdo(nuevo["id"]))
        self.assertFalse(self.store.listar_recuerdos())
        fisico = self.store.guardar_recuerdo("Registro temporal para borrado físico")
        self.assertTrue(self.store.eliminar_recuerdo(fisico["id"], fisico=True))

    def test_concurrencia_y_olvido_por_tema(self):
        errores = []
        def worker(n):
            try:
                for i in range(20):
                    self.store.guardar_recuerdo(f"Dato de grupo {n}, entrada {i}")
            except Exception as exc:
                errores.append(exc)
        hilos = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
        [h.start() for h in hilos]
        [h.join(5) for h in hilos]
        self.assertFalse(any(h.is_alive() for h in hilos))
        self.assertEqual(errores, [])
        self.assertEqual(self.store.contar_recuerdos(), 120)
        self.assertGreater(self.store.olvidar_por_tema("grupo 2"), 0)

    def test_no_registra_contenido_literal(self):
        secreto_prueba = "frase-unica-privada-5928"
        salida = StringIO()
        with redirect_stdout(salida):
            self.store.guardar_recuerdo(secreto_prueba)
            ruta_json = os.path.join(self.tmp.name, "sin_logs.json")
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump({"hechos": [], "resumenes_tematicos": {}}, f)
            fachada = memoria.Memoria(ruta_json=ruta_json,
                ruta_db=os.path.join(self.tmp.name, "sin_logs.db"))
            try:
                fachada.recordar("La frase de privacidad debe permanecer fuera del registro")
            finally:
                fachada.cerrar()
        self.assertNotIn(secreto_prueba, salida.getvalue())
        self.assertNotIn("La frase de privacidad debe permanecer fuera del registro", salida.getvalue())

    def test_migracion_idempotente_y_json_intactos(self):
        fuentes = {
            "memoria.json": {"hechos": ["Vive en una ciudad costera"], "resumenes_tematicos": {"trabajo": "Coordina un equipo"}},
            "ideas.json": [{"texto": "Mejorar el tablero", "veces": 2, "fecha": "2026-01-02"}],
            "hilos.json": [{"texto": "Revisar el plan", "estado": "abierto", "fecha": "2026-01-03"}],
            "correcciones.json": [{"texto": "Usar el nombre correcto", "fecha": "2026-01-04"}],
        }
        hashes = {}
        for nombre, datos in fuentes.items():
            ruta = os.path.join(self.tmp.name, nombre)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
            with open(ruta, "rb") as f:
                hashes[nombre] = hashlib.sha256(f.read()).hexdigest()
        primero = migrar_legado_a_sqlite(self.store, self.tmp.name)
        segundo = migrar_legado_a_sqlite(self.store, self.tmp.name)
        self.assertEqual(primero["migrados"], 5)
        self.assertTrue(segundo["ya_aplicada"])
        self.assertEqual(self.store.contar_recuerdos(), 5)
        hilo = next(r for r in self.store.buscar_texto("Revisar el plan")
                    if r["metadatos"].get("categoria") == "hilo")
        self.assertEqual(hilo["metadatos"]["categoria"], "hilo")
        self.assertEqual(hilo["metadatos"]["fecha_original"], "2026-01-03")
        for nombre, digest in hashes.items():
            with open(os.path.join(self.tmp.name, nombre), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest)

    def test_fachada_memoria_compatible_y_ruta_aislada(self):
        ruta_json = os.path.join(self.tmp.name, "memoria.json")
        ruta_db = os.path.join(self.tmp.name, "fachada.db")
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump({"hechos": [], "resumenes_tematicos": {}}, f)
        m = memoria.Memoria(ruta_json=ruta_json, ruta_db=ruta_db)
        try:
            self.assertTrue(m.recordar("Prefiere caminar temprano"))
            self.assertTrue(m.hechos)
            self.assertIn("caminar", m.consultar("caminar"))
            self.assertIn("olvidado", m.olvidar("caminar"))
            self.assertEqual(m.almacen.contar_recuerdos(), 0)
        finally:
            m.cerrar()
        self.assertTrue(os.path.isfile(ruta_db))
        self.assertTrue(os.path.isfile(ruta_json))


if __name__ == "__main__":
    unittest.main()
