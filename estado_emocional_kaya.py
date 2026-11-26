"""Motor emocional persistente de Kaya, compartido por Live y voz clásica.

Guarda cuatro niveles en [0,1] en `datos/silvestra_memoria.db`, tabla
`kaya_estado_emocional`, una fila por usuario. Ninguna inferencia: los valores
cambian solo ante eventos reales del ciclo de vida de la llamada.
"""
import os
import sqlite3
import threading
import time
from contextlib import closing

import rutas_app
from memoria_modelos import validar_usuario_id

RUTA_DB = os.path.join(rutas_app.dir_usuario(), "datos", "silvestra_memoria.db")
_BLOQUEO = threading.RLock()
UMBRAL_ABANDONO_SEG = 2 * 3600

DEFAULTS = {
    "energia": 0.75,
    "curiosidad": 0.65,
    "complicidad": 0.50,
    "fastidio": 0.10,
    "ultima_interaccion_ts": 0.0,
    "interrupciones_seguidas": 0,
}
_COLUMNAS = tuple(DEFAULTS)


def _ahora():
    """Marca temporal monolítica aislable en pruebas."""
    return time.time()


def _limitar(valor):
    return max(0.0, min(1.0, float(valor)))


def _conectar():
    carpeta = os.path.dirname(os.path.abspath(RUTA_DB))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, timeout=5.0)
    con.execute(
        "CREATE TABLE IF NOT EXISTS kaya_estado_emocional ("
        "usuario_id TEXT PRIMARY KEY, energia REAL NOT NULL, curiosidad REAL NOT NULL, "
        "complicidad REAL NOT NULL, fastidio REAL NOT NULL, "
        "ultima_interaccion_ts REAL NOT NULL, interrupciones_seguidas INTEGER NOT NULL)"
    )
    return con


def obtener_estado(usuario_id="local"):
    """Devuelve la fila real (o la inicializa) sin alterar ningún nivel."""
    uid = validar_usuario_id(usuario_id)
    with _BLOQUEO, closing(_conectar()) as con:
        fila = con.execute(
            "SELECT " + ",".join(_COLUMNAS) +
            " FROM kaya_estado_emocional WHERE usuario_id=?", (uid,)
        ).fetchone()
        if fila is None:
            con.execute(
                "INSERT INTO kaya_estado_emocional (" +
                ",".join(("usuario_id",) + _COLUMNAS) + ") VALUES (" +
                ",".join("?" for _ in range(len(_COLUMNAS) + 1)) + ")",
                (uid,) + tuple(DEFAULTS[c] for c in _COLUMNAS),
            )
            con.commit()
            return dict(DEFAULTS)
        return dict(zip(_COLUMNAS, fila))


def _guardar(uid, estado):
    with closing(_conectar()) as con:
        con.execute(
            "INSERT INTO kaya_estado_emocional (" +
            ",".join(("usuario_id",) + _COLUMNAS) + ") VALUES (" +
            ",".join("?" for _ in range(len(_COLUMNAS) + 1)) + ") "
            "ON CONFLICT(usuario_id) DO UPDATE SET " +
            ",".join(f"{c}=excluded.{c}" for c in _COLUMNAS),
            (uid,) + tuple(estado[c] for c in _COLUMNAS),
        )
        con.commit()


def registrar_evento_emocional(tipo, usuario_id="local"):
    """Actualiza los niveles ante un evento real y devuelve el estado resultante."""
    uid = validar_usuario_id(usuario_id)
    ahora = _ahora()
    with _BLOQUEO:
        estado = obtener_estado(uid)
        ultimo = float(estado.get("ultima_interaccion_ts") or 0.0)
        if tipo == "despertar_tras_abandono":
            if ((not ultimo or (ahora - ultimo) > UMBRAL_ABANDONO_SEG)
                    and float(estado["curiosidad"]) < 0.75):
                estado["curiosidad"] = _limitar(estado["curiosidad"] + 0.18)
                # Toque de reclamo amistoso, nunca enfado real.
                estado["fastidio"] = min(0.25, _limitar(estado["fastidio"] + 0.05))
        elif tipo == "charla_fluida":
            estado["complicidad"] = _limitar(estado["complicidad"] + 0.10)
            estado["energia"] = _limitar(estado["energia"] + 0.08)
            estado["fastidio"] = _limitar(estado["fastidio"] - 0.12)
            # La charla satisface la curiosidad y permite un próximo abandono.
            estado["curiosidad"] = max(0.65, _limitar(estado["curiosidad"] - 0.18))
            estado["interrupciones_seguidas"] = 0
        elif tipo == "interrupcion_barge_in":
            estado["interrupciones_seguidas"] = int(estado["interrupciones_seguidas"]) + 1
            if estado["interrupciones_seguidas"] >= 3:
                estado["fastidio"] = min(0.75, _limitar(estado["fastidio"] + 0.10))
                estado["energia"] = _limitar(estado["energia"] - 0.08)
        elif tipo == "reposo_prolongado":
            estado["fastidio"] = _limitar(0.10 + (float(estado["fastidio"]) - 0.10) * 0.5)
            estado["energia"] = _limitar(estado["energia"] + 0.10)
            estado["interrupciones_seguidas"] = 0
        else:
            return estado
        # Despertar y reposo no son interacciones: conservan la marca previa
        # para que la directriz de "curiosa tras horas" siga siendo verdad.
        if tipo in ("charla_fluida", "interrupcion_barge_in"):
            estado["ultima_interaccion_ts"] = ahora
        estado["interrupciones_seguidas"] = int(estado["interrupciones_seguidas"])
        _guardar(uid, estado)
        return dict(estado)


def resumen_estado_emocional(usuario_id="local"):
    """Directriz breve de tono vocal (<=160 caracteres) para los prompts."""
    estado = obtener_estado(usuario_id)
    if (int(estado["interrupciones_seguidas"]) >= 3
            or float(estado["fastidio"]) >= 0.45):
        return "Ánimo: algo picada por tantas interrupciones, responde breve y directa"
    ultimo = float(estado["ultima_interaccion_ts"] or 0.0)
    if ((not ultimo or (_ahora() - ultimo) > UMBRAL_ABANDONO_SEG)
            and float(estado["curiosidad"]) >= 0.75):
        return "Ánimo: curiosa tras horas sin hablar, con reclamo amistoso"
    if (float(estado["complicidad"]) >= 0.65
            and float(estado["energia"]) >= 0.65):
        return "Ánimo: cómplice y relajada"
    if float(estado["energia"]) < 0.40:
        return "Ánimo: con poca energía, responde corto y suave"
    return "Ánimo: serena y atenta, sigue el tono de tu usuario"


def registrar_si_disponible(tipo, usuario_id="local"):
    """Enganche tolerante para los hilos de audio: nunca propaga errores."""
    try:
        return registrar_evento_emocional(tipo, usuario_id)
    except Exception:
        return None


__all__ = [
    "obtener_estado", "registrar_evento_emocional", "resumen_estado_emocional",
    "registrar_si_disponible",
]
