"""Validación dinámica de modelos al arrancar consultando GET /models."""
import json
import threading
import urllib.error
import urllib.request

import config

_modelos_desactivados = set()
_proveedores_desactivados = set()
_bloqueo_estado = threading.RLock()


def extraer_motivo(resp, codigo):
    """Extrae un fragmento descriptivo de error HTTP para el log de enfriamiento."""
    snippet = ""
    try:
        obj = resp.json()
        err = obj.get("error", {})
        snippet = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:
        snippet = resp.text
    snippet = " ".join((snippet or "").split())[:70]
    return f"HTTP {codigo}: {snippet}" if snippet else f"HTTP {codigo}"


def esta_desactivado(nombre, modelo):
    """Devuelve True si el modelo o el proveedor están fuera de rotación."""
    with _bloqueo_estado:
        return (nombre in _proveedores_desactivados
                or f"{nombre}::{modelo}" in _modelos_desactivados)


def desactivar_modelo(nombre, modelo):
    """Registra y desactiva un modelo inexistente o retirado."""
    clave = f"{nombre}::{modelo}"
    with _bloqueo_estado:
        if clave in _modelos_desactivados:
            return
        _modelos_desactivados.add(clave)
    print(f"[proveedores] modelo inexistente={modelo} desactivado", flush=True)


def desactivar_proveedor(nombre):
    """Saca un proveedor de rotación por credencial rechazada, sin exponer claves."""
    with _bloqueo_estado:
        if nombre in _proveedores_desactivados:
            return
        _proveedores_desactivados.add(nombre)
    print(f"[proveedores] proveedor={nombre} desactivado: credencial rechazada", flush=True)


TAREAS_VALIDADAS = ("charla", "razonamiento", "vision")


def _modelos_a_validar(prov):
    """Une la lista efectiva por tarea con la configuración, sin duplicados."""
    try:
        import proveedores_cadenas as pc
    except Exception:
        return []
    resultado = []

    def _anadir(modelos):
        for m in modelos or []:
            if m not in resultado:
                resultado.append(m)

    for tarea in TAREAS_VALIDADAS:
        try:
            _anadir(pc.obtener_modelos_tarea(prov, tarea))
        except Exception:
            pass
    for clave in ("modelos", "modelos_charla", "modelos_razonamiento", "modelos_vision"):
        _anadir(prov.get(clave, []))
    return resultado


def validar_proveedor(prov):
    """Consulta GET /models para un proveedor específico si tiene clave."""
    nombre = prov.get("nombre", "")
    clave = (prov.get("clave") or "").strip()
    base_url = (prov.get("base_url") or "").strip()
    if not clave or not base_url:
        return

    models_url = base_url.rstrip("/") + "/models"
    if "accounts/" in base_url and "/ai/v1" in base_url:
        models_url = base_url.replace("/ai/v1", "/ai/models/search")

    req = urllib.request.Request(
        models_url,
        headers={"Authorization": f"Bearer {clave}", "User-Agent": "Silvestra/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6.0) as r:
            if r.status != 200:
                return
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            ids = set()
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    for m in data["data"]:
                        if isinstance(m, dict) and "id" in m:
                            mid = str(m["id"])
                            ids.add(mid)
                            ids.add(mid.replace("models/", ""))
                elif "result" in data and isinstance(data["result"], list):
                    for m in data["result"]:
                        if isinstance(m, dict) and "name" in m:
                            ids.add(str(m["name"]))
            if not ids:
                return

            # Incluye la lista efectiva (la que realmente se va a intentar), no solo config.
            for m in _modelos_a_validar(prov):
                if m not in ids:
                    desactivar_modelo(nombre, m)
    except Exception:
        # Si falla la consulta a /models (timeout, red, sin soporte), no se desactiva nada
        pass


def validar_modelos_remotos():
    """Valida en segundo plano los modelos de todos los proveedores configurados."""
    try:
        import proveedores_cadenas as pc
        for p in config.PROVEEDORES:
            copia = dict(p)
            pc.refrescar_clave_proveedor(copia)
            validar_proveedor(copia)
        for ext in getattr(config, "PROVEEDORES_EXTRA", []):
            copia = dict(ext)
            copia["nombre"] = copia.get("nombre") or "Extra"
            copia["base_url"] = copia.get("url") or copia.get("base_url") or ""
            validar_proveedor(copia)
    except Exception as e:
        print(f"[proveedores] error durante validación de modelos: {e}", flush=True)


def iniciar_validacion_segundo_plano():
    """Lanza la validación en un hilo secundario daemon."""
    hilo = threading.Thread(target=validar_modelos_remotos, daemon=True, name="ValidadorModelos")
    hilo.start()
    return hilo
