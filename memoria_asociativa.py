"""Memoria asociativa e hilos abiertos de conversación para Kaya (Fase 4B).

Permite recuperar recuerdos pasados por afinidad conceptual y mantener un
registro persistente de temas o proyectos pendientes de retomar.
"""
from __future__ import annotations

import contextlib
import datetime
import os
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any, Optional

STOPWORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por",
    "un", "para", "con", "no", "una", "su", "al", "lo", "como", "mas", "pero",
    "sus", "le", "ya", "o", "este", "si", "porque", "esta", "entre", "cuando",
    "muy", "sin", "sobre", "tambien", "me", "hasta", "hay", "donde", "quien",
    "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni", "contra",
    "otros", "ese", "eso", "ante", "ellos", "e", "esto", "mi", "antes", "algunos",
    "unos", "yo", "otro", "otras", "otra", "tanto", "esa", "estos", "mucho",
    "quienes", "nada", "muchos", "cual", "poco", "ella", "estar", "estas", "algo",
    "nosotros", "mis", "tu", "te", "ti", "hoy", "ayer", "bien", "hola",
}


def _normalizar_texto(texto: str) -> list[str]:
    """Limpia tildes, pasa a minúsculas y extrae palabras clave útiles (>= 3 chars)."""
    if not texto:
        return []
    s = unicodedata.normalize("NFKD", str(texto).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9_]{3,}", s)
    return [t for t in tokens if t not in STOPWORDS]


class MemoriaAsociativa:
    """Gestor thread-safe de asociaciones semánticas e hilos abiertos."""

    def __init__(self, ruta_db: Optional[str] = None):
        if not ruta_db:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
            try:
                os.makedirs(base, exist_ok=True)
            except Exception:
                pass
            ruta_db = os.path.join(base, "diario_kaya.db")
        self.ruta_db = ruta_db
        self._lock = threading.RLock()
        self._inicializar_tabla()

    @contextlib.contextmanager
    def _conectar(self):
        with self._lock:
            conn = sqlite3.connect(self.ruta_db, timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _inicializar_tabla(self):
        with self._conectar() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hilos_abiertos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tema TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    estado TEXT DEFAULT 'abierto',
                    creado_en TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hilos_estado ON hilos_abiertos (estado, actualizado_en DESC)"
            )

    def buscar_recuerdos_relacionados(self, texto_consulta: str, limite: int = 3) -> list[dict[str, Any]]:
        """Recupera recuerdos del diario cuya temática o reflexión coincide con la consulta."""
        tokens_q = set(_normalizar_texto(texto_consulta))
        if not tokens_q:
            return []

        candidatos = []
        try:
            with self._conectar() as conn:
                filas = conn.execute(
                    """
                    SELECT id, fecha_iso, tema_principal, estado_animo,
                           reflexion_primera_persona
                    FROM entradas_diario
                    ORDER BY id DESC LIMIT 60
                    """
                ).fetchall()
        except Exception:
            return []

        if not filas:
            return []

        max_id = max(int(f["id"]) for f in filas)
        for f in filas:
            t_tema = set(_normalizar_texto(f["tema_principal"] or ""))
            t_ref = set(_normalizar_texto(f["reflexion_primera_persona"] or ""))

            coincidencias_tema = len(tokens_q & t_tema)
            coincidencias_ref = len(tokens_q & t_ref)

            if not coincidencias_tema and not coincidencias_ref:
                continue

            score_coincidencia = (coincidencias_tema * 2.5) + (coincidencias_ref * 1.0)
            score_recencia = float(f["id"]) / float(max(1, max_id))
            score_total = (score_coincidencia * 0.75) + (score_recencia * 0.25)

            candidatos.append((
                score_total,
                {
                    "id": f["id"],
                    "fecha": f["fecha_iso"],
                    "tema": f["tema_principal"],
                    "reflexion": f["reflexion_primera_persona"],
                    "emocion": f["estado_animo"],
                }
            ))

        candidatos.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidatos[:limite]]

    def abrir_hilo(self, tema: str, detalle: str) -> int:
        """Registra o actualiza un hilo abierto evitando duplicados temáticos."""
        t_limpio = str(tema or "").strip()
        d_limpio = str(detalle or "").strip()
        if not t_limpio:
            return 0

        ahora_iso = datetime.datetime.now().isoformat()
        tokens_nuevo = set(_normalizar_texto(t_limpio))

        with self._conectar() as conn:
            filas = conn.execute(
                "SELECT id, tema FROM hilos_abiertos WHERE estado = 'abierto'"
            ).fetchall()
            for f in filas:
                tokens_exist = set(_normalizar_texto(f["tema"]))
                inter = tokens_nuevo & tokens_exist
                if (tokens_exist and len(inter) >= max(1, len(tokens_exist) - 1)) or f["tema"].lower() == t_limpio.lower():
                    conn.execute(
                        "UPDATE hilos_abiertos SET detalle = ?, actualizado_en = ? WHERE id = ?",
                        (d_limpio, ahora_iso, f["id"]),
                    )
                    return int(f["id"])

            cur = conn.execute(
                """
                INSERT INTO hilos_abiertos (tema, detalle, estado, creado_en, actualizado_en)
                VALUES (?, ?, 'abierto', ?, ?)
                """,
                (t_limpio, d_limpio, ahora_iso, ahora_iso),
            )
            return int(cur.lastrowid or 0)

    def cerrar_hilo(self, hilo_id: int) -> bool:
        """Cierra un hilo abierto por su identificador numérico."""
        ahora_iso = datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            cur = conn.execute(
                "UPDATE hilos_abiertos SET estado = 'cerrado', actualizado_en = ? WHERE id = ?",
                (ahora_iso, int(hilo_id)),
            )
            return cur.rowcount > 0

    def obtener_hilos_abiertos(self, limite: int = 4) -> list[dict[str, Any]]:
        """Devuelve los hilos abiertos más recientes."""
        with self._conectar() as conn:
            filas = conn.execute(
                """
                SELECT id, tema, detalle, creado_en, actualizado_en
                FROM hilos_abiertos
                WHERE estado = 'abierto'
                ORDER BY actualizado_en DESC LIMIT ?
                """,
                (max(1, int(limite)),),
            ).fetchall()
            return [dict(f) for f in filas]

    def construir_bloque_asociativo(
        self, contexto_actual: str = "", limite_recuerdos: int = 2, limite_hilos: int = 3
    ) -> str:
        """Genera un bloque compacto en primera persona con hilos y recuerdos afines."""
        partes = []
        hilos = self.obtener_hilos_abiertos(limite=limite_hilos)
        if hilos:
            lineas_h = []
            for h in hilos:
                lineas_h.append(f"- Sobre '{h['tema']}': {h['detalle']}")
            partes.append("[TEMAS E HILOS PENDIENTES QUE RECUERDO]\n" + "\n".join(lineas_h))

        if contexto_actual:
            recuerdos = self.buscar_recuerdos_relacionados(contexto_actual, limite=limite_recuerdos)
            if recuerdos:
                lineas_r = []
                for r in recuerdos:
                    lineas_r.append(f"- Sobre {r['tema']} ({r['fecha']}): \"{r['reflexion']}\"")
                partes.append("[RECUERDOS RELACIONADOS CON LO QUE VEO/HABLAMOS]\n" + "\n".join(lineas_r))

        return "\n\n".join(partes)


__all__ = ["MemoriaAsociativa"]
