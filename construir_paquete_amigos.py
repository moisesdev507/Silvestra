"""Genera un paquete portable de Kaya sin claves ni datos personales."""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
NOMBRE = "Kaya_Portable"
DESTINO = os.path.join(BASE, "dist_amigos")

# Allowlist de modelos genéricos. Los modelos de voz local pesados se descargan aparte.
MODELOS = (
    "modelos/silero_vad.onnx",
    "modelos/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
    "modelos/face_detection_yunet_2023mar.onnx",
    "modelos/face_recognition_sface_2021dec.onnx",
    "modelos/hand_landmarker.task",
)

# CLAVE de la plantilla -> variable de entorno que la poblará en la laptop del amigo.
ENTORNOS = {
    "CLAVE": "GROQ_API_KEY",
    "CLAVE_GOOGLE": "GEMINI_API_KEY",
    "CLAVE_OPENROUTER": "OPENROUTER_API_KEY",
    "CLAVE_CEREBRAS": "CEREBRAS_API_KEY",
    "CLAVE_MISTRAL": "MISTRAL_API_KEY",
    "CLAVE_NVIDIA": "NVIDIA_API_KEY",
    "CLAVE_CLOUDFLARE": "CLOUDFLARE_API_TOKEN",
    "ID_CUENTA_CLOUDFLARE": "CLOUDFLARE_ACCOUNT_ID",
    "CLAVE_GITHUB": "GITHUB_TOKEN",
    "CLAVE_SAMBANOVA": "SAMBANOVA_API_KEY",
    "CLAVE_COHERE": "COHERE_API_KEY",
    "TOKEN_TELEGRAM": "TELEGRAM_BOT_TOKEN",
    "ID_TELEGRAM_DUENO": "TELEGRAM_DUENO_ID",
}

CABECERA_CONFIG = '''"""Configuración limpia de Kaya: las claves se leen de .env, nunca se distribuyen."""
import os as _os

try:
    import rutas_app as _rutas
    _DIR_USUARIO = _rutas.dir_usuario()
except Exception:
    _DIR_USUARIO = _os.path.dirname(_os.path.abspath(__file__))


def _leer_env():
    datos = {}
    try:
        with open(_os.path.join(_DIR_USUARIO, ".env"),
                  "r", encoding="utf-8", errors="replace") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                nombre, valor = linea.split("=", 1)
                datos[nombre.strip()] = valor.strip().strip("\\"'")
    except Exception:
        pass
    return datos


_ENV = _leer_env()


def _cfg(nombre, defecto=""):
    return str(_ENV.get(nombre) or _os.environ.get(nombre) or defecto).strip()


'''

ENV_EJEMPLO = """# Copia este archivo como .env y pega tus propias claves.
# NUNCA compartas tu .env con nadie.
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPGRAM_API_KEY=
"""

LANZADOR = """@echo off
cd /d "%~dp0"
if not exist ".venv\\Scripts\\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
)
".venv\\Scripts\\python.exe" -m pip install --upgrade pip
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
".venv\\Scripts\\python.exe" main.py
if errorlevel 1 pause
"""

LEEME = """KAYA PORTABLE - INSTALACION EN TU LAPTOP
=========================================

1. Descomprime 'Kaya_Portable.zip' en una carpeta de tu computadora (por ejemplo Documentos\\Kaya).
2. Ejecuta 'Iniciar_Kaya.bat' con doble clic: creara .venv e instalara las dependencias.
3. Al abrir Kaya veras la pantalla de bienvenida: escribe tu nombre y pega tus claves.
   - Gemini:  https://aistudio.google.com/app/apikey
   - Groq:    https://console.groq.com/keys
   - Deepgram:https://console.deepgram.com/
4. Opcional: graba 3 frases para calibrar tu voz, o pulsa 'Omitir por ahora'.
5. Listo: pulsa 'Probar y Guardar'. Kaya guardara tu configuracion solo en esta laptop.

NOTA: este paquete NO incluye tus claves, memorias, diario ni huella de voz.
Los modelos locales pesados se pueden descargar con: python bajar_modelos.py
"""

NOMBRES_PROHIBIDOS = {
    ".env", "datos", ".git", "__pycache__", ".venv", "env", "venv",
    "scratch", "workspace_lyris", "dist_amigos", "silvestra.log",
    "credentials.json", "token.json", "google_token.json", "memoria.json",
    "estado.json", "diario.md", "dueno.npy", "voz_dueno.npy",
}
PATRONES_NOMBRE = ("*.tmp", "*.pyc", "*.npy", "*.db", "*.sqlite", "*.pem",
                   "*.key", "*.log", "client_secret*")
PATRONES_SECRETO = (
    re.compile(r"\bgsk_[A-Za-z0-9]{18,}"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9]{18,}"),
    re.compile(r"\bnvapi-[A-Za-z0-9]{18,}"),
    re.compile(r"\bAQ\.[A-Za-z0-9_-]{18,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bgk_live_[A-Za-z0-9]{18,}"),
    re.compile(r"\bcfut_[A-Za-z0-9]{18,}"),
    re.compile(r"\btvly-[A-Za-z0-9_-]{18,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{18,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|clave|password)[\w ]{0,6}[:=]\s*[\"'][A-Za-z0-9_.-]{16,}[\"']"),
    re.compile(r"(?<![A-Za-z0-9])[0-9a-f]{40}(?![A-Za-z0-9])", re.I),
)
EXT_TEXTO = {".py", ".txt", ".bat", ".md", ".json", ".example", ".ini", ".cfg"}


def _escribir(ruta, texto, crlf=False):
    with open(ruta, "w", encoding="utf-8", newline="\r\n" if crlf else "\n") as f:
        f.write(texto)


