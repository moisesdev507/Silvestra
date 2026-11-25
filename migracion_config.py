"""Migración segura de claves antiguas desde config.py hacia .env."""
from __future__ import annotations

import ast
import os
import tempfile

ALIASES = {
    "GEMINI_API_KEY": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAVE_GOOGLE"),
    "GROQ_API_KEY": ("GROQ_API_KEY", "GROQ_KEY", "CLAVE"),
    "DEEPGRAM_API_KEY": ("DEEPGRAM_API_KEY", "CLAVE_DEEPGRAM"),
}
CABECERA = "# Claves privadas de Kaya. Nunca compartas este archivo.\n"


def leer_asignaciones(ruta):
    """Extrae asignaciones de texto sin ejecutar código del archivo."""
    if not ruta or not os.path.isfile(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            arbol = ast.parse(f.read(), filename=ruta)
    except Exception:
        return {}
    datos = {}
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign) or not isinstance(nodo.value, ast.Constant):
            continue
        valor = nodo.value.value
        if not isinstance(valor, str):
            continue
        for destino in nodo.targets:
            if isinstance(destino, ast.Name):
                datos[destino.id] = valor.strip()
    return datos


def escribir_env(ruta_env, claves):
    """Reemplaza atómicamente solo las claves indicadas y preserva el resto."""
    try:
        lineas = []
        if os.path.exists(ruta_env):
            with open(ruta_env, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.read().splitlines()
        objetivo = set(claves)
        finales, vistos = [], set()
        for linea in lineas:
            nombre = linea.split("=", 1)[0].strip().lstrip("#")
            if nombre.lower().startswith("export "):
                nombre = nombre[7:].strip()
            if nombre in objetivo:
                if nombre not in vistos:
                    finales.append(f"{nombre}={str(claves[nombre]).strip()}")
                    vistos.add(nombre)
                continue
            finales.append(linea)
        for nombre, valor in claves.items():
            if nombre not in vistos:
                finales.append(f"{nombre}={str(valor).strip()}")
        texto = CABECERA + "\n".join(finales).strip() + "\n"
        directorio = os.path.dirname(os.path.abspath(ruta_env))
        os.makedirs(directorio, exist_ok=True)
        fd, temporal = tempfile.mkstemp(prefix=".env-", dir=directorio)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(temporal, 0o600)
        except Exception:
            pass
        os.replace(temporal, ruta_env)
        return True
    except Exception as e:
        print(f"[migracion] No se pudo escribir .env: {type(e).__name__}", flush=True)
        return False


def migrar_desde_config(base, actuales=None, es_valida=None, ruta_config=None):
    """Completa .env con claves válidas de config.py; no crea ni toca perfiles."""
    ruta_config = ruta_config or os.path.join(base, "config.py")
    datos = leer_asignaciones(ruta_config)
    if not datos:
        return {}
    actuales = dict(actuales or {})
    migradas = {}
    for canon, alias in ALIASES.items():
        valor_actual = str(actuales.get(canon) or "").strip()
        if es_valida and es_valida(canon, valor_actual):
            continue
        for nombre in alias:
            valor = str(datos.get(nombre) or "").strip()
            if valor and (not es_valida or es_valida(canon, valor)):
                migradas[canon] = valor
                break
    if not migradas or not escribir_env(os.path.join(base, ".env"), migradas):
        return {}
    print("[migracion] Claves migradas desde config.py: "
          + ", ".join(sorted(migradas)), flush=True)
    return migradas


__all__ = ["ALIASES", "leer_asignaciones", "escribir_env", "migrar_desde_config"]
