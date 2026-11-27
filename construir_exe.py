"""Compila Kaya.exe standalone de Windows con PyInstaller, sin secretos ni .py expuestos."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import construir_paquete_amigos as empaquetador

BASE = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(BASE, "dist_exe")
NOMBRE = "Kaya"
EXCLUIR_PREFIJOS = ("prueba_", "test_", "construir_")
ARCHIVOS_RECURSO = ("alma.txt", "apps_permitidas.json", "requirements.txt")
CARPETAS_RECURSO = ("modelos", "sonidos")
TEXTO = {".py", ".txt", ".md", ".json", ".cfg", ".ini", ".example", ".bat"}
PATRONES_SECRETO = empaquetador.PATRONES_SECRETO

# Los hooks de PyInstaller dejan .py de estas bibliotecas como datos de runtime
# (cv2 necesita su config.py; google.genai, sherpa_onnx y websockets los leen como
# datos). El código de Kaya SIEMPRE queda compilado dentro del PYZ: cualquier .py
# en la raíz o directamente bajo _internal/ se considera fuente expuesta.
BIBLIOTECAS_RUNTIME = ("cv2", "google", "sherpa_onnx", "vosk", "websockets")
MODELO_VOSK = "modelos/vosk-model-small-es-0.42"
# Esquemas públicos de Google API: contienen hashes de 40 hex, no claves privadas.
DATOS_PUBLICOS = ("_internal/googleapiclient/discovery_cache/",)
ARCHIVO_FLAG_COMPARTIDA = "beta_compartida.flag"


def _es_codigo_kaya(rel):
    """True si el .py es fuente expuesta en lugar de un dato de biblioteca."""
    if not rel.endswith(".py"):
        return False
    partes = rel.split("/")
    if len(partes) >= 3 and partes[0] == "_internal" and partes[1] in BIBLIOTECAS_RUNTIME:
        return False
    return True

ENV_EJEMPLO = """# Copia el contenido de tu .env privado aquí si quieres precargar claves.
# Nunca compartas este archivo con tus claves reales.
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPGRAM_API_KEY=
KAYA_TECLA=Ctrl + Alt + K
KAYA_MODO_AUDIFONOS=0
"""

LEEME = """KAYA PARA WINDOWS - EJECUTABLE STANDALONE
==========================================

1. Descomprime 'Kaya_Windows.zip' en una carpeta (por ejemplo Documentos\\Kaya).
2. Haz doble clic en 'Kaya.exe'. No necesitas instalar Python.
3. La primera vez aparecerá la bienvenida: escribe tu nombre, pega tus claves,
   elige la tecla de encendido y si usas audífonos o parlantes.
   - Gemini:   https://aistudio.google.com/app/apikey
   - Groq:     https://console.groq.com/keys
   - Deepgram: https://console.deepgram.com/
4. Doble clic en el orbe abre 'Configuración de Kaya': cambia tecla/audio o graba
   3 frases para reconocer tu voz cuando quieras.