def _generar_config(origen, destino):
    """Genera un config.py sin secretos a partir de la plantilla pública."""
    plantilla = os.path.join(origen, "config.example.py")
    if not os.path.exists(plantilla):
        plantilla = os.path.join(BASE, "config.example.py")
    with open(plantilla, "r", encoding="utf-8", errors="replace") as f:
        texto = f.read()
    for nombre, variable in ENTORNOS.items():
        valor = (f'int(_cfg("{variable}", "0") or 0)' if nombre == "ID_TELEGRAM_DUENO"
                 else f'_cfg("{variable}")')
        texto = re.sub(rf"(?m)^{re.escape(nombre)} = .*$",
                       f"{nombre} = {valor}", texto, count=1)
    extra = ("\n# Claves usadas por los motores de voz y Live\n"
             "DEEPGRAM_API_KEY = _cfg(\"DEEPGRAM_API_KEY\")\n"
             "GEMINI_API_KEY = _cfg(\"GEMINI_API_KEY\")\n"
             "GROQ_API_KEY = _cfg(\"GROQ_API_KEY\")\n"
             "GOOGLE_API_KEY = GEMINI_API_KEY\n")
    _escribir(os.path.join(destino, "config.py"), CABECERA_CONFIG + texto.rstrip() + "\n" + extra)


def auditar(carpeta):
    """Devuelve una lista de problemas; vacía significa paquete limpio."""
    problemas = []
    for raiz, directorios, archivos in os.walk(carpeta):
        for nombre in list(directorios):
            if nombre in NOMBRES_PROHIBIDOS:
                problemas.append(f"Directorio prohibido: {nombre}")
                directorios.remove(nombre)
        for nombre in archivos:
            ruta = os.path.join(raiz, nombre)
            rel = os.path.relpath(ruta, carpeta).replace("\\", "/")
            if nombre in NOMBRES_PROHIBIDOS or any(
                    fnmatch.fnmatch(nombre, p) for p in PATRONES_NOMBRE):
                problemas.append(f"Archivo prohibido: {rel}")
                continue
            if os.path.splitext(nombre)[1].lower() not in EXT_TEXTO and not nombre.startswith(".env"):
                continue
            try:
                with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
            except Exception:
                continue
            for patron in PATRONES_SECRETO:
                if patron.search(contenido):
                    problemas.append(f"Posible secreto en {rel}: {patron.pattern[:28]}")
                    break
    return problemas


def construir(origen=None, destino=None):
    """Copia solo código y recursos genéricos, audita y comprime el paquete."""
    origen = origen or BASE
    destino = destino or DESTINO
    raiz = os.path.join(destino, NOMBRE)
    if os.path.exists(raiz):
        shutil.rmtree(raiz)
    os.makedirs(raiz, exist_ok=True)
    copiados = 0

    for nombre in sorted(os.listdir(origen)):
        if not nombre.endswith(".py") or nombre == "config.py":
            continue
        if nombre.startswith(("test_", "prueba_")):
            continue
        ruta = os.path.join(origen, nombre)
        if os.path.isfile(ruta):
            shutil.copy2(ruta, os.path.join(raiz, nombre))
            copiados += 1

    req = os.path.join(origen, "requirements.txt")
    if not os.path.exists(req):
        req = os.path.join(BASE, "requirements.txt")
    if os.path.exists(req):
        shutil.copy2(req, os.path.join(raiz, "requirements.txt"))
        copiados += 1

    for relativo in MODELOS:
        fuente = os.path.join(origen, *relativo.split("/"))
        if os.path.exists(fuente):
            destino_modelo = os.path.join(raiz, relativo)
            os.makedirs(os.path.dirname(destino_modelo), exist_ok=True)
            shutil.copy2(fuente, destino_modelo)
            copiados += 1

    fuente_sonidos = os.path.join(origen, "sonidos")
    if os.path.isdir(fuente_sonidos):
        for nombre in sorted(fnmatch.filter(os.listdir(fuente_sonidos), "*.wav")):
            os.makedirs(os.path.join(raiz, "sonidos"), exist_ok=True)
            shutil.copy2(os.path.join(fuente_sonidos, nombre),
                         os.path.join(raiz, "sonidos", nombre))
            copiados += 1

    _generar_config(origen, raiz)
    _escribir(os.path.join(raiz, ".env.example"), ENV_EJEMPLO)
    _escribir(os.path.join(raiz, "Iniciar_Kaya.bat"), LANZADOR, crlf=True)
    _escribir(os.path.join(raiz, "LEEME_INSTALACION.txt"), LEEME)
    copiados += 4

    problemas = auditar(raiz)
    if problemas:
        raise RuntimeError("Auditoría fallida; no se creó el ZIP:\n  - "
                           + "\n  - ".join(problemas[:20]))

    zip_path = os.path.join(destino, NOMBRE + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for raiz_actual, _, archivos in os.walk(raiz):
            for nombre in archivos:
                ruta = os.path.join(raiz_actual, nombre)
                zf.write(ruta, os.path.join(NOMBRE, os.path.relpath(ruta, raiz)))
    return {"carpeta": raiz, "zip": zip_path, "archivos": copiados, "problemas": []}


def main():
    parser = argparse.ArgumentParser(description="Construye Kaya_Portable sin datos privados")
    parser.add_argument("--origen", default=BASE, help="Carpeta de código fuente")
    parser.add_argument("--destino", default=DESTINO, help="Carpeta de salida")
    args = parser.parse_args()
    try:
        resultado = construir(args.origen, args.destino)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 1
    print(f"OK: {resultado['archivos']} archivos en {resultado['carpeta']}", flush=True)
    print(f"OK: auditoría limpia. ZIP: {resultado['zip']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
