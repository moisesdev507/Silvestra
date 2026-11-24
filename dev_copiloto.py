"""Copiloto de desarrollo: proyectos locales, Git, búsqueda de código y entorno.

Solo lectura salvo ``abrir_en_vscode``. Nunca abre ``config.py`` ni secretos.
"""
import os
import subprocess
import threading
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
UNIDAD = os.path.splitdrive(RAIZ)[0] + os.sep
HOGAR = os.path.expanduser("~")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

MARCADORES = {".git": "git", "pyproject.toml": "python",
              "requirements.txt": "python", "package.json": "node",
              "pom.xml": "java-maven"}
EXCLUIDOS = {".git", ".venv", "venv", "node_modules", "__pycache__", "modelos",
             "appdata", "windows", "program files", "program files (x86)",
             "$recycle.bin", "system volume information", "msys64", ".pytest_cache",
             ".idea", ".vscode", "dist", "build", "scratch", "oneDriveTemp"}
EXT_CODIGO = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".go",
              ".rs", ".html", ".css", ".sql", ".md", ".txt", ".json", ".toml")

_bloqueo = threading.RLock()
_cache = {"proyectos": [], "momento": 0.0}


def _cmd(args, timeout=4.0, cwd=None):
    """Ejecuta un comando sin consola y devuelve stdout como texto."""
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace",
                              creationflags=_NO_WINDOW)
        return proc.stdout or ""
    except Exception:
        return ""


def _inspeccionar(ruta, encontrados):
    nombre = os.path.basename(ruta.rstrip(os.sep))
    if not nombre or nombre.lower() in EXCLUIDOS:
        return
    try:
        with os.scandir(ruta) as it:
            presentes = {e.name.lower() for e in it}
    except OSError:
        return
    stack = [tech for marca, tech in MARCADORES.items() if marca in presentes]
    if stack:
        encontrados[ruta.lower()] = {
            "nombre": nombre, "ruta": ruta,
            "stack": ", ".join(dict.fromkeys(stack)),
        }


def descubrir_proyectos(max_profundidad=2):
    """Repositorios/proyectos activos en la unidad y en ``~`` (profundidad 1-2)."""
    try:
        profundidad = int(max_profundidad) if max_profundidad is not None and str(max_profundidad).strip().isdigit() else 2
    except (TypeError, ValueError):
        profundidad = 2
    with _bloqueo:
        if _cache["proyectos"] and time.time() - _cache["momento"] < 60.0:
            return [dict(p) for p in _cache["proyectos"]]
    encontrados = {}
    for raiz in (UNIDAD, HOGAR):
        try:
            with os.scandir(raiz) as it:
                primarios = [e.path for e in it
                             if e.is_dir(follow_symlinks=False)
                             and e.name.lower() not in EXCLUIDOS]
        except OSError:
            continue
        for primario in primarios:
            _inspeccionar(primario, encontrados)
            if profundidad < 2:
                continue
            try:
                with os.scandir(primario) as it:
                    secundarios = [e.path for e in it
                                   if e.is_dir(follow_symlinks=False)
                                   and e.name.lower() not in EXCLUIDOS]
            except OSError:
                continue
            for secundario in secundarios[:25]:
                _inspeccionar(secundario, encontrados)
    proyectos = sorted(encontrados.values(), key=lambda p: (
        p["nombre"].lower() != "proyecto_silvestra", p["nombre"].lower()))[:60]
    with _bloqueo:
        _cache["proyectos"] = [dict(p) for p in proyectos]
        _cache["momento"] = time.time()
    return proyectos


def _resolver(nombre_o_ruta=None):
    """Resuelve un nombre de proyecto o ruta a un directorio existente."""
    if not nombre_o_ruta:
        return RAIZ
    valor = os.path.expanduser(str(nombre_o_ruta).strip())
    if os.path.isdir(valor):
        return os.path.abspath(valor)
    bajo = valor.lower()
    for proyecto in descubrir_proyectos():
        if proyecto["nombre"].lower() == bajo or proyecto["nombre"].lower() in bajo:
            return proyecto["ruta"]
    candidato = os.path.join(UNIDAD, valor)
    if os.path.isdir(candidato):
        return os.path.abspath(candidato)
    return RAIZ