Tu configuración, memoria y grabaciones quedan en la carpeta de Kaya.exe.
El código fuente NO se distribuye: solo el ejecutable y sus recursos.
"""


def modulos_activos(origen=BASE):
    """Nombres de módulos .py activos, sin pruebas ni scripts de compilación."""
    nombres = []
    for nombre in sorted(os.listdir(origen)):
        if not nombre.endswith(".py") or nombre.startswith(EXCLUIR_PREFIJOS):
            continue
        modulo = nombre[:-3]
        if modulo != "config" and "." not in modulo:
            nombres.append(modulo)
    return nombres


def asegurar_pyinstaller():
    """Instala PyInstaller en el intérprete activo si no está disponible."""
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    print("[exe] PyInstaller no encontrado; instalando en el .venv...", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _escribir(ruta, texto):
    with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)


def preparar_staging(staging):
    """Copia código y recursos limpios; genera un config.py sin claves reales."""
    os.makedirs(staging, exist_ok=True)
    for modulo in modulos_activos():
        shutil.copy2(os.path.join(BASE, modulo + ".py"),
                     os.path.join(staging, modulo + ".py"))
    empaquetador._generar_config(BASE, staging)

    for nombre in ARCHIVOS_RECURSO:
        origen = os.path.join(BASE, nombre)
        if os.path.isfile(origen):
            shutil.copy2(origen, os.path.join(staging, nombre))
    for nombre in CARPETAS_RECURSO:
        origen = os.path.join(BASE, nombre)
        if os.path.isdir(origen):
            shutil.copytree(origen, os.path.join(staging, nombre), dirs_exist_ok=True)
    if not os.path.isdir(os.path.join(staging, MODELO_VOSK)):
        raise RuntimeError(f"Falta el modelo Vosk para el wake-word local: {MODELO_VOSK}")

    _escribir(os.path.join(staging, ".env.example"), ENV_EJEMPLO)
    _escribir(os.path.join(staging, "LEEME_KAYA_EXE.txt"), LEEME)


def recursos_para_empaquetar(staging):
    """Entradas de datos que deben viajar junto al ejecutable."""
    entradas = []
    for nombre in sorted(os.listdir(staging)):
        if nombre.endswith(".py") or nombre in ("config.py", "config.example.py"):
            continue
        ruta = os.path.join(staging, nombre)
        if os.path.isfile(ruta) or os.path.isdir(ruta):
            entradas.append(nombre)
    return entradas


def comando_pyinstaller(staging):
    """Construye la línea de comandos --onedir --windowed con todos los módulos."""
    cmd = [sys.executable, "-m", "PyInstaller", "--onedir", "--windowed",
           "--noconfirm", "--clean", "--name", NOMBRE]
    for modulo in modulos_activos():
        cmd.extend(("--hidden-import", modulo))
    cmd.extend(("--hidden-import", "vosk"))
    cmd.extend(("--collect-binaries", "vosk"))
    for nombre in recursos_para_empaquetar(staging):
        origen = os.path.join(staging, nombre)
        cmd.extend(("--add-data", origen + os.pathsep + nombre))
    cmd.extend((
        "--collect-data", "certifi",
        "--collect-binaries", "PySide6",
        "--collect-data", "PySide6",
        "--collect-data", "_sounddevice_data",
        "--collect-binaries", "_sounddevice_data",
        "--collect-all", "sherpa_onnx",
        "--collect-all", "onnxruntime",
        "--collect-all", "google.genai",
        "--collect-all", "websockets",
        "--distpath", DESTINO,
        "--workpath", os.path.join(BASE, "build", "kaya_exe"),
        "--specpath", os.path.join(BASE, "build", "kaya_exe"),
        os.path.join(staging, "main.py"),
    ))
    return cmd


def auditar(carpeta):
    """Devuelve problemas; vacío significa paquete limpio y listo para compartir."""
    problemas = []
    if not os.path.isfile(os.path.join(carpeta, NOMBRE + ".exe")):
        problemas.append("Falta Kaya.exe")
    for raiz, directorios, archivos in os.walk(carpeta):
        for nombre in list(directorios):
            if nombre in ("datos", "__pycache__", ".git", ".venv"):
                problemas.append(f"Directorio prohibido: {nombre}")
                directorios.remove(nombre)
        for nombre in archivos:
            ruta = os.path.join(raiz, nombre)
            rel = os.path.relpath(ruta, carpeta).replace("\\", "/")
            if nombre == ARCHIVO_FLAG_COMPARTIDA:
                continue
            if nombre == ".env" or nombre == "silvestra.log" or _es_codigo_kaya(rel):
                problemas.append(f"Archivo prohibido: {rel}")
                continue
            # El .py permitido es código de biblioteca con claves ficticias de prueba.
            if rel.endswith(".py") or any(rel.startswith(p) for p in DATOS_PUBLICOS):
                continue
            if os.path.splitext(nombre)[1].lower() not in TEXTO:
                continue
            try:
                with open(ruta, "r", encoding="utf-8", errors="replace") as archivo:
                    contenido = archivo.read()
            except Exception:
                continue
            for patron in PATRONES_SECRETO:
                if patron.search(contenido):
                    problemas.append(f"Posible secreto en {rel}: {patron.pattern[:28]}")
                    break
    return problemas


def buscar_iscc():
    """Busca el compilador de Inno Setup (ISCC.exe) en rutas estándar o PATH."""
    rutas_candidatas = [
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
    ]
    for ruta in rutas_candidatas:
        if os.path.isfile(ruta):
            return ruta
    which = shutil.which("ISCC.exe") or shutil.which("iscc")
    if which:
        return which
    return None


def comprimir(carpeta, ruta_zip):
    """Comprime toda la carpeta del ejecutable conservando 'Kaya/' como raíz."""
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for raiz, _, archivos in os.walk(carpeta):
            for nombre in archivos:
                ruta = os.path.join(raiz, nombre)
                zf.write(ruta, os.path.join(NOMBRE, os.path.relpath(ruta, carpeta)))


def construir():
    """Compila, audita y comprime; falla cerrado si aparece cualquier secreto."""
    asegurar_pyinstaller()
    os.makedirs(DESTINO, exist_ok=True)
    paquete = os.path.join(DESTINO, NOMBRE)
    shutil.rmtree(paquete, ignore_errors=True)
    shutil.rmtree(os.path.join(BASE, "build", "kaya_exe"), ignore_errors=True)

    with tempfile.TemporaryDirectory(prefix="kaya_staging_") as staging:
        preparar_staging(staging)
        cmd = comando_pyinstaller(staging)
        print(f"[exe] Compilando {len(modulos_activos())} módulos...", flush=True)
        subprocess.check_call(cmd, cwd=staging)

    problemas = auditar(paquete)
    if problemas:
        raise RuntimeError("Auditoría del ejecutable fallida:\n  - "
                           + "\n  - ".join(problemas[:20]))
    with open(os.path.join(paquete, ARCHIVO_FLAG_COMPARTIDA), "wb"):
        pass
    ruta_zip = os.path.join(DESTINO, "Kaya_Windows.zip")
    comprimir(paquete, ruta_zip)
    print(f"OK: auditoría limpia. Ejecutable: {os.path.join(paquete, NOMBRE + '.exe')}",
          flush=True)
    print(f"OK: ZIP listo para compartir: {ruta_zip}", flush=True)

    ruta_iss = os.path.join(BASE, "instalador_kaya.iss")
    iscc = buscar_iscc()
    if iscc and os.path.isfile(ruta_iss):
        print(f"[installer] Compilando instalador con Inno Setup ({iscc})...", flush=True)
        try:
            subprocess.check_call([iscc, ruta_iss], cwd=BASE)
            ruta_setup = os.path.join(DESTINO, "Kaya_Setup.exe")
            if os.path.isfile(ruta_setup):
                print(f"OK: Instalador Windows listo: {ruta_setup}", flush=True)
        except Exception as e:
            print(f"[installer] Aviso: Error al compilar instalador: {e}", flush=True)
    else:
        print(f"[installer] ISCC.exe no encontrado. Para generar Kaya_Setup.exe, "
              f"instala Inno Setup 6 y compila: {ruta_iss}", flush=True)

    return {"carpeta": paquete, "zip": ruta_zip, "problemas": []}


if __name__ == "__main__":
    construir()
