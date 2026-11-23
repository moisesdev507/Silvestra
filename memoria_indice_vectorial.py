"""Índice vectorial sobre la columna embedding ya existente en SQLite.

Lecturas y escrituras usan el RLock del almacén. El backfill corre en un hilo
daemon, por lotes cortos y cancelable; nunca toca widgets Qt.
"""
import collections
import json
import threading
import time

import numpy as np

import memoria_embeddings as me


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None))
                and token.is_set())


def guardar_embedding(almacen, recuerdo_id, vector, tipo=me.TIPO_FALLBACK,
                      usuario_id=None):
    """Persiste el vector cuantizado. No lanza hacia arriba."""
    try:
        blob = me.cuantizar(vector, tipo)
        return bool(almacen.actualizar_embedding(int(recuerdo_id), blob, usuario_id))
    except Exception:
        return False


def leer_embedding(almacen, recuerdo_id, usuario_id=None):
    """Devuelve (vector, tipo) o None."""
    uid = almacen._uid(usuario_id)
    try:
        with almacen._lock:
            fila = almacen.conexion.execute(
                "SELECT embedding FROM recuerdos WHERE id=? AND usuario_id=?",
                (int(recuerdo_id), uid)).fetchone()
        if not fila or fila[0] is None:
            return None
        return me.desquantizar(fila[0])
    except Exception:
        return None


def tipo_dominante(almacen, usuario_id=None):
    """1 si hay vectores de API; 0 en caso contrario (modo offline puro)."""
    uid = almacen._uid(usuario_id)
    try:
        with almacen._lock:
            fila = almacen.conexion.execute(
                "SELECT 1 FROM recuerdos WHERE usuario_id=? AND estado='activo' "
                "AND embedding IS NOT NULL AND hex(substr(embedding,1,1))='01' LIMIT 1",
                (uid,)).fetchone()
        return me.TIPO_API if fila else me.TIPO_FALLBACK
    except Exception:
        return me.TIPO_FALLBACK


