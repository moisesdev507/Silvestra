"""Memoria Asociativa Profunda para Lyris // Silvestra.

Cruza en una sola llamada compacta (<= 600 caracteres) recuerdos activos,
síntesis temáticas de sueño cognitivo, relaciones del Grafo de Conocimiento
y fragmentos indexados del RAG de proyectos sin inflar los tokens del prompt.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from typing import Any, List

_bloqueo = threading.RLock()


def _extraer_palabras_clave(texto: str) -> List[str]:
    palabras = re.findall(r"[a-záéíóúüñ0-9]{3,}", (texto or "").lower())
    ignorar = {"para", "como", "este", "esta", "sobre", "entre", "tiene", "hace", "donde", "cual", "quien"}
    return [p for p in palabras if p not in ignorar][:4]


def buscar_contexto_asociativo(
    consulta: str,
    limite: int = 3,
    db_path: str = "silvestra_memoria.db",
) -> str:
    """Retorna un bloque asociativo unificado (<= 600 caracteres) cruzando múltiples fuentes."""
    if not consulta or len(consulta.strip()) < 3:
        return ""

    secciones: List[str] = []
    palabras = _extraer_palabras_clave(consulta)

    # 1. Consultar síntesis temáticas en memoria_resumenes
    resumen_txt = ""
    if os.path.exists(db_path) or ":memory:" in db_path:
        with _bloqueo:
            try:
                con = sqlite3.connect(db_path, timeout=3.0)
                cur = con.cursor()
                tablas = {t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "memoria_resumenes" in tablas:
                    clauses = " OR ".join(["sintesis LIKE ?"] * len(palabras)) if palabras else "1=1"
                    params = [f"%{p}%" for p in palabras] if palabras else []
                    sql = f"SELECT tema, sintesis FROM memoria_resumenes WHERE {clauses} ORDER BY id DESC LIMIT 1"
                    fila = cur.execute(sql, params).fetchone()
                    if fila:
                        resumen_txt = f"{fila[0]}: {fila[1]}"
                con.close()
            except Exception:
                pass

    if resumen_txt:
        if len(resumen_txt) > 160:
            resumen_txt = resumen_txt[:157] + "..."
        secciones.append(f"Síntesis: {resumen_txt}")

    # 2. Consultar Grafo de Conocimiento (cerebro_grafo)
    try:
        import cerebro_grafo
        grafo_ctx = cerebro_grafo.consultar_contexto_grafo(consulta, limite=2)
        if grafo_ctx:
            clean_g = grafo_ctx.replace("\n", " | ").strip()
            if len(clean_g) > 180:
                clean_g = clean_g[:177] + "..."
            secciones.append(f"Grafo: {clean_g}")
    except Exception:
        pass

    # 3. Consultar RAG de Proyectos (cerebro_rag)
    try:
        import cerebro_rag
        rag_ctx = cerebro_rag.consultar_rag(consulta, limite=1)
        if rag_ctx:
            # Extraer solo el contenido esencial del chunk
            lineas_rag = [l.strip() for l in rag_ctx.splitlines() if l.strip() and not l.startswith("[RAG") and not l.startswith("Archivo:")]
            txt_rag = " ".join(lineas_rag)
            if len(txt_rag) > 160:
                txt_rag = txt_rag[:157] + "..."
            if txt_rag:
                secciones.append(f"Proyecto: {txt_rag}")
    except Exception:
        pass

    if not secciones:
        return ""

    resultado = "[MEMORIA ASOCIATIVA PROFUNDA]\n" + "\n".join(f"• {s}" for s in secciones)
    if len(resultado) > 600:
        resultado = resultado[:597] + "..."
    return resultado
