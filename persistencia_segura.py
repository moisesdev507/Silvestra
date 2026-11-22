"""Persistencia atómica y resiliente para archivos JSON en Silvestra."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

_bloqueo_persistencia = threading.RLock()


def cargar_json_seguro(ruta: str, defecto: Any = None) -> Any:
    """Carga un archivo JSON de forma segura, retornando 'defecto' si está ausente o corrupto."""
    with _bloqueo_persistencia:
        if not os.path.exists(ruta):
            return defecto
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[persistencia] Archivo '{ruta}' corrupto o ilegible ({e}). Usando valor por defecto.", flush=True)
            return defecto


def guardar_json_atomico(ruta: str, datos: Any, indent: int = 2) -> bool:
    """Guarda datos en un archivo JSON mediante escritura atómica (NamedTemporaryFile + fsync + os.replace)."""
    with _bloqueo_persistencia:
        dir_destino = os.path.dirname(os.path.abspath(ruta))
        if not os.path.exists(dir_destino):
            os.makedirs(dir_destino, exist_ok=True)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dir_destino, delete=False, suffix=".tmp") as f:
                tmp_path = f.name
                json.dump(datos, f, ensure_ascii=False, indent=indent)
                f.flush()
                os.fsync(f.fileno())
            for intento in range(3):
                try:
                    os.replace(tmp_path, ruta)
                    return True
                except PermissionError:
                    if intento == 2:
                        raise
                    import time
                    time.sleep(0.02)
        except Exception as e:
            print(f"[persistencia] Error en escritura atómica hacia '{ruta}': {e}", flush=True)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False