def candidatos_vectoriales(almacen, vector, tipo=None, usuario_id=None,
                           limite=20, min_similitud=0.10, max_explorados=1500):
    """Recuerdos con vectorizable cercana; devuelve items tipo `_fila` + similitud."""
    uid = almacen._uid(usuario_id)
    tipo = tipo_dominante(almacen, uid) if tipo is None else int(tipo)
    limite = max(0, min(int(limite), 100))
    max_explorados = max(1, min(int(max_explorados), 5000))
    try:
        with almacen._lock:
            filas = almacen.conexion.execute(
                "SELECT id,contenido,embedding,confianza,fecha_evento,creado_en,"
                "actualizado_en,tipo_memoria,categoria,origen,metadatos_json "
                "FROM recuerdos WHERE usuario_id=? AND estado='activo' "
                "AND embedding IS NOT NULL ORDER BY actualizado_en DESC LIMIT ?",
                (uid, max_explorados)).fetchall()
    except Exception:
        return []

    similitudes, patrones = [], []
    for fila in filas:
        if fila[2] is None:
            continue
        decodificado = me.desquantizar(fila[2])
        if not decodificado or decodificado[1] != tipo:
            continue
        sim = me.coseno(vector, decodificado[0])
        if sim >= min_similitud:
            similitudes.append(sim)
            patrones.append(fila)

    if not patrones:
        return []
    orden = np.argsort(np.asarray(similitudes, dtype=np.float32))[::-1][:limite]
    resultados = []
    for i in orden:
        fila = patrones[int(i)]
        try:
            meta = json.loads(fila[10] or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except (TypeError, ValueError):
            meta = {}
        resultados.append({
            "id": fila[0], "contenido": fila[1], "confianza": fila[3],
            "fecha_evento": fila[4], "creado_en": fila[5], "actualizado_en": fila[6],
            "tipo_memoria": fila[7] or "semantica", "categoria": fila[8] or "general",
            "origen": fila[9] or "inferido", "metadatos": meta,
            "similitud_vectorial": round(float(similitudes[int(i)]), 4),
        })
    return resultados


def sin_embedding(almacen, usuario_id=None, limite=8):
    """Recuerdos activos sin vector, para backfill progresivo."""
    uid = almacen._uid(usuario_id)
    try:
        with almacen._lock:
            filas = almacen.conexion.execute(
                "SELECT id,contenido FROM recuerdos WHERE usuario_id=? "
                "AND estado='activo' AND embedding IS NULL ORDER BY id LIMIT ?",
                (uid, max(1, min(int(limite), 100)))).fetchall()
        return [{"id": f[0], "contenido": f[1]} for f in filas]
    except Exception:
        return []


def backfill(almacen, usuario_id=None, limite=8, max_segundos=0.30,
             token_cancelacion=None):
    """Procesa un lote corto de recuerdos sin embedding. Seguro y cancelable."""
    if _cancelado(token_cancelacion):
        return {"procesados": 0, "cancelado": True}
    inicio = time.monotonic()
    filas = sin_embedding(almacen, usuario_id, limite)
    procesados = 0
    for fila in filas:
        if _cancelado(token_cancelacion):
            break
        if time.monotonic() - inicio > max_segundos:
            break
        try:
            vector, tipo = me.vector_con_tipo(
                me.texto_para_indice(fila["contenido"]), "documento", True)
            if guardar_embedding(almacen, fila["id"], vector, tipo, usuario_id):
                procesados += 1
        except Exception:
            continue
    return {"procesados": procesados, "cancelado": _cancelado(token_cancelacion)}


class BackfillVectorial:
    """Worker daemon: drena altas recientes y escanea recuerdos antiguos."""

    def __init__(self, almacen, usuario_id=None, intervalo=2.5):
        self.almacen = almacen
        self.usuario_id = usuario_id
        self.intervalo = max(0.5, float(intervalo))
        self._lock = threading.RLock()
        self._cola = collections.deque()
        self._evento = threading.Event()
        self._cancel = threading.Event()
        self._hilo = None

    def encolar(self, recuerdo_id):
        with self._lock:
            self._cola.append(int(recuerdo_id))
            self._evento.set()

    def iniciar(self, retardo=1.5):
        with self._lock:
            if self._hilo and self._hilo.is_alive():
                return self._hilo
            self._cancel.clear()
            self._hilo = threading.Thread(target=self._bucle, args=(retardo,),
                                          name="silvestra-backfill-embeddings",
                                          daemon=True)
            self._hilo.start()
            return self._hilo

    def detener(self):
        self._cancel.set()
        self._evento.set()

    def _drenar(self):
        with self._lock:
            ids = list(self._cola)
            self._cola.clear()
            self._evento.clear()
        return ids

    def _procesar_ids(self, ids):
        uid = self.usuario_id
        try:
            with self.almacen._lock:
                marcas = ",".join("?" for _ in ids)
                filas = self.almacen.conexion.execute(
                    "SELECT id,contenido FROM recuerdos WHERE id IN (" + marcas + ")",
                    tuple(ids)).fetchall()
        except Exception:
            return 0
        hechos = 0
        for fila in filas:
            if self._cancel.is_set():
                break
            try:
                vector, tipo = me.vector_con_tipo(
                    me.texto_para_indice(fila[1]), "documento", True)
                if guardar_embedding(self.almacen, fila[0], vector, tipo, uid):
                    hechos += 1
            except Exception:
                continue
        return hechos

    def _bucle(self, retardo):
        if retardo > 0 and self._cancel.wait(retardo):
            return
        while not self._cancel.is_set():
            ids = self._drenar()
            upgrade = self._procesar_ids(ids) if ids else 0
            legado = backfill(self.almacen, self.usuario_id, limite=6,
                              max_segundos=0.35,
                              token_cancelacion=self._cancel)["procesados"]
            if not ids and not upgrade and not legado:
                self._evento.wait(self.intervalo)


def obtener_backfill(almacen, usuario_id=None):
    """Crea (una sola vez) el worker asociado al almacén."""
    bloqueo = getattr(almacen, "_lock", threading.RLock())
    with bloqueo:
        worker = getattr(almacen, "_backfill_vectorial", None)
        if worker is None:
            worker = BackfillVectorial(almacen, usuario_id)
            almacen._backfill_vectorial = worker
        return worker


def iniciar_backfill(almacen, usuario_id=None, retardo=1.5):
    return obtener_backfill(almacen, usuario_id).iniciar(retardo)
