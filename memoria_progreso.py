"""Mapa de Evolución y Progreso Técnico del Dueño para Lyris // Silvestra.

Rastrea tecnologías, patrones arquitectónicos y conceptos dominados en SQLite,
calibra el nivel socrático en cerebro_mentor y responde a consultas sobre
el crecimiento profesional y técnico de Moisés.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

_bloqueo = threading.RLock()
_PATRON_PROGRESO = re.compile(
    r"\b(?:qu[eé]\s+he\s+aprendido|c[oó]mo\s+voy\s+mejorando|mi\s+progreso(?:\s+como\s+programador)?|mi\s+nivel(?:\s+t[eé]cnico)?|qu[eé]\s+tecnolog[ií]as\s+domino)\b",
    re.IGNORECASE,
)


def inicializar_tablas_progreso(db_path: str = "silvestra_memoria.db") -> bool:
    """Crea las tablas aditivas de habilidades e hitos si no existen."""
    if not os.path.exists(db_path) and ":memory:" not in db_path:
        return False
    with _bloqueo:
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS habilidades_dueno (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tecnologia TEXT UNIQUE,
                    categoria TEXT,
                    nivel TEXT,
                    evidencia TEXT,
                    actualizado_ts REAL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hitos_tecnicos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tecnologia TEXT,
                    concepto TEXT,
                    nivel_evidencia TEXT,
                    creado_ts REAL,
                    detalles TEXT
                )
            """)
            con.commit()
            con.close()
            return True
        except Exception as e:
            print(f"[memoria_progreso] Error inicializando tablas: {e}", flush=True)
            return False


def _calibrar_nivel(conteo_hitos: int) -> str:
    if conteo_hitos >= 8:
        return "avanzado"
    if conteo_hitos >= 3:
        return "intermedio"
    return "iniciación"


def registrar_avance_tecnico(
    tecnologia: str,
    concepto: str,
    nivel_evidencia: str = "practicado",
    db_path: str = "silvestra_memoria.db",
    detalles: str = "",
) -> bool:
    """Registra un hito y actualiza el nivel de la tecnología en la base."""
    if not tecnologia or not concepto:
        return False
    inicializar_tablas_progreso(db_path)

    tec_norm = tecnologia.strip().capitalize()
    con_norm = concepto.strip()
    ahora_ts = time.time()

    with _bloqueo:
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()

            # Insertar hito
            cur.execute(
                "INSERT INTO hitos_tecnicos (tecnologia, concepto, nivel_evidencia, creado_ts, detalles) VALUES (?, ?, ?, ?, ?)",
                (tec_norm, con_norm, nivel_evidencia, ahora_ts, detalles or con_norm),
            )

            # Contar hitos para esta tecnología
            cur.execute("SELECT COUNT(*) FROM hitos_tecnicos WHERE tecnologia = ?", (tec_norm,))
            total_hitos = cur.fetchone()[0]
            nivel = _calibrar_nivel(total_hitos)

            cat = "lenguaje" if tec_norm in ("Python", "Java", "Javascript", "Typescript", "Sql") else "framework_o_herramienta"

            cur.execute("""
                INSERT INTO habilidades_dueno (tecnologia, categoria, nivel, evidencia, actualizado_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tecnologia) DO UPDATE SET
                    nivel = excluded.nivel,
                    evidencia = excluded.evidencia,
                    actualizado_ts = excluded.actualizado_ts
            """, (tec_norm, cat, nivel, f"{total_hitos} hitos registrados ({con_norm})", ahora_ts))

            con.commit()
            con.close()
            return True
        except Exception as e:
            print(f"[memoria_progreso] Error registrando avance: {e}", flush=True)
            return False


def resumen_nivel_programador(db_path: str = "silvestra_memoria.db") -> str:
    """Genera una síntesis compacta (<= 160 caracteres) para inyectar en cerebro_mentor."""
    inicializar_tablas_progreso(db_path)
    with _bloqueo:
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()
            cur.execute("SELECT tecnologia, nivel FROM habilidades_dueno ORDER BY actualizado_ts DESC LIMIT 4")
            filas = cur.execute("SELECT tecnologia, nivel FROM habilidades_dueno ORDER BY actualizado_ts DESC LIMIT 4").fetchall()
            con.close()

            if not filas:
                return "Moisés: nivel intermedio en Python/PySide6 con enfoque en arquitectura modular y clean code."

            resumen_partes = [f"{t} ({n})" for t, n in filas]
            res = f"Moisés domina: {', '.join(resumen_partes)}. Nivel socrático: desafiante y práctico."
            if len(res) > 160:
                res = res[:157] + "..."
            return res
        except Exception:
            return "Moisés: nivel intermedio-avanzado en desarrollo modular en Python."


def consultar_mi_progreso(db_path: str = "silvestra_memoria.db") -> str:
    """Genera un reporte motivador y exhaustivo sobre el avance del dueño."""
    inicializar_tablas_progreso(db_path)
    with _bloqueo:
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()
            habs = cur.execute("SELECT tecnologia, nivel, evidencia FROM habilidades_dueno ORDER BY actualizado_ts DESC").fetchall()
            hitos = cur.execute("SELECT tecnologia, concepto, creado_ts FROM hitos_tecnicos ORDER BY id DESC LIMIT 5").fetchall()
            con.close()

            if not habs and not hitos:
                return (
                    "Aún estamos comenzando a registrar tus hitos técnicos en esta base. "
                    "Has construido Silvestra con PySide6, FastAPI, SQLite FTS5 y modelos multimodales, "
                    "lo que demuestra una sólida base de arquitectura limpia. ¡Sigamos practicando!"
                )

            lineas = ["Has crecido notablemente como programador. Tu mapa de habilidades actual es:"]
            for tec, niv, evi in habs[:5]:
                lineas.append(f"• **{tec}** ({niv}): {evi}")

            if hitos:
                lineas.append("\nÚltimos hitos técnicos registrados:")
                for tec, conc, ts in hitos[:3]:
                    f_str = time.strftime("%d/%m", time.localtime(ts)) if ts else "reciente"
                    lineas.append(f"- [{f_str}] {tec}: {conc}")

            lineas.append("\nTu criterio arquitectónico y resolución socrática están en un nivel sobresaliente.")
            return "\n".join(lineas)
        except Exception as e:
            return f"Hubo un detalle consultando tu progreso: {e}. Pero tus avances siguen firmes en la memoria."


def detectar_orden_progreso(texto: str) -> bool:
    """Detecta si el usuario está preguntando por su crecimiento técnico."""
    if not texto:
        return False
    return bool(_PATRON_PROGRESO.search(texto.strip()))
