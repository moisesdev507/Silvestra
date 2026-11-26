"""Respaldo opcional y asíncrono de memoria a Supabase.

Sin SUPABASE_URL/SUPABASE_KEY el módulo es un no-op: nunca abre red,
nunca lanza hilos y la memoria local sigue siendo instantánea (SQLite).
Con claves, encola upserts/borrados y los envía un único hilo daemon con
httpx, sin tocar jamás el hilo de audio ni los widgets de Qt.
"""
import os
import queue
import threading

import httpx

TABLA = "kaya_memorias"
TIMEOUT_SEG = 3.0
_MAX_COLA = 500

_lock = threading.RLock()
_url = ""
_key = ""
_activo = False
_revisado = False
_cola = queue.Queue(maxsize=_MAX_COLA)
_hilo = None
_enviados = 0
_error = ""


def _leer_env():
    """Lee .env igual que live_audio: sin python-dotenv y sin imprimir secretos."""
    valores = {}
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(ruta):
        return valores
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                texto = linea.strip()
                if not texto or texto.startswith("#") or "=" not in texto:
                    continue
                clave, valor = texto.split("=", 1)
                clave = clave.strip().lstrip("export ")
                valores[clave] = valor.strip().strip("'\"")
    except Exception:
        pass
    return valores


def configurar(url=None, clave=None, forzar=False, iniciar_hilo=True):
    """Configura el respaldo una sola vez; devuelve True si quedó activo."""
    global _url, _key, _activo, _revisado, _hilo, _error
    with _lock:
        if _revisado and not forzar:
            return _activo
        u = str(url if url is not None else os.environ.get("SUPABASE_URL", "")).strip()
        k = str(clave if clave is not None else os.environ.get("SUPABASE_KEY", "")).strip()
        if not u or not k:
            try:
                datos = _leer_env()
                u = u or datos.get("SUPABASE_URL", "")
                k = k or datos.get("SUPABASE_KEY", "")
            except Exception:
                pass
        _url, _key = u.rstrip("/"), k
        _activo = bool(_url and _key)
        _revisado = True
        _error = ""
        if iniciar_hilo and _activo and (_hilo is None or not _hilo.is_alive()):
            _hilo = threading.Thread(target=_trabajador, name="supabase-memoria", daemon=True)
            _hilo.start()
        return _activo


def esta_activo():
    configurar()
    return _activo


def _cabeceras():
    return {
        "apikey": _key,
        "Authorization": "Bearer " + _key,
        "Content-Type": "application/json",
    }


def _encolar(item):
    if not configurar():
        return False
    try:
        _cola.put_nowait(item)
        return True
    except queue.Full:
        try:
            _cola.get_nowait()
            _cola.put_nowait(item)
            return True
        except Exception:
            return False


def notificar_guardado(fila):
    """Encola un UPSERT de un recuerdo recién creado/reemplazado."""
    if not isinstance(fila, dict):
        return False
    dato = {
        "id": fila.get("id"),
        "usuario_id": fila.get("usuario_id"),
        "contenido": str(fila.get("contenido") or ""),
        "categoria": str(fila.get("categoria") or "general"),
        "actualizado_en": str(fila.get("actualizado_en") or ""),
    }
    if dato["id"] is None or not dato["contenido"]:
        return False
    return _encolar(("upsert", dato))


def notificar_eliminacion(ids, usuario_id="local"):
    """Encola borrados por id. Acepta un id o una lista de ids."""
    if isinstance(ids, (int, str)):
        ids = [ids]
    validos = [i for i in (ids or []) if i is not None]
    if not validos:
        return False
    return _encolar(("delete", {"ids": validos, "usuario_id": usuario_id}))


def _enviar(operacion, dato):
    endpoints = _url + "/rest/v1/" + TABLA
    headers = dict(_cabeceras())
    if operacion == "upsert":
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        httpx.request("POST", endpoints, headers=headers, json=[dato], timeout=TIMEOUT_SEG)
        return
    headers["Prefer"] = "return=minimal"
    for recuerdo_id in dato.get("ids", []):
        httpx.request(
            "DELETE", endpoints, headers=headers,
            params={"id": "eq." + str(recuerdo_id)}, timeout=TIMEOUT_SEG,
        )


def _trabajador():
    global _enviados, _error
    while True:
        operacion, dato = _cola.get()
        try:
            _enviar(operacion, dato)
            with _lock:
                _enviados += 1
                _error = ""
        except Exception as exc:
            with _lock:
                _error = type(exc).__name__
        finally:
            _cola.task_done()


def sincronizar_pendientes(limite=50):
    """Drena hasta `limite` elementos en el hilo llamante (solo para pruebas)."""
    procesados = 0
    while procesados < limite:
        try:
            operacion, dato = _cola.get_nowait()
        except queue.Empty:
            break
        try:
            _enviar(operacion, dato)
            procesados += 1
        except Exception as exc:
            global _error
            with _lock:
                _error = type(exc).__name__
        finally:
            _cola.task_done()
    return procesados


def consultar(usuario_id="local", limite=50):
    """Lee recuerdos del respaldo; sin credenciales devuelve [] sin red."""
    if not configurar():
        return []
    try:
        respuesta = httpx.request(
            "GET", _url + "/rest/v1/" + TABLA, headers=_cabeceras(),
            params={
                "select": "id,contenido,categoria,actualizado_en",
                "usuario_id": "eq." + str(usuario_id),
                "limit": str(max(0, min(int(limite), 500))),
            },
            timeout=TIMEOUT_SEG,
        )
        if respuesta.status_code >= 400:
            return []
        datos = respuesta.json()
        return datos if isinstance(datos, list) else []
    except Exception:
        return []


def estado():
    """Devuelve telemetría compacta sin secretos."""
    with _lock:
        return {
            "activo": _activo,
            "pendientes": _cola.qsize(),
            "enviados": _enviados,
            "error": _error,
        }


def reiniciar_para_pruebas():
    """Permite probar el módulo sin depender del estado global del proceso."""
    global _revisado, _activo, _url, _key, _enviados, _error
    with _lock:
        while not _cola.empty():
            try:
                _cola.get_nowait()
                _cola.task_done()
            except queue.Empty:
                break
        _revisado = False
        _activo = False
        _url = _key = _error = ""
        _enviados = 0


__all__ = [
    "configurar", "esta_activo", "notificar_guardado", "notificar_eliminacion",
    "sincronizar_pendientes", "consultar", "estado", "reiniciar_para_pruebas",
]
