import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import memoria
from memoria_almacen import AlmacenMemoriaCognitiva
from memoria_gestor import GestorMemoria
from memoria_migrador import migrar_legado_a_sqlite
from memoria_modelos import OrigenMemoria, Recuerdo, TipoMemoria


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
        row = self.store.guardar_recuerdo("El índice conserva este texto de manera consistente")
        self.assertTrue(self.store.buscar_texto("índice conserva"))
        self.store.actualizar_recuerdo(row["id"], nuevo_contenido="Información recién modificada y segura")
        self.assertEqual(self.store.buscar_texto("índice conserva"), [])
        self.assertTrue(self.store.buscar_texto("modificada segura"))
        self.store.eliminar_recuerdo(row["id"], fisico=True)
        self.assertEqual(self.store.buscar_texto("modificada segura"), [])

    def test_insercion_deduplicacion_y_busqueda_segura(self):
        uno = self.store.guardar_recuerdo("Le gusta el café de altura", origen="explicito")
        dos = self.store.guardar_recuerdo("LE GUSTA EL CAFÉ, DE ALTURA.", origen="inferido")
        self.assertEqual(uno["id"], dos["id"])
        self.assertEqual(self.store.contar_recuerdos(), 1)
        resultados = self.store.buscar_texto('¿qué "café" OR [altura] (*):?', limite=5)
        self.assertTrue(any(r["id"] == uno["id"] for r in resultados))
        self.assertEqual(self.store.buscar_texto("!!!???"), [])
        with self.assertRaises(ValueError):
            self.store.guardar_recuerdo("x", confianza=1.2)
        with self.assertRaises(ValueError):
            self.store.guardar_recuerdo("dato con sintaxis", tipo_memoria="desconocida")

    def test_crud(self):
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
        privado = "Este recuerdo privado no debe aparecer en los logs"
        salida = StringIO()
        with redirect_stdout(salida):
            self.store.guardar_recuerdo(secreto_prueba)
            ruta_json = os.path.join(self.tmp.name, "sin_logs.json")
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump({"hechos": [], "resumenes_tematicos": {}}, f)
            fachada = memoria.Memoria(ruta_json=ruta_json,
                ruta_db=os.path.join(self.tmp.name, "sin_logs.db"))
            try:
                fachada.recordar(privado)
            finally:
                fachada.cerrar()
        self.assertNotIn(secreto_prueba, salida.getvalue())
        self.assertNotIn(privado, salida.getvalue())

    def test_migracion_json(self):
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

    def test_modelos_tipos_y_validacion_estricta(self):
        texto = "Dato válido suficientemente descriptivo"
        for tipo in (TipoMemoria.EPISODICA, TipoMemoria.SEMANTICA, TipoMemoria.PROCEDIMENTAL):
            item = Recuerdo("ana", tipo, texto, OrigenMemoria.INFERIDO, 0.4)
            self.assertEqual(item.origen, "inferido")
            self.assertTrue(item.creado_en and item.actualizado_en)
        trabajo = Recuerdo("ana", "trabajo", "Tarea temporal que se está procesando")
        self.assertEqual(trabajo.tipo_memoria, "trabajo")
        for uid in ("", " ana", "a/b"):
            with self.assertRaises(ValueError):
                Recuerdo(uid, "semantica", texto)
        with self.assertRaises(ValueError):
            Recuerdo("ana", "semantica", "texto", confianza=-0.1)

    def test_usuario_id_aisla_fts_crud_y_deduplicacion(self):
        texto = "La cuenta tiene preferencia especial"
        ana = self.store.guardar_recuerdo(texto, usuario_id="ana")
        bob = self.store.guardar_recuerdo(texto, usuario_id="bob")
        self.assertNotEqual(ana["id"], bob["id"])
        self.assertEqual(ana["usuario_id"], "ana")
        repetido = self.store.guardar_recuerdo(texto.upper(), usuario_id="ana")
        self.assertEqual(repetido["id"], ana["id"])
        self.assertEqual([r["usuario_id"] for r in self.store.buscar_texto("preferencia")], [])
        self.assertEqual(len(self.store.buscar_texto("preferencia", usuario_id="ana")), 1)
        self.assertEqual(len(self.store.buscar_texto("preferencia", usuario_id="bob")), 1)
        self.assertIsNone(self.store.actualizar_recuerdo(ana["id"], confianza=.2, usuario_id="bob"))
        self.assertFalse(self.store.eliminar_recuerdo(ana["id"], usuario_id="bob"))
        with self.assertRaises(KeyError):
            self.store.reemplazar_recuerdo(ana["id"], "La cuenta fue actualizada de forma segura", usuario_id="bob")
        self.assertEqual(self.store.contar_recuerdos(usuario_id="ana"), 1)
        self.assertEqual(self.store.contar_recuerdos(usuario_id="bob"), 1)

    def test_trabajo_aislado_ttl(self):
        gestor = GestorMemoria(self.store, "ana", capacidad_trabajo=2, ttl_trabajo=2)
        gestor.agregar_trabajo("a", "Primera tarea temporal de Ana")
        gestor.agregar_trabajo("b", "Segunda tarea temporal de Ana")
        gestor.agregar_trabajo("c", "Tercera tarea temporal de Ana")
        self.assertIsNone(gestor.obtener_trabajo("a", "ana"))
        self.assertIsNone(gestor.obtener_trabajo("b", "bob"))
        gestor.agregar_trabajo("corta", "Dato corto pero válido de trabajo", ttl=1)
        time.sleep(1.02)
        self.assertIsNone(gestor.obtener_trabajo("corta", "ana"))
        self.assertEqual(gestor.cambiar_perfil("bob"), "ana")
        self.assertEqual(gestor.listar_trabajo("ana"), [])
        with self.assertRaises(ValueError):
            gestor.agregar_trabajo("privado", "Mi password secreto es 123456")

    def test_filtro_privacidad(self):
        gestor = GestorMemoria(self.store)
        with self.assertRaises(ValueError):
            gestor.guardar("La contraseña de mi cuenta es 123456")
        self.assertEqual(self.store.contar_recuerdos(), 0)

    def test_actualiza_esquema(self):
        ruta = os.path.join(self.tmp.name, "anterior.db")
        con = sqlite3.connect(ruta)
        con.executescript("""CREATE TABLE recuerdos(id INTEGER PRIMARY KEY AUTOINCREMENT,
          tipo_memoria TEXT NOT NULL,contenido TEXT NOT NULL,contenido_norm TEXT NOT NULL,
          categoria TEXT DEFAULT 'general',origen TEXT NOT NULL,confianza REAL NOT NULL DEFAULT .8,
          estado TEXT NOT NULL DEFAULT 'activo',reemplaza_a_id INTEGER,fecha_evento TEXT,
          creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL,metadatos_json TEXT DEFAULT '{}',embedding BLOB);
          INSERT INTO recuerdos(tipo_memoria,contenido,contenido_norm,origen,creado_en,actualizado_en)
          VALUES('semantica','Recuerdo anterior suficientemente largo','recuerdo anterior suficientemente largo',
          'migrado','2026-01-01','2026-01-01');""")
        con.close()
        upgraded = AlmacenMemoriaCognitiva(ruta)
        try:
            registro = upgraded.buscar_texto("recuerdo anterior")[0]
            self.assertEqual(registro["usuario_id"], "local")
            self.assertEqual(registro["contenido"], "Recuerdo anterior suficientemente largo")
            names = {r[1] for r in upgraded.conexion.execute("PRAGMA index_list(recuerdos)")}
            self.assertIn("idx_recuerdos_usuario_norm", names)
        finally:
            upgraded.cerrar()

    def test_reinicio_perfil_integracion(self):
        ruta = os.path.join(self.tmp.name, "reinicio.db")
        uno = AlmacenMemoriaCognitiva(ruta, "ana")
        recuerdo = uno.guardar_recuerdo("Ana prepara una presentación importante", tipo_memoria="episodica")
        uno.cerrar()
        dos = AlmacenMemoriaCognitiva(ruta, "ana")
        otro = AlmacenMemoriaCognitiva(ruta, "bob")
        try:
            self.assertEqual(dos.buscar_texto("presentación")[0]["id"], recuerdo["id"])
            self.assertEqual(otro.buscar_texto("presentación"), [])
            local = memoria.Memoria(ruta_db=ruta, usuario_id="ana")
            remoto = memoria.Memoria(ruta_db=ruta, usuario_id="bob")
            try:
                self.assertIn("presentación", local.hechos[0])
                self.assertEqual(remoto.hechos, [])
                from cerebro import Cerebro
                self.assertIs(Cerebro(None, local).memoria, local)
                import iniciativa
                app = SimpleNamespace(memoria=local, cara=SimpleNamespace())
                with patch("iniciativa.estado.cargar", return_value={"iniciativa": False}), \
                     patch("iniciativa.iniciativa_contextual.obtener_motor_iniciativa", return_value=object()):
                    self.assertIs(iniciativa.Iniciativa(app).app.memoria, local)
            finally:
                local.cerrar()
                remoto.cerrar()
        finally:
            dos.cerrar()
            otro.cerrar()

    def test_cancelacion(self):
        gestor = GestorMemoria(self.store, "local")
        evento = threading.Event()
        evento.set()
        lote = [{"contenido": "Registro por lote suficientemente largo", "tipo_memoria": "semantica"}]
        salida = gestor.procesar_lote(lote, token_cancelacion=evento)
        self.assertTrue(salida["cancelado"])
        self.assertEqual(salida["resultados"], [])
        ruta = os.path.join(self.tmp.name, "migrable")
        os.makedirs(ruta)
        with open(os.path.join(ruta, "memoria.json"), "w", encoding="utf-8") as f:
            json.dump({"hechos": ["Recuerdo migrable y suficientemente largo"], "resumenes_tematicos": {}}, f)
        cancelada = migrar_legado_a_sqlite(self.store, ruta, token_cancelacion=evento)
        self.assertTrue(cancelada["cancelado"])
        evento.clear()
        reintento = migrar_legado_a_sqlite(self.store, ruta, token_cancelacion=evento)
        self.assertFalse(reintento["cancelado"])
        self.assertEqual(reintento["migrados"], 1)\n