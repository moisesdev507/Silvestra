"""Claves API dinámicas: el entorno manda y `config` se sincroniza al instante."""
from __future__ import annotations

import os

import rutas_app

# Variable de entorno -> atributos históricos de config que deben reflejarla.
ATRIBUTOS = {
    "GEMINI_API_KEY": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAVE_GOOGLE"),
    "GOOGLE_API_KEY": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAVE_GOOGLE"),
    "GROQ_API_KEY": ("GROQ_API_KEY", "CLAVE"),
    "DEEPGRAM_API_KEY": ("DEEPGRAM_API_KEY", "CLAVE_DEEPGRAM"),
    "OPENROUTER_API_KEY": ("CLAVE_OPENROUTER",),
    "CEREBRAS_API_KEY": ("CLAVE_CEREBRAS",),
    "MISTRAL_API_KEY": ("CLAVE_MISTRAL",),
    "NVIDIA_API_KEY": ("CLAVE_NVIDIA",),
    "CLOUDFLARE_API_TOKEN": ("CLAVE_CLOUDFLARE",),
    "CLOUDFLARE_ACCOUNT_ID": ("ID_CUENTA_CLOUDFLARE",),
    "GITHUB_TOKEN": ("CLAVE_GITHUB",),
    "SAMBANOVA_API_KEY": ("CLAVE_SAMBANOVA",),
    "COHERE_API_KEY": ("CLAVE_COHERE",),
    "TELEGRAM_BOT_TOKEN": ("TOKEN_TELEGRAM",),
    "TELEGRAM_DUENO_ID": ("ID_TELEGRAM_DUENO",),
}


def leer_env(ruta=None):
    """Lee el .env del usuario sin ejecutar código; se llama en cada consulta."""
    ruta = ruta or os.path.join(rutas_app.dir_usuario(), ".env")
    datos = {}
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                if linea.lower().startswith("export "):
                    linea = linea[7:].strip()
                nombre, valor = linea.split("=", 1)
                nombre = nombre.strip()
                if nombre:
                    datos[nombre] = valor.strip().strip("'\"")
    except Exception:
        pass
    return datos


def valor(nombre, *atributos):
    """Clave vigente: entorno, .env recién leído y, por último, config legacy."""
    nombre = str(nombre or "").strip()
    actual = str(os.environ.get(nombre, "") or "").strip()
    if not actual and nombre:
        actual = str(leer_env().get(nombre, "") or "").strip()
        if actual:
            os.environ[nombre] = actual
    if not actual:
        try:
            import config
            for atributo in tuple(atributos) + ATRIBUTOS.get(nombre, ()):
                candidato = str(getattr(config, atributo, "") or "").strip()
                if candidato:
                    actual = candidato
                    break
        except Exception:
            pass
    return actual


def recargar(ruta_env=None):
    """Vuelca .env al entorno y actualiza los atributos de config sin reinicio."""
    datos = leer_env(ruta_env)
    for nombre, contenido in datos.items():
        if contenido:
            os.environ[nombre] = contenido
    try:
        import config
    except Exception:
        return datos
    for nombre, atributos in ATRIBUTOS.items():
        actual = str(os.environ.get(nombre, "") or "").strip()
        if not actual:
            continue
        for atributo in atributos:
            if atributo == "ID_TELEGRAM_DUENO":
                actual_attr = int(actual) if actual.isdigit() else 0
            else:
                actual_attr = actual
            setattr(config, atributo, actual_attr)
    return datos


__all__ = ["valor", "recargar", "leer_env", "ATRIBUTOS"]
