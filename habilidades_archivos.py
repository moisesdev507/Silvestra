"""Primitivas seguras para manipulación de archivos y código por Lyris."""
import os
import re
import threading

_bloqueo = threading.RLock()

DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_WORKSPACE = os.path.join(DIR_RAIZ, "workspace_lyris")
DIR_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
DIR_DOCUMENTS = os.path.join(os.path.expanduser("~"), "Documents")

EXT_PROHIBIDAS = {
    ".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1", ".vbs",
    ".sh", ".bin", ".msi", ".pem", ".key", ".db", ".sqlite",
    ".env", ".ini"
}

EXT_PERMITIDAS_USUARIO = {".txt", ".md", ".json", ".csv", ".log"}
EXT_PERMITIDAS_WORKSPACE = {
    ".txt", ".md", ".py", ".json", ".csv", ".log",
    ".html", ".css", ".js", ".sql"
}

MAX_BYTES_ESCRITURA = 1_048_576  # 1 MB
MAX_BYTES_LECTURA = 16_384       # 16 KB


def _asegurar_workspace():
    try:
        os.makedirs(DIR_WORKSPACE, exist_ok=True)
    except Exception:
        pass


def validar_ruta(ruta_usuario, modo="lectura"):
    """Valida y resuelve una ruta dentro de las zonas seguras autorizadas."""
    _asegurar_workspace()
    if not ruta_usuario or not str(ruta_usuario).strip():
        return False, "", "Ruta de archivo no especificada."

    r = str(ruta_usuario).strip().strip("'\"")

    # Si es solo un nombre de archivo o ruta relativa simple, ubicarlo en workspace_lyris
    if not os.path.isabs(r):
        r_res = os.path.abspath(os.path.join(DIR_WORKSPACE, r))
    else:
        r_res = os.path.abspath(os.path.normpath(r))

    # Detectar zonas permitidas
    en_workspace = False
    en_desktop = False
    en_documents = False

    try:
        if os.path.commonpath([r_res, DIR_WORKSPACE]) == DIR_WORKSPACE:
            en_workspace = True
        elif os.path.commonpath([r_res, DIR_DESKTOP]) == DIR_DESKTOP:
            en_desktop = True
        elif os.path.commonpath([r_res, DIR_DOCUMENTS]) == DIR_DOCUMENTS:
            en_documents = True
    except Exception:
        return False, "", "Ruta inválida o de unidad no coincidente."

    if not (en_workspace or en_desktop or en_documents):
        return False, "", "Acceso denegado: solo se permite operar en workspace_lyris, Escritorio o Documentos."

    # Bloqueo estricto del núcleo de Silvestra fuera de workspace_lyris
    try:
        if os.path.commonpath([r_res, DIR_RAIZ]) == DIR_RAIZ and not en_workspace:
            return False, "", "Acceso denegado: está prohibido alterar o leer el código base del sistema."
    except Exception:
        pass

    _, ext = os.path.splitext(r_res)
    ext_baja = ext.lower()

    if ext_baja in EXT_PROHIBIDAS:
        return False, "", f"Extensión de archivo '{ext_baja}' prohibida por seguridad."

    if en_workspace:
        if ext_baja and ext_baja not in EXT_PERMITIDAS_WORKSPACE:
            return False, "", f"Extensión '{ext_baja}' no permitida en workspace."
    else:
        if ext_baja and ext_baja not in EXT_PERMITIDAS_USUARIO:
            return False, "", f"Extensión '{ext_baja}' no permitida en carpetas de usuario."

    return True, r_res, "OK"


def escribir_archivo(arg):
    """Escribe contenido seguro en una ruta autorizada. Formato: ruta | contenido."""
    if not arg or not str(arg).strip():
        return False, "Debes especificar la ruta y el contenido (ej: archivo.txt | contenido)."

    if "|" in arg:
        partes = arg.split("|", 1)
        ruta_raw = partes[0].strip()
        contenido = partes[1]
    else:
        ruta_raw = arg.strip()
        contenido = ""

    valido, ruta_abs, motivo = validar_ruta(ruta_raw, modo="escritura")
    if not valido:
        return False, motivo

    contenido_bytes = contenido.encode("utf-8", errors="replace")
    if len(contenido_bytes) > MAX_BYTES_ESCRITURA:
        return False, f"El contenido supera el límite máximo de {MAX_BYTES_ESCRITURA} bytes."

    with _bloqueo:
        try:
            os.makedirs(os.path.dirname(ruta_abs), exist_ok=True)
            tmp_path = ruta_abs + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(contenido_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, ruta_abs)
            nom = os.path.basename(ruta_abs)
            return True, f"Listo. Archivo '{nom}' guardado correctamente ({len(contenido_bytes)} bytes)."
        except Exception as e:
            return False, f"Error al escribir archivo: {e}"


def leer_archivo(arg):
    """Lee el contenido de un archivo seguro autorizado."""
    if not arg or not str(arg).strip():
        return False, "Debes especificar la ruta del archivo a leer."

    ruta_raw = str(arg).strip().split("|")[0].strip()
    valido, ruta_abs, motivo = validar_ruta(ruta_raw, modo="lectura")
    if not valido:
        return False, motivo

    if not os.path.exists(ruta_abs):
        return False, f"El archivo no existe: '{os.path.basename(ruta_abs)}'."

    if not os.path.isfile(ruta_abs):
        return False, "La ruta indicada no es un archivo regular."

    with _bloqueo:
        try:
            total = os.path.getsize(ruta_abs)
            with open(ruta_abs, "r", encoding="utf-8", errors="replace") as f:
                texto = f.read(MAX_BYTES_LECTURA)
            nom = os.path.basename(ruta_abs)
            if total > MAX_BYTES_LECTURA:
                texto += f"\n\n[... Truncado a {MAX_BYTES_LECTURA} de {total} bytes]"
            return True, f"=== {nom} ===\n{texto}"
        except Exception as e:
            return False, f"Error al leer archivo: {e}"


def listar_archivos(arg=None):
    """Lista archivos en workspace_lyris o subcarpetas permitidas."""
    _asegurar_workspace()
    directorio = DIR_WORKSPACE

    if arg and str(arg).strip():
        t = str(arg).strip().lower()
        if t in ("escritorio", "desktop"):
            directorio = DIR_DESKTOP
        elif t in ("documentos", "documents"):
            directorio = DIR_DOCUMENTS
        else:
            valido, ruta_abs, _ = validar_ruta(arg, modo="lectura")
            if valido and os.path.isdir(ruta_abs):
                directorio = ruta_abs

    if not os.path.exists(directorio):
        return True, "El directorio no existe todavía."

    with _bloqueo:
        try:
            entradas = os.listdir(directorio)
            archivos = []
            for item in sorted(entradas):
                p = os.path.join(directorio, item)
                if os.path.isfile(p):
                    sz = os.path.getsize(p)
                    archivos.append(f"- {item} ({sz} bytes)")
                elif os.path.isdir(p):
                    archivos.append(f"- [DIR] {item}/")
            if not archivos:
                return True, f"El directorio '{os.path.basename(directorio)}' está vacío."
            return True, f"Archivos en '{os.path.basename(directorio)}' ({len(archivos)} items):\n" + "\n".join(archivos)
        except Exception as e:
            return False, f"Error al listar archivos: {e}"
