"""Ciclo de sueño de Reposo Azul y seguimientos astutos de Kaya.

Todo se persiste en la DB canónica `silvestra_memoria.db` de la raíz. El sueño
se lanza en hilo daemon:
nunca toca Qt ni bloquea el hilo de audio. Solo produce intuiciones marcadas
como inferidas, nunca hechos confirmados.
"""
import os
import re
import sqlite3
import threading
import time
from contextlib import closing

import estado_emocional_kaya
from memoria_modelos import validar_usuario_id

RUTA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra_memoria.db")
COOLDOWN_SEG = 3 * 3600
CONFIANZA_INTUICION = 0.65
_bloqueo = threading.RLock()
_DDL_SUENO = ("CREATE TABLE IF NOT EXISTS kaya_sueno ("
              "usuario_id TEXT PRIMARY KEY, ultimo_sueno REAL NOT NULL)")
_DDL_SEGUIMIENTOS = ("CREATE TABLE IF NOT EXISTS kaya_seguimientos ("
                     "id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id TEXT NOT NULL, "
                     "tema TEXT NOT NULL, contexto TEXT, creado_en REAL NOT NULL, "
                     "due_en REAL NOT NULL, mostrado INTEGER NOT NULL DEFAULT 0, "
                     "estado TEXT NOT NULL DEFAULT 'vigente')")


def _ahora():
    """Marca temporal aislable en pruebas."""
    return time.time()


def _conectar():
    carpeta = os.path.dirname(os.path.abspath(RUTA_DB))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute(_DDL_SUENO)
    con.execute(_DDL_SEGUIMIENTOS)
    return con


def sueno_debido(usuario_id="local", ahora=None):
    """True si nunca durmió o pasaron al menos 3 horas."""
    uid = validar_usuario_id(usuario_id)
    instante = _ahora() if ahora is None else float(ahora)
    with _bloqueo, closing(_conectar()) as con:
        fila = con.execute("SELECT ultimo_sueno FROM kaya_sueno WHERE usuario_id=?",
                           (uid,)).fetchone()
    return fila is None or (instante - float(fila["ultimo_sueno"])) >= COOLDOWN_SEG


def solicitar_sueno(turnos=None, usuario_id="local"):
    """Marca el cooldown y lanza la consolidación en daemon; nunca bloquea."""
    uid = validar_usuario_id(usuario_id)
    instante = _ahora()
    with _bloqueo:
        if not sueno_debido(uid, instante):
            return False
        with closing(_conectar()) as con:
            con.execute(
                "INSERT INTO kaya_sueno VALUES(?,?) ON CONFLICT(usuario_id) "
                "DO UPDATE SET ultimo_sueno=excluded.ultimo_sueno", (uid, instante))
            con.commit()
    threading.Thread(target=consolidar, args=(list(turnos or []), uid),
                     daemon=True, name="kaya-sueno").start()
    return True


def _temas(turnos):
    """Extrae temas reales dichos por el usuario, sin ruido ni suposiciones."""
    try:
        from memoria_filtro import STOPWORDS, es_ruido_extraccion
    except Exception:
        STOPWORDS, es_ruido_extraccion = set(), lambda t: False
    descartar = STOPWORDS | {"estoy", "tengo", "quiero", "necesito", "soy",
                             "tiene", "hacer", "puede", "cuando", "tambien"}
    frecuencias = {}
    for mensaje in turnos or []:
        if mensaje.get("role") != "user":
            continue
        texto = str(mensaje.get("content") or "").strip()
        if not texto or es_ruido_extraccion(texto):
            continue
        for palabra in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}", texto.lower()):
            if palabra not in descartar:
                frecuencias[palabra] = frecuencias.get(palabra, 0) + 1
    temas = sorted(frecuencias.items(), key=lambda x: (-x[1], x[0]))[:2]
    if len(temas) > 1:
        repetidos = [t for t in temas if t[1] >= 2]
        temas = repetidos[:2] or temas[:1]
    return temas


