"""Motor de Sueño Cognitivo y Consolidación de Memoria para Lyris // Silvestra.

Inspecciona recuerdos históricos en SQLite, fusiona duplicados conservando el registro
más completo y reciente, y sintetiza resúmenes temáticos aditivos para mantener
la memoria a largo plazo ágil y sin inflar el consumo de tokens.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Tuple

from memoria_consolidacion_validacion import es_duplicado

_bloqueo = threading.RLock()
_PATRON_SUENO = re.compile(
    r"\b(?:consolida(?:r)?\s+(?:tu\s+)?memoria|limpieza\s+de\s+memoria|sue[ñn]o\s+cognitivo|optimiza(?:r)?\s+(?:la\s+|tu\s+)?memoria)\b",
    re.IGNORECASE,
)

_TEMAS_MAPA = {
    "programacion": re.compile(r"\b(?:python|codigo|pyside|qt|fastapi|sql|sqlite|funcion|modulo|clase|ast|git|error|bug|test|prueba|refactor)\b", re.I),
    "uniconnect_estudio": re.compile(r"\b(?:uniconnect|universidad|carrera|estudio|estudiar|examen|semestre|linguistica|gramatica|clase)\b", re.I),
    "web_desarrollo": re.compile(r"\b(?:html|css|javascript|js|tailwind|pwa|hud|tablet|web|navegador|sse|http|endpoint|api)\b", re.I),
    "preferencias_personales": re.compile(r"\b(?:dueno|moises|musica|descanso|rutina|nombre|asistente|lyris|preferencia|noche)\b", re.I),
}


def inicializar_tablas_sueno(db_path: str = "silvestra_memoria.db") -> bool:
    """Crea la tabla aditiva memoria_resumenes si no existe."""
    if not os.path.exists(db_path) and ":memory:" not in db_path:
        return False
    with _bloqueo:
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memoria_resumenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    periodo TEXT,
                    tema TEXT,
                    sintesis TEXT,
                    creado_ts REAL
                )
            """)
            con.commit()
            con.close()
            return True
        except Exception as e:
            print(f"[memoria_sueno] Error inicializando tablas: {e}", flush=True)
            return False


