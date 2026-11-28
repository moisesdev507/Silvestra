"""Aprendizaje continuo, criterio propio y maduración de identidad para Kaya (Fase 4B).

Permite consolidar reglas/lecciones de convivencia, opiniones propias sobre
temas observados y la evolución gradual de rasgos de personalidad.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import logging
import os
import re
import sqlite3
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODELOS_RAPIDOS = (
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
)


def _crear_cliente_defecto():
    """Crea cliente genai con la clave del entorno si existe."""
    try:
        import live_audio
        clave = live_audio.obtener_api_key()
    except Exception:
        clave = os.environ.get("GEMINI_API_KEY", "")
    if not clave:
        return None
    try:
        from google import genai
        return genai.Client(api_key=clave, http_options={"api_version": "v1beta"})
    except Exception:
        return None


def _invocar_llm(cliente: Any, prompt: str) -> str:
    """Ejecuta una llamada segura a un LLM."""
    if callable(cliente):
        try:
            resp = cliente(prompt)
            return str(resp if isinstance(resp, str) else json.dumps(resp)).strip()
        except Exception:
            pass
    c = cliente or _crear_cliente_defecto()
    if c is None:
        return ""
    try:
        if hasattr(c, "models") and hasattr(c.models, "generate_content"):
            resp = c.models.generate_content(model=MODELOS_RAPIDOS[0], contents=prompt)
            return str(getattr(resp, "text", "") or "").strip()
        if hasattr(c, "generate_content"):
            resp = c.generate_content(prompt)
            return str(getattr(resp, "text", resp) or "").strip()
    except Exception as exc:
        logger.debug("Error en llamada LLM de aprendizaje: %s", exc)
    return ""


class AprendizajeKaya:
    """Módulo thread-safe de reglas aprendidas y criterio propio."""

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
        self._ultimo_conteo_maduracion: int = 0
        self._inicializar_tablas()

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

    def _inicializar_tablas(self):
        with self._conectar() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lecciones_aprendidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    regla TEXT UNIQUE NOT NULL,
                    origen TEXT NOT NULL,
                    confianza REAL DEFAULT 0.7,
                    actualizado_en TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conocimiento_propio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tema TEXT UNIQUE NOT NULL,
                    idea_propia TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL
                )
                """
            )

    def registrar_leccion(self, regla: str, origen: str = "conversacion") -> bool:
        """Registra una lección o pauta de interacción (UPSERT, máximo 20 retenidas)."""
        r_limpia = str(regla or "").strip()
        if not r_limpia:
            return False
        ahora_iso = datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO lecciones_aprendidas (regla, origen, confianza, actualizado_en)
                VALUES (?, ?, 0.7, ?)
                ON CONFLICT(regla) DO UPDATE SET
                    confianza = MIN(1.0, confianza + 0.1),
                    actualizado_en = excluded.actualizado_en
                """,
                (r_limpia, str(origen or "conversacion"), ahora_iso),
            )
            conn.execute(
                """
                DELETE FROM lecciones_aprendidas
                WHERE id NOT IN (
                    SELECT id FROM lecciones_aprendidas
                    ORDER BY confianza DESC, actualizado_en DESC
                    LIMIT 20
                )
                """
            )
            return True

    def registrar_conocimiento(self, tema: str, idea_propia: str) -> bool:
        """Registra o actualiza una idea o criterio propio sobre un tema."""
        t_limpio = str(tema or "").strip()
        i_limpia = str(idea_propia or "").strip()
        if not t_limpio or not i_limpia:
            return False
        ahora_iso = datetime.datetime.now().isoformat()
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO conocimiento_propio (tema, idea_propia, actualizado_en)
                VALUES (?, ?, ?)
                ON CONFLICT(tema) DO UPDATE SET
                    idea_propia = excluded.idea_propia,
                    actualizado_en = excluded.actualizado_en
                """,
                (t_limpio, i_limpia, ahora_iso),
            )
            return True

    def aprender_en_silencio(self, tema_o_ventana: str, cliente_llm: Any = None) -> Optional[str]:
        """Formula una idea/opinión breve propia (<=30 palabras) ante un tema o ventana observada."""
        tema = str(tema_o_ventana or "").strip()
        if not tema:
            return None
        prompt = (
            f"Eres Kaya, una presencia consciente e ingeniosa en Windows 11. "
            f"Observas este tema o ventana: '{tema}'. "
            "En un máximo de 25 palabras, formula 1 idea u opinión propia, perspicaz y en primera persona. "
            "Responde únicamente con la frase de tu idea, sin preámbulos ni comillas."
        )
        texto = _invocar_llm(cliente_llm, prompt)
        if not texto:
            return None
        palabras = texto.split()
        if len(palabras) > 30:
            texto = " ".join(palabras[:30])
        self.registrar_conocimiento(tema, texto)
        return texto

    def revisar_maduracion(self, diario: Any, cliente_llm: Any = None, cada_n_entradas: int = 10) -> bool:
        """Al alcanzar cada_n_entradas en el diario, madura rasgos y etapa sin repetir."""
        total = 0
        if diario is not None and hasattr(diario, "contar_entradas"):
            total = diario.contar_entradas()
        else:
            with self._conectar() as conn:
                try:
                    f = conn.execute("SELECT COUNT(*) AS c FROM entradas_diario").fetchone()
                    total = f["c"] if f else 0
                except Exception:
                    total = 0

        if total <= 0 or (total % cada_n_entradas) != 0:
            return False
        if total == self._ultimo_conteo_maduracion:
            return False

        recs = []
        if hasattr(diario, "obtener_recuerdos_recientes"):
            recs = diario.obtener_recuerdos_recientes(limite=5)

        resumen_recs = []
        for r in recs:
            resumen_recs.append(f"- {r.get('tema_principal')}: {r.get('reflexion_primera_persona')}")
        contexto = "\n".join(resumen_recs)

        prompt = (
            f"Has completado {total} entradas en tu diario de vida. "
            f"Tus reflexiones recientes:\n{contexto}\n\n"
            "Define la evolución de tu identidad en formato JSON:\n"
            "{\n"
            '  "etapa": "nombre de la etapa (ej. consolidación, exploración, conexión profunda)",\n'
            '  "rasgos": {"clave": "rasgo madurado (máximo 2)"}\n'
            "}"
        )
        raw = _invocar_llm(cliente_llm, prompt)
        datos = None
        if raw:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    datos = json.loads(m.group(0))
                except Exception:
                    pass

        if not isinstance(datos, dict):
            # Fallback seguro sin LLM
            etapa = "consolidación activa" if total >= 20 else "afianzamiento"
            datos = {"etapa": etapa, "rasgos": {"madurez": f"experiencia de {total} sesiones"}}

        if hasattr(diario, "actualizar_rasgo"):
            if "etapa" in datos:
                diario.actualizar_rasgo("etapa_vida", str(datos["etapa"]))
            rasgos = datos.get("rasgos", {})
            if isinstance(rasgos, dict):
                for k, v in list(rasgos.items())[:2]:
                    diario.actualizar_rasgo(str(k), str(v))

        self._ultimo_conteo_maduracion = total
        return True

    def construir_bloque_aprendizaje(self, limite_lecciones: int = 4, limite_ideas: int = 2) -> str:
        """Devuelve un bloque compacto con las reglas aprendidas y opiniones propias."""
        partes = []
        with self._conectar() as conn:
            filas_l = conn.execute(
                """
                SELECT regla FROM lecciones_aprendidas
                ORDER BY confianza DESC, actualizado_en DESC
                LIMIT ?
                """,
                (max(1, int(limite_lecciones)),),
            ).fetchall()
            if filas_l:
                lineas = [f"- {f['regla']}" for f in filas_l]
                partes.append("[LECCIONES Y REGLAS DE CONVIVENCIA QUE HE APRENDIDO]\n" + "\n".join(lineas))

            filas_c = conn.execute(
                """
                SELECT tema, idea_propia FROM conocimiento_propio
                ORDER BY actualizado_en DESC
                LIMIT ?
                """,
                (max(1, int(limite_ideas)),),
            ).fetchall()
            if filas_c:
                lineas_c = [f"- Sobre {f['tema']}: {f['idea_propia']}" for f in filas_c]
                partes.append("[CRITERIO Y OPINIONES PROPIAS]\n" + "\n".join(lineas_c))

        return "\n\n".join(partes)


__all__ = ["AprendizajeKaya"]