def estado_git(nombre_o_ruta=None):
    """Rama, ``git status -sb`` y últimos 5 commits del proyecto indicado."""
    ruta = _resolver(nombre_o_ruta)
    rama = _cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], 5.0, ruta).strip()
    estado = _cmd(["git", "status", "-sb"], 5.0, ruta).strip()
    registro = _cmd(["git", "log", "-n", "5", "--oneline"], 5.0, ruta).strip()
    return {"ruta": ruta, "rama": rama, "status": estado, "log": registro,
            "texto": (f"{os.path.basename(ruta)} | rama {rama or '?'} | "
                      f"{estado.splitlines()[0] if estado else 'sin estado'} | "
                      f"últimos: {registro.replace(chr(10), ' / ')[:400]}")}


def buscar_codigo(consulta, nombre_o_ruta=None, limite=40):
    """Busca texto en fuentes del proyecto; jamás abre ``config.py``."""
    aguja = str(consulta or "").strip().lower()
    if not aguja:
        return []
    ruta = _resolver(nombre_o_ruta)
    resultados = []
    for base, dirs, archivos in os.walk(ruta):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUIDOS]
        for nombre in archivos:
            bajo = nombre.lower()
            if bajo == "config.py" or not bajo.endswith(EXT_CODIGO):
                continue
            completo = os.path.join(base, nombre)
            try:
                with open(completo, "r", encoding="utf-8", errors="replace") as archivo:
                    for numero, linea in enumerate(archivo, 1):
                        if aguja in linea.lower():
                            resultados.append({
                                "archivo": os.path.relpath(completo, ruta),
                                "linea": numero,
                                "fragmento": linea.strip()[:180],
                            })
                            if len(resultados) >= limite:
                                return resultados
            except OSError:
                continue
    return resultados


def estado_entorno_dev():
    """Procesos de desarrollo y puertos TCP locales en escucha."""
    lista = _cmd(["tasklist", "/FO", "CSV", "/NH"], 4.0).lower()
    objetivos = ("code.exe", "python.exe", "node.exe", "java.exe")
    procesos = {nombre: lista.count('"' + nombre + '"') for nombre in objetivos}
    puertos, vistos = [], set()
    for linea in _cmd(["netstat", "-ano", "-p", "tcp"], 5.0).splitlines():
        if "listening" not in linea.lower():
            continue
        partes = linea.split()
        if len(partes) < 4:
            continue
        clave = (partes[1], partes[-1])
        if clave in vistos:
            continue
        vistos.add(clave)
        puertos.append({"direccion": partes[1], "pid": partes[-1]})
        if len(puertos) >= 20:
            break
    return {"procesos": procesos, "puertos": puertos,
            "texto": ("Procesos: " + ", ".join(f"{k}={v}" for k, v in procesos.items())
                      + f". Puertos escuchando: {len(puertos)} "
                      + ", ".join(p["direccion"] for p in puertos[:8]))}


def abrir_en_vscode(nombre_o_ruta=None):
    """Abre un proyecto en VS Code de forma inmediata (no bloqueante)."""
    ruta = _resolver(nombre_o_ruta)
    if not os.path.isdir(ruta):
        return False
    exe = None
    try:
        import control_pc
        exe = control_pc.resolver_ruta_vscode()
    except Exception:
        pass
    try:
        subprocess.Popen([exe or "code.cmd", ruta], cwd=ruta, shell=False,
                         close_fds=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        return True
    except Exception:
        return False


def telemetria_pc():
    """Telemetría de CPU/RAM/batería/disco reutilizando ``telemetria.py``."""
    try:
        import telemetria
        sistema = telemetria.estado_sistema()
        disco = telemetria.estado_disco()
        return {"texto": sistema.get("texto", ""), "cpu": sistema.get("cpu"),
                "ram_pct": sistema.get("ram_pct"), "disco": disco}
    except Exception as exc:
        return {"texto": f"Telemetría no disponible ({type(exc).__name__})"}


__all__ = ["RAIZ", "descubrir_proyectos", "estado_git", "buscar_codigo",
           "estado_entorno_dev", "abrir_en_vscode", "telemetria_pc"]