def _fijar_confianza(mem, uid, intuicion):
    """La membrana evalúa; aquí solo se ajusta la confianza de la intuición."""
    try:
        import memoria_formacion
        clave = memoria_formacion.normalizar(intuicion)[:45]
        for fila in mem.almacen.listar_recuerdos(300, usuario_id=uid):
            if clave in memoria_formacion.normalizar(fila.get("contenido", "")):
                mem.almacen.actualizar_recuerdo(fila["id"], confianza=CONFIANZA_INTUICION)
                return True
    except Exception:
        pass
    return False


def consolidar(turnos=None, usuario_id="local"):
    """Convierte temas reales en 1-2 intuiciones inferidas y actualiza el ánimo."""
    uid = validar_usuario_id(usuario_id)
    guardadas = 0
    temas = _temas(turnos)
    try:
        import memoria
        mem = memoria.instancia_principal()
    except Exception:
        mem = None
    if temas and mem is not None and not getattr(mem, "bloqueo_invitado", False):
        for palabra, veces in temas:
            detalle = f" {veces} veces" if veces > 1 else ""
            intuicion = (f"[INTUICION] Tu usuario mencionó {palabra}{detalle}; "
                         "tema reciente para retomar.")
            try:
                if mem.recordar(intuicion, origen="inferido", fuente="extraccion",
                                canal="sueno"):
                    _fijar_confianza(mem, uid, intuicion)
                    guardadas += 1
            except Exception:
                continue
    estado_emocional_kaya.registrar_si_disponible("reposo_prolongado", uid)
    return guardadas


def al_dormir(turnos=None):
    """Reposo Azul: extrae hechos reales filtrados y lanza el sueño en daemon."""
    historial = []
    try:
        from memoria_filtro import es_ruido_extraccion
        historial = [m for m in (turnos or [])
                     if m.get("role") == "user"
                     and not es_ruido_extraccion(m.get("content", ""))]
    except Exception:
        pass
    if historial:
        try:
            import memoria
            mem = memoria.instancia_principal()
            if mem is not None and not getattr(mem, "bloqueo_invitado", False):
                threading.Thread(target=mem.extraer_hechos_conversacion,
                                 args=(historial,), daemon=True,
                                 name="kaya-extraccion-reposo").start()
        except Exception:
            pass
    return solicitar_sueno(turnos)


def agendar(tema, contexto="", horas_espera=24, usuario_id="local"):
    """Agenda un seguimiento vigente para un tema real del usuario."""
    uid = validar_usuario_id(usuario_id)
    asunto = " ".join(str(tema or "").split())[:120]
    if len(asunto) < 3:
        return False
    try:
        horas = float(horas_espera)
    except (TypeError, ValueError):
        horas = 24.0
    horas = max(1.0, min(720.0, horas))
    ahora = _ahora()
    with _bloqueo, closing(_conectar()) as con:
        con.execute(
            "INSERT INTO kaya_seguimientos(usuario_id,tema,contexto,creado_en,due_en) "
            "VALUES(?,?,?,?,?)",
            (uid, asunto, " ".join(str(contexto or "").split())[:160],
             ahora, ahora + horas * 3600))
        con.commit()
    return True


def seguimiento_para_prompt(usuario_id="local", ahora=None):
    """Devuelve y marca como mostrado 1 seguimiento vigente no visto aún."""
    uid = validar_usuario_id(usuario_id)
    instante = _ahora() if ahora is None else float(ahora)
    with _bloqueo, closing(_conectar()) as con:
        fila = con.execute(
            "SELECT id,tema FROM kaya_seguimientos WHERE usuario_id=? "
            "AND estado='vigente' AND mostrado=0 AND due_en<=? "
            "ORDER BY due_en LIMIT 1", (uid, instante)).fetchone()
        if fila is None:
            return ""
        con.execute("UPDATE kaya_seguimientos SET mostrado=1 WHERE id=?", (fila["id"],))
        con.commit()
    return "Seguimiento: " + " ".join(str(fila["tema"]).split())[:60]


__all__ = [
    "sueno_debido", "solicitar_sueno", "al_dormir", "consolidar", "agendar",
    "seguimiento_para_prompt", "RUTA_DB", "COOLDOWN_SEG", "CONFIANZA_INTUICION",
]
