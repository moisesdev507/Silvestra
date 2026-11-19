"""Módulo de respaldo automático fuera de Git para los datos de Silvestra."""
import datetime
import glob
import os
import sys
import threading
import zipfile

import acciones

# Directorio de respaldos por defecto: fuera del repositorio Git
DIR_RESPALDOS_DEFECTO = os.path.join(os.path.expanduser("~"), "Documents", "Respaldos_Silvestra")
DIR_PROYECTO_DEFECTO = os.path.dirname(os.path.abspath(__file__))

# Reglas de exclusión estricta de seguridad
ARCHIVOS_EXCLUIDOS_EXACTOS = {
    "config.py",
    "config.example.py",
    ".env",
    "silvestra.log",
    "acciones_log.txt",
}

EXTENSIONES_EXCLUIDAS = {
    ".py",
    ".pyc",
    ".env",
    ".log",
    ".tmp",
    ".exe",
    ".dll",
    ".pyd",
    ".lock",
}

CARPETAS_EXCLUIDAS = {
    ".git",
    ".venv",
    "__pycache__",
    "scratch",
    ".pytest_cache",
    ".gemini",
    "build",
    "dist",
}

PALABRAS_PROHIBIDAS = {
    "token",
    "secret",
    "password",
    "credential",
}

# Archivos de datos del usuario que deben respaldarse si existen
ARCHIVOS_DATOS_OBJETIVO = [
    "memoria.json",
    "diario.md",
    "recordatorios.json",
    "estado.json",
    "conversaciones_dia.json",
    "perfil_conversacion.json",
    "hilos.json",
    "ideas.json",
    "propuestas.json",
    "correcciones.json",
    "notas.json",
    "apps_permitidas.json",
    "alma.txt",
]

CARPETAS_DATOS_OBJETIVO = [
    "propuestas",
]


def es_archivo_seguro(nombre_archivo):
    """Verifica que el archivo no contenga claves, código ni logs del sistema."""
    nombre_limpio = os.path.basename(nombre_archivo).strip().lower()

    if nombre_limpio in ARCHIVOS_EXCLUIDOS_EXACTOS:
        return False

    for ext in EXTENSIONES_EXCLUIDAS:
        if nombre_limpio.endswith(ext):
            return False

    for pal in PALABRAS_PROHIBIDAS:
        if pal in nombre_limpio:
            return False

    return True


def rotar_respaldos(directorio_destino, max_respaldos=10):
    """Mantiene como máximo los últimos 10 archivos de respaldo en disco."""
    patron = os.path.join(directorio_destino, "respaldo_silvestra_*.zip")
    archivos = sorted(glob.glob(patron), key=os.path.getmtime)
    eliminados = 0
    if len(archivos) > max_respaldos:
        sobrantes = archivos[:-max_respaldos]
        for f in sobrantes:
            try:
                os.remove(f)
                eliminados += 1
            except Exception:
                pass
    return eliminados


def generar_respaldo(directorio_origen=None, directorio_destino=None, max_respaldos=10):
    """Crea un archivo ZIP con los datos reales del usuario fuera del repositorio."""
    origen = directorio_origen or DIR_PROYECTO_DEFECTO
    destino = directorio_destino or DIR_RESPALDOS_DEFECTO

    try:
        os.makedirs(destino, exist_ok=True)
    except Exception as e:
        return False, f"No se pudo crear carpeta de respaldo: {e}", []

    ahora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_zip = f"respaldo_silvestra_{ahora}.zip"
    ruta_zip = os.path.join(destino, nombre_zip)

    archivos_a_incluir = []

    # 1. Archivos principales del usuario
    for nom in ARCHIVOS_DATOS_OBJETIVO:
        ruta = os.path.join(origen, nom)
        if os.path.isfile(ruta) and es_archivo_seguro(nom):
            archivos_a_incluir.append((ruta, nom))

    # 2. Carpetas de datos de usuario
    for carp in CARPETAS_DATOS_OBJETIVO:
        ruta_carp = os.path.join(origen, carp)
        if os.path.isdir(ruta_carp) and carp not in CARPETAS_EXCLUIDAS:
            for raiz, _, archivos in os.walk(ruta_carp):
                for arch in archivos:
                    if es_archivo_seguro(arch):
                        r_completa = os.path.join(raiz, arch)
                        r_relativa = os.path.relpath(r_completa, origen)
                        archivos_a_incluir.append((r_completa, r_relativa))

    if not archivos_a_incluir:
        return False, "No se encontraron datos para respaldar", []

    try:
        with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for ruta_real, ruta_interna in archivos_a_incluir:
                zf.write(ruta_real, arcname=ruta_interna)
    except Exception as e:
        return False, f"Error al comprimir zip: {e}", []

    # Rotar respaldos viejos
    rotar_respaldos(destino, max_respaldos=max_respaldos)

    incluidos = [rel for _, rel in archivos_a_incluir]
    return True, ruta_zip, incluidos


def instalar(app):
    """Instala la acción crear_respaldo para invocación por voz o texto."""
    def _accion_respaldo(arg=None):
        def _hilo():
            ok, ruta, incluidos = generar_respaldo()
            if ok:
                cant = len(incluidos)
                msg = f"Listo, creé un respaldo con {cant} archivos en tu carpeta de Documentos."
                burbuja = f"📦 RESPALDO CREADO:\n{ruta}\n({cant} archivos guardados)"
            else:
                msg = "No pude crear el respaldo en este momento."
                burbuja = f"❌ Error en respaldo:\n{ruta}"

            if app and hasattr(app, "cola"):
                app.cola.put(("hablar_registro", (msg, burbuja)))

        threading.Thread(target=_hilo, daemon=True, name="HiloRespaldo").start()
        return True, "Generando respaldo de datos en segundo plano..."

    acciones.registrar(
        "crear_respaldo",
        _accion_respaldo,
        "crea una copia de seguridad en zip con los datos del usuario en la carpeta Documentos",
    )
    return True


if __name__ == "__main__":
    print("=== INICIANDO RESPALDO DE SILVESTRA ===")
    exito, ruta_res, lista = generar_respaldo()
    if exito:
        print(f"OK: Respaldo generado con éxito.")
        print(f"Ruta: {ruta_res}")
        print(f"Archivos guardados ({len(lista)}):")
        for item in lista:
            print(f"  - {item}")
        sys.exit(0)
    else:
        print(f"ERROR: {ruta_res}")
        sys.exit(1)