def ejecutar_sueno_cognitivo(db_path: str = "silvestra_memoria.db", limite_lote: int = 40) -> Dict[str, Any]:
    """Inspecciona recuerdos activos, deduplica con el criterio compartido y sintetiza temas."""
    inicializar_tablas_sueno(db_path)
    res: Dict[str, Any] = {"ok": False, "duplicados_consolidados": 0, "resumenes_generados": 0, "detalles": []}

    with _bloqueo:
        con = None
        try:
            con = sqlite3.connect(db_path, timeout=5.0)
            cur = con.cursor()

            # 1. Comprobar columnas reales de recuerdos con PRAGMA
            columnas_info = cur.execute("PRAGMA table_info(recuerdos)").fetchall()
            col_nombres = {c[1] for c in columnas_info}
            if "id" not in col_nombres or "contenido" not in col_nombres:
                con.close()
                return res

            tiene_estado = "estado" in col_nombres
            tiene_reemplazo = "reemplaza_a_id" in col_nombres

            # 2. Cargar lote de recuerdos para auditar
            sql = "SELECT id, contenido, categoria, creado_en FROM recuerdos"
            if tiene_estado:
                sql += " WHERE estado = 'activo' OR estado IS NULL"
            sql += f" ORDER BY id DESC LIMIT {int(limite_lote)}"

            filas = cur.execute(sql).fetchall()
            if not filas:
                con.close()
                res["ok"] = True
                return res

            # 3. Detectar redundancias / duplicados
            items = []
            for fid, cont, cat, creado in filas:
                items.append({
                    "id": fid,
                    "contenido": cont or "",
                    "categoria": cat or "general",
                    "creado": creado,
                })

            duplicados_ids: List[Tuple[int, int]] = []
            ya_marcados: set[int] = set()

            for i in range(len(items)):
                id_a = items[i]["id"]
                if id_a in ya_marcados:
                    continue
                for j in range(i + 1, len(items)):
                    id_b = items[j]["id"]
                    if id_b in ya_marcados:
                        continue
                    if es_duplicado(items[i]["contenido"], items[j]["contenido"]):
                        # id_a es más reciente (ORDER BY id DESC). Si id_a tiene igual o mayor longitud, gana a.
                        len_a, len_b = len(items[i]["contenido"]), len(items[j]["contenido"])
                        ganador, perdedor = (id_a, id_b) if len_a >= len_b else (id_b, id_a)
                        duplicados_ids.append((perdedor, ganador))
                        ya_marcados.add(perdedor)

            # 4. Actualizar estado de duplicados en la base
            for perdedor, ganador in duplicados_ids:
                if tiene_estado and tiene_reemplazo:
                    cur.execute(
                        "UPDATE recuerdos SET estado = 'consolidado', reemplaza_a_id = ? WHERE id = ?",
                        (ganador, perdedor),
                    )
                elif tiene_estado:
                    cur.execute("UPDATE recuerdos SET estado = 'consolidado' WHERE id = ?", (perdedor,))
            res["duplicados_consolidados"] = len(duplicados_ids)

            # 5. Agrupación temática de recuerdos conservados
            temas_agrupados: Dict[str, List[str]] = {k: [] for k in _TEMAS_MAPA}
            for it in items:
                if it["id"] in ya_marcados:
                    continue
                c_txt = it["contenido"]
                clasificado = False
                for tema, patron in _TEMAS_MAPA.items():
                    if patron.search(c_txt):
                        temas_agrupados[tema].append(c_txt)
                        clasificado = True
                        break
                if not clasificado:
                    temas_agrupados["preferencias_personales"].append(c_txt)

            # 6. Generar e insertar síntesis compactas
            ahora_ts = time.time()
            periodo_str = time.strftime("%Y-%m-%d")
            resumenes_creados = 0

            for tema, textos in temas_agrupados.items():
                if len(textos) >= 2:
                    ejemplos = [t.strip() for t in textos[:3]]
                    sintesis = (
                        f"Consolidación de {tema.replace('_', ' ')} ({len(textos)} puntos activos). "
                        f"Aspectos clave: {' | '.join(ejemplos)}"
                    )
                    if len(sintesis) > 300:
                        sintesis = sintesis[:297] + "..."

                    # Evitar duplicar síntesis idéntica en el mismo día
                    existe = cur.execute(
                        "SELECT id FROM memoria_resumenes WHERE periodo = ? AND tema = ? LIMIT 1",
                        (periodo_str, tema),
                    ).fetchone()
                    if existe:
                        cur.execute(
                            "UPDATE memoria_resumenes SET sintesis = ?, creado_ts = ? WHERE id = ?",
                            (sintesis, ahora_ts, existe[0]),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO memoria_resumenes (periodo, tema, sintesis, creado_ts) VALUES (?, ?, ?, ?)",
                            (periodo_str, tema, sintesis, ahora_ts),
                        )
                    resumenes_creados += 1
                    res["detalles"].append(f"{tema}: {len(textos)} recuerdos")

            res["resumenes_generados"] = resumenes_creados
            con.commit()
            con.close()
            res["ok"] = True
            return res
        except Exception as e:
            if con:
                try:
                    con.close()
                except Exception:
                    pass
            print(f"[memoria_sueno] Error en ejecución de sueño: {e}", flush=True)
            res["error"] = str(e)
            return res


def detectar_orden_sueno(texto: str) -> bool:
    """Detecta si el usuario solicita explícitamente consolidar o limpiar memoria."""
    if not texto:
        return False
    return bool(_PATRON_SUENO.search(texto.strip()))


def ejecutar_orden_sueno(texto: str, app: Any = None, db_path: str = "silvestra_memoria.db") -> str:
    """Ejecuta la consolidación y devuelve una respuesta amigable para el usuario."""
    r = ejecutar_sueno_cognitivo(db_path=db_path)
    if not r.get("ok"):
        return "Intenté consolidar la memoria pero ocurrió una excepción interna. Todo sigue respaldado de forma segura."
    dups = r.get("duplicados_consolidados", 0)
    resums = r.get("resumenes_generados", 0)
    detalles = ", ".join(r.get("detalles", [])) or "estructura limpia"
    return (
        f"Sueño cognitivo completado. He consolidado {dups} recuerdos redundantes y sintetizado "
        f"{resums} resúmenes temáticos ({detalles}). Tu memoria a largo plazo está optimizada."
    )
