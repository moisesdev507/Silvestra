"""Salud dinámica de proveedores LLM: EWMA de TTFT, fallos y persistencia ligera."""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time

ALFA_EWMA = 0.3
RUTA_DB_POR_DEFECTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "silvestra_salud.db"
)
CATEGORIAS = {"429", "404", "http", "timeout", "excepcion", "calidad", "vacia", "otro"}
_DDL = (
    "CREATE TABLE IF NOT EXISTS salud ("
    "clave TEXT PRIMARY KEY, proveedor TEXT NOT NULL, modelo TEXT, "
    "ewma_ttft REAL, muestras_ttft INTEGER, intentos INTEGER, errores INTEGER, "
    "errores_429 INTEGER, ultimo_fallo TEXT, ts_fallo REAL)"
)


def _sanitizar(texto):
    """Recorta motivos y elimina posibles credenciales antes de persistirlos."""
    s = str(texto or "")
    s = re.sub(r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTADO]", s)
    s = re.sub(r"\b(?:sk|coh|gsk|nvapi|grs)_[A-Za-z0-9_\-]{6,}", "[CLAVE REDACTADA]", s)
    return s[:160].strip()


class RegistroSalud:
    """Registro thread-safe de métricas por proveedor::modelo."""

    def __init__(self, ruta_db=None, alfa=ALFA_EWMA):
        self._bloqueo = threading.RLock()
        self._ruta = os.path.abspath(ruta_db or RUTA_DB_POR_DEFECTO)
        self._alfa = float(alfa)
        self._estado = {}
        self._cargar()

    @staticmethod
    def _clave(proveedor, modelo=None):
        return f"{proveedor}::{modelo or '*'}"

    def _cargar(self):
        if not os.path.exists(self._ruta):
            return
        try:
            con = sqlite3.connect(self._ruta, timeout=5.0)
            try:
                con.row_factory = sqlite3.Row
                con.execute(_DDL)
                filas = con.execute("SELECT * FROM salud").fetchall()
            finally:
                con.close()
            for fila in filas:
                datos = dict(fila)
                self._estado[datos["clave"]] = {
                    "proveedor": datos["proveedor"],
                    "modelo": datos["modelo"],
                    "ewma_ttft": datos["ewma_ttft"],
                    "muestras_ttft": int(datos["muestras_ttft"] or 0),
                    "intentos": int(datos["intentos"] or 0),
                    "errores": int(datos["errores"] or 0),
                    "errores_429": int(datos["errores_429"] or 0),
                    "ultimo_fallo": datos["ultimo_fallo"],
                    "ts_fallo": datos["ts_fallo"],
                }
        except Exception:
            self._estado = {}

    def _guardar(self, clave, datos):
        try:
            con = sqlite3.connect(self._ruta, timeout=5.0)
            try:
                con.execute(_DDL)
                con.execute(
                    "INSERT OR REPLACE INTO salud VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        clave, datos["proveedor"], datos["modelo"], datos["ewma_ttft"],
                        datos["muestras_ttft"], datos["intentos"], datos["errores"],
                        datos["errores_429"], datos["ultimo_fallo"], datos["ts_fallo"],
                    ),
                )
                con.commit()
            finally:
                con.close()
        except Exception:
            pass

    def _obtener_o_crear(self, proveedor, modelo):
        clave = self._clave(proveedor, modelo)
        datos = self._estado.get(clave)
        if datos is None:
            datos = {
                "proveedor": str(proveedor), "modelo": modelo, "ewma_ttft": None,
                "muestras_ttft": 0, "intentos": 0, "errores": 0, "errores_429": 0,
                "ultimo_fallo": None, "ts_fallo": None,
            }
            self._estado[clave] = datos
        return clave, datos

    def registrar_ttft(self, proveedor, modelo, ttft):
        try:
            valor = float(ttft)
        except (TypeError, ValueError):
            return
        if valor <= 0:
            return
        with self._bloqueo:
            clave, datos = self._obtener_o_crear(proveedor, modelo)
            if datos["muestras_ttft"] == 0:
                datos["ewma_ttft"] = valor
            else:
                datos["ewma_ttft"] = self._alfa * valor + (1.0 - self._alfa) * datos["ewma_ttft"]
            datos["muestras_ttft"] += 1
            self._guardar(clave, datos)

    def registrar_exito(self, proveedor, modelo):
        with self._bloqueo:
            clave, datos = self._obtener_o_crear(proveedor, modelo)
            datos["intentos"] += 1
            self._guardar(clave, datos)

    def registrar_fallo(self, proveedor, modelo, categoria="otro", motivo=""):
        cat = categoria if categoria in CATEGORIAS else "otro"
        with self._bloqueo:
            clave, datos = self._obtener_o_crear(proveedor, modelo)
            datos["intentos"] += 1
            datos["errores"] += 1
            if cat == "429":
                datos["errores_429"] += 1
            datos["ultimo_fallo"] = f"{cat}: {_sanitizar(motivo)}"[:180]
            datos["ts_fallo"] = time.time()
            self._guardar(clave, datos)

    def obtener_salud(self, proveedor, modelo=None):
        with self._bloqueo:
            datos = self._estado.get(self._clave(proveedor, modelo))
            if datos is None and modelo is not None:
                datos = self._estado.get(self._clave(proveedor))
            if datos is None:
                return {
                    "proveedor": proveedor, "modelo": modelo, "intentos": 0,
                    "errores": 0, "errores_429": 0, "ewma_ttft": None,
                    "muestras_ttft": 0, "tasa_error": 0.0, "tasa_429": 0.0,
                    "ultimo_fallo": None, "ts_fallo": None,
                }
            copia = dict(datos)
            base = max(1, int(datos["intentos"]))
            copia["tasa_error"] = int(datos["errores"]) / base
            copia["tasa_429"] = int(datos["errores_429"]) / base
            return copia


_registro = None
_registro_bloqueo = threading.RLock()


def _instancia():
    global _registro
    with _registro_bloqueo:
        if _registro is None:
            _registro = RegistroSalud()
        return _registro


def configurar(ruta_db=None, alfa=None):
    """Reemplaza el registro global (útil para BD temporales en pruebas)."""
    global _registro
    with _registro_bloqueo:
        _registro = RegistroSalud(ruta_db=ruta_db, alfa=alfa or ALFA_EWMA)
    return _registro


def registrar_ttft(proveedor, modelo, ttft):
    return _instancia().registrar_ttft(proveedor, modelo, ttft)


def registrar_exito(proveedor, modelo):
    return _instancia().registrar_exito(proveedor, modelo)


def registrar_fallo(proveedor, modelo, categoria="otro", motivo=""):
    return _instancia().registrar_fallo(proveedor, modelo, categoria, motivo)


def obtener_salud(proveedor, modelo=None):
    return _instancia().obtener_salud(proveedor, modelo)
