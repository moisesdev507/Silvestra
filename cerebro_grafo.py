"""Grafo de conocimiento vivo y relacional en SQLite para Lyris."""
import datetime
import os
import re
import sqlite3
import threading
import unicodedata

_bloqueo = threading.RLock()
RUTA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra_memoria.db")


def _obtener_conexion():
    con = sqlite3.connect(RUTA_DB, timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def inicializar_grafo():
    """Crea las tablas aditivas del grafo sin alterar tablas previas."""
    with _bloqueo:
        with _obtener_conexion() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS grafo_nodos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    tipo TEXT DEFAULT 'entidad',
                    creado_en TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS grafo_relaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sujeto TEXT NOT NULL,
                    relacion TEXT NOT NULL,
                    objeto TEXT NOT NULL,
                    confianza REAL DEFAULT 1.0,
                    activo INTEGER DEFAULT 1,
                    creado_en TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_grafo_suj ON grafo_relaciones(sujeto, activo)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_grafo_obj ON grafo_relaciones(objeto, activo)")
            con.commit()


def _normalizar(texto):
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def registrar_hecho(sujeto, relacion, objeto, confianza=1.0, tipo_sujeto="entidad", tipo_objeto="entidad"):
    """Registra o actualiza un hecho en el grafo, invalidando relaciones previas obsoletas."""
    if not sujeto or not relacion or not objeto:
        return False

    s = str(sujeto).strip()
    r = str(relacion).strip().replace(" ", "_").lower()
    o = str(objeto).strip()
    ahora = datetime.datetime.now().isoformat()

    inicializar_grafo()
    with _bloqueo:
        with _obtener_conexion() as con:
            # Asegurar nodos
            for nom, tipo in ((s, tipo_sujeto), (o, tipo_objeto)):
                con.execute("""
                    INSERT INTO grafo_nodos (nombre, tipo, creado_en, actualizado_en)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(nombre) DO UPDATE SET actualizado_en = excluded.actualizado_en
                """, (nom, tipo, ahora, ahora))

            # Desactivar relaciones previas con el mismo sujeto y relación para evitar contradicciones
            con.execute("""
                UPDATE grafo_relaciones
                SET activo = 0, actualizado_en = ?
                WHERE LOWER(sujeto) = LOWER(?) AND LOWER(relacion) = LOWER(?) AND activo = 1
            """, (ahora, s, r))

            # Insertar nueva relación activa
            con.execute("""
                INSERT INTO grafo_relaciones (sujeto, relacion, objeto, confianza, activo, creado_en, actualizado_en)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (s, r, o, float(confianza), ahora, ahora))
            con.commit()
    return True


def consultar_relaciones(entidad, limite=6):
    """Consulta todas las relaciones activas vinculadas a una entidad."""
    if not entidad:
        return []
    inicializar_grafo()
    e = str(entidad).strip().lower()
    with _bloqueo:
        with _obtener_conexion() as con:
            cur = con.execute("""
                SELECT sujeto, relacion, objeto, confianza, actualizado_en
                FROM grafo_relaciones
                WHERE activo = 1 AND (LOWER(sujeto) = ? OR LOWER(objeto) = ?)
                ORDER BY actualizado_en DESC LIMIT ?
            """, (e, e, limite))
            return [dict(row) for row in cur.fetchall()]


def consultar_contexto_grafo(consulta, limite=6):
    """Genera bloque textual compacto con los hechos más relevantes para inyectar al prompt."""
    if not consulta or not str(consulta).strip():
        return ""

    inicializar_grafo()
    texto_norm = _normalizar(consulta)
    palabras = [p for p in re.findall(r"[a-z0-9_]{3,}", texto_norm)]
    if not palabras:
        return ""

    hechos = []
    vistos = set()
    with _bloqueo:
        with _obtener_conexion() as con:
            # Buscar hechos activos que coincidan con las palabras clave de la consulta
            for p in palabras[:5]:
                cur = con.execute("""
                    SELECT sujeto, relacion, objeto, confianza
                    FROM grafo_relaciones
                    WHERE activo = 1 AND (
                        LOWER(sujeto) LIKE ? OR
                        LOWER(relacion) LIKE ? OR
                        LOWER(objeto) LIKE ?
                    )
                    ORDER BY actualizado_en DESC LIMIT ?
                """, (f"%{p}%", f"%{p}%", f"%{p}%", limite))
                for row in cur.fetchall():
                    clave = (row["sujeto"].lower(), row["relacion"].lower(), row["objeto"].lower())
                    if clave not in vistos:
                        vistos.add(clave)
                        hechos.append(f"- {row['sujeto']} {row['relacion']}: {row['objeto']}")
                        if len(hechos) >= limite:
                            break
                if len(hechos) >= limite:
                    break

    if not hechos:
        return ""

    return "[CONOCIMIENTO VIVO DEL GRAFO]\n" + "\n".join(hechos) + "\n"


def extraer_y_guardar_hechos(texto, creador="Moisés"):
    """Extrae hechos estructurados automáticamente desde conversaciones del dueño."""
    if not texto or len(str(texto).strip()) < 5:
        return 0

    t = str(texto).strip()
    guardados = 0

    # 1. Preferencias del usuario: "me gusta X", "prefiero X"
    m_gusta = re.search(r"\b(?:me\s+gusta|me\s+encanta)\s+(.+)", t, re.I)
    if m_gusta:
        obj = m_gusta.group(1).strip(" .!,;")
        if len(obj) >= 2:
            registrar_hecho(creador, "le_gusta", obj, 1.0, "persona", "preferencia")
            guardados += 1

    m_pref = re.search(r"\bprefiero\s+(.+)", t, re.I)
    if m_pref:
        obj = m_pref.group(1).strip(" .!,;")
        if len(obj) >= 2:
            registrar_hecho(creador, "prefiere", obj, 1.0, "persona", "preferencia")
            guardados += 1

    # 2. Ocupación o contexto: "trabajo en X", "estudio X"
    m_trabajo = re.search(r"\btrabajo\s+en\s+(.+)", t, re.I)
    if m_trabajo:
        obj = m_trabajo.group(1).strip(" .!,;")
        if len(obj) >= 2:
            registrar_hecho(creador, "trabaja_en", obj, 1.0, "persona", "ocupacion")
            guardados += 1

    # 3. Datos o reglas explícitas: "recuerda siempre que X es Y" o "mi X es Y"
    m_mi = re.search(r"\bmi\s+([a-zA-Záéíóúñ]+)\s+es\s+([^,.;]+)", t, re.I)
    if m_mi:
        rel = m_mi.group(1).strip().lower()
        obj = m_mi.group(2).strip(" .!,;")
        if len(obj) >= 2 and rel not in ("dia", "hora", "idea"):
            registrar_hecho(creador, rel, obj, 1.0, "persona", "dato")
            guardados += 1

    m_regla = re.search(r"\brecuerda\s+(?:siempre\s+)?que\s+([a-zA-Záéíóúñ0-9_\s]+)\s+es\s+(.+)", t, re.I)
    if m_regla:
        suj = m_regla.group(1).strip()
        obj = m_regla.group(2).strip(" .!,;")
        if len(suj) >= 2 and len(obj) >= 2:
            registrar_hecho(suj, "es", obj, 1.0, "entidad", "concepto")
            guardados += 1

    return guardados
