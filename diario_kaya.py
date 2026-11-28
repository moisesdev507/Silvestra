"""diario_kaya.py - Diario autobiográfico y memoria de identidad de Kaya en SQLite.

Permite a Kaya almacenar reflexiones personales en primera persona y consolidar
rasgos de identidad, gustos propios y opiniones que van evolucionando con el tiempo.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
import threading
from typing import Any, Generator, Optional

import rutas_app


def ruta_diario_defecto() -> str:
    """Ruta predeterminada en el directorio escribible datos/."""
    return rutas_app.ruta_usuario("datos", "diario_kaya.db")


class DiarioKaya:
    """Gestor SQLite thread-safe para reflexiones íntimas y rasgos de identidad."""

    def __init__(self, ruta_db: Optional[str] = None) -> None:
        self.ruta_db = ruta_db or ruta_diario_defecto()
        self._lock = threading.RLock()
        self._inicializar_esquema()

    @contextmanager
    def _sesion_db(self) -> Generator[sqlite3.Connection, None, None]:
        dir_padre = os.path.dirname(os.path.abspath(self.ruta_db))
        os.makedirs(dir_padre, exist_ok=True)
        conn = sqlite3.connect(self.ruta_db, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _inicializar_esquema(self) -> None:
        with self._lock, self._sesion_db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entradas_diario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_iso TEXT NOT NULL,
                    reflexion_primera_persona TEXT NOT NULL,
                    estado_animo TEXT NOT NULL,
                    tema_principal TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rasgos_identidad (
                    clave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                );
                """
            )

    def guardar_entrada(
        self,
        reflexion: str,
        estado_animo: str = "neutral",
        tema: str = "general",
    ) -> int:
        """Registra una nueva reflexión en primera persona en el diario íntimo."""
        texto = str(reflexion or "").strip()
        if not texto:
            return 0
        fecha = datetime.now().isoformat(timespec="seconds")
        animo = str(estado_animo or "neutral").strip()
        tema_txt = str(tema or "general").strip()

        with self._lock, self._sesion_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO entradas_diario (
                    fecha_iso, reflexion_primera_persona, estado_animo, tema_principal
                ) VALUES (?, ?, ?, ?);
                """,
                (fecha, texto, animo, tema_txt),
            )
            return int(cursor.lastrowid or 0)

    def obtener_recuerdos_recientes(self, limite: int = 5) -> list[dict[str, Any]]:
        """Obtiene las últimas reflexiones ordenadas de más reciente a más antigua."""
        lim = max(1, min(int(limite), 50))
        with self._lock, self._sesion_db() as conn:
            cursor = conn.execute(
                """
                SELECT id, fecha_iso, reflexion_primera_persona, estado_animo, tema_principal
                FROM entradas_diario
                ORDER BY id DESC
                LIMIT ?;
                """,
                (lim,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def actualizar_rasgo(self, clave: str, valor: str) -> None:
        """Registra o actualiza una opinión, gusto o rasgo subjetivo de Kaya."""
        c = str(clave or "").strip().lower()
        v = str(valor or "").strip()
        if not c or not v:
            return
        fecha = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._sesion_db() as conn:
            conn.execute(
                """
                INSERT INTO rasgos_identidad (clave, valor, actualizado_en)
                VALUES (?, ?, ?)
                ON CONFLICT(clave) DO UPDATE SET
                    valor = excluded.valor,
                    actualizado_en = excluded.actualizado_en;
                """,
                (c, v, fecha),
            )

    def obtener_rasgos(self) -> dict[str, str]:
        """Devuelve todos los rasgos y opiniones consolidadas de Kaya."""
        with self._lock, self._sesion_db() as conn:
            cursor = conn.execute("SELECT clave, valor FROM rasgos_identidad ORDER BY clave ASC;")
            return {row["clave"]: row["valor"] for row in cursor.fetchall()}

    def construir_bloque_memoria(self, limite_recuerdos: int = 4) -> str:
        """Genera un bloque de texto en primera persona listo para inyectar en prompts."""
        recuerdos = self.obtener_recuerdos_recientes(limite=limite_recuerdos)
        rasgos = self.obtener_rasgos()

        lineas = ["[SUBJETIVIDAD Y RECUERDOS PROPIOS]"]

        if recuerdos:
            lineas.append("Reflexiones recientes de mi diario:")
            for r in recuerdos:
                fecha_corta = r["fecha_iso"][:10]
                lineas.append(
                    f"- En {fecha_corta} sobre {r['tema_principal']}: \"{r['reflexion_primera_persona']}\" "
                    f"(ánimo: {r['estado_animo']})"
                )

        if rasgos:
            lineas.append("Rasgos y opiniones que he ido formando:")
            for k, val in rasgos.items():
                lineas.append(f"- {k}: {val}")

        if len(lineas) == 1:
            lineas.append("Estoy comenzando a formar mis propios recuerdos y perspectiva del mundo.")

        return "\n".join(lineas)


_diario_global: Optional[DiarioKaya] = None
_candado_modulo = threading.RLock()


def obtener_diario(ruta_db: Optional[str] = None) -> DiarioKaya:
    """Devuelve la instancia singleton de DiarioKaya o una personalizada si se pasa ruta."""
    global _diario_global
    with _candado_modulo:
        if ruta_db is not None:
            return DiarioKaya(ruta_db)
        if _diario_global is None:
            _diario_global = DiarioKaya()
        return _diario_global


def guardar_entrada(reflexion: str, estado_animo: str = "neutral", tema: str = "general") -> int:
    """Acceso rápido para registrar una reflexión en el diario."""
    return obtener_diario().guardar_entrada(reflexion, estado_animo, tema)


def obtener_recuerdos_recientes(limite: int = 5) -> list[dict[str, Any]]:
    """Acceso rápido para leer recuerdos recientes."""
    return obtener_diario().obtener_recuerdos_recientes(limite)


def actualizar_rasgo(clave: str, valor: str) -> None:
    """Acceso rápido para fijar un rasgo u opinión de identidad."""
    obtener_diario().actualizar_rasgo(clave, valor)


def construir_bloque_memoria() -> str:
    """Acceso rápido para generar el bloque de memoria subjetiva."""
    return obtener_diario().construir_bloque_memoria()
