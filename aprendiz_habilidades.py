"""Motor de auto-aprendizaje de habilidades seguras con auditoría AST para Lyris."""
import ast
import datetime
import importlib.util
import json
import os
import re
import threading

import persistencia_segura as ps

_bloqueo = threading.RLock()

DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_HABILIDADES = os.path.join(DIR_RAIZ, "habilidades_aprendidas")
RUTA_REGISTRO = os.path.join(DIR_HABILIDADES, "registro.json")

MODULOS_PROHIBIDOS = {
    "subprocess", "ctypes", "winreg", "socket", "pty",
    "multiprocessing", "signal", "inspect", "shutil"
}

LLAMADAS_PROHIBIDAS = {
    "eval", "exec", "compile", "__import__", "globals",
    "locals", "getattr", "setattr", "delattr"
}

MAX_BYTES_CODIGO = 15_360


def _asegurar_entorno():
    with _bloqueo:
        try:
            os.makedirs(DIR_HABILIDADES, exist_ok=True)
            init_file = os.path.join(DIR_HABILIDADES, "__init__.py")
            if not os.path.exists(init_file):
                with open(init_file, "w", encoding="utf-8") as f:
                    f.write('"""Paquete de habilidades aprendidas dinámicamente por Lyris."""\n')
            if not os.path.exists(RUTA_REGISTRO):
                ps.guardar_json_atomico(RUTA_REGISTRO, {"habilidades": {}})
        except Exception:
            pass


def _cargar_registro():
    _asegurar_entorno()
    with _bloqueo:
        datos = ps.cargar_json_seguro(RUTA_REGISTRO, {"habilidades": {}})
        if not isinstance(datos, dict) or "habilidades" not in datos:
            return {"habilidades": {}}
        return datos


def _guardar_registro(datos):
    _asegurar_entorno()
    with _bloqueo:
        return ps.guardar_json_atomico(RUTA_REGISTRO, datos)


def auditar_codigo(codigo):
    """Audita código Python mediante AST. Devuelve (es_seguro, motivo)."""
    if not codigo or not str(codigo).strip():
        return False, "El código está vacío."

    codigo_str = str(codigo).strip()
    codigo_bytes = codigo_str.encode("utf-8")
    if len(codigo_bytes) > MAX_BYTES_CODIGO:
        return False, f"El tamaño del código ({len(codigo_bytes)} B) supera el límite de {MAX_BYTES_CODIGO} B."

    try:
        arbol = ast.parse(codigo_str)
    except SyntaxError as e:
        return False, f"Error de sintaxis en el código: {e}"

    tiene_ejecutar = False

    for nodo in ast.walk(arbol):
        # 1. Validar imports
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                mod = alias.name.split(".")[0].lower()
                if mod in MODULOS_PROHIBIDOS:
                    return False, f"Importación prohibida por seguridad: '{alias.name}'."
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                mod = nodo.module.split(".")[0].lower()
                if mod in MODULOS_PROHIBIDOS:
                    return False, f"Importación prohibida por seguridad: '{nodo.module}'."

        # 2. Validar llamadas peligrosas
        elif isinstance(nodo, ast.Call):
            if isinstance(nodo.func, ast.Name):
                if nodo.func.id in LLAMADAS_PROHIBIDAS:
                    return False, f"Llamada a función prohibida: '{nodo.func.id}'."
            elif isinstance(nodo.func, ast.Attribute):
                attr = nodo.func.attr.lower()
                if attr in ("system", "popen", "spawn", "rmtree", "unlink", "remove"):
                    return False, f"Llamada a método restringido: '{attr}'."

        # 3. Detectar función ejecutar
        elif isinstance(nodo, ast.FunctionDef):
            if nodo.name == "ejecutar":
                tiene_ejecutar = True

    if not tiene_ejecutar:
        return False, "El módulo debe definir obligatoriamente la función 'ejecutar(arg=None, app=None)'."

    return True, "Auditoría AST aprobada: código seguro."


def _generar_plantilla(nombre, descripcion):
    """Genera código Python seguro de fallback cuando no se usa LLM externo."""
    return f'''"""Habilidad aprendida: {nombre}."""

def ejecutar(arg=None, app=None):
    """{descripcion}"""
    entrada = str(arg or "").strip()
    return f"Habilidad '{nombre}' ejecutada con argumento: '{{entrada}}'."
'''


def aprender_habilidad(arg, app=None):
    """Crea y audita una nueva habilidad, dejándola pendiente de confirmación."""
    if not arg or not str(arg).strip():
        return False, "Debes indicar el nombre y la descripción de la habilidad (ej: calcular_iva | Calcula el 7% de un monto)."

    partes = str(arg).split("|", 1)
    nom_raw = partes[0].strip().lower().replace(" ", "_")
    nombre = re.sub(r"[^a-z0-9_]", "", nom_raw)
    if not nombre:
        return False, "Nombre de habilidad inválido."

    descripcion = partes[1].strip() if len(partes) > 1 else f"Habilidad para {nombre}"

    # Generar código (con LLM si está disponible, o plantilla segura)
    codigo = None
    try:
        import proveedores
        prompt = (
            f"Escribe un módulo Python seguro para Silvestra que implemente la habilidad '{nombre}'.\n"
            f"Descripción: {descripcion}\n"
            f"REGLAS ESTRICTAS:\n"
            f"1. Define la función: def ejecutar(arg=None, app=None):\n"
            f"2. Devuelve un string explicativo con el resultado.\n"
            f"3. Prohibido subprocess, ctypes, winreg, os.system, socket, eval, exec.\n"
            f"4. Devuelve ÚNICAMENTE el código Python sin markdown ni explicaciones.\n"
        )
        res = proveedores.completar([{"role": "user", "content": prompt}], max_tokens=600)
        if res:
            res_limpio = re.sub(r"^```(?:python)?\s*", "", res.strip(), flags=re.I)
            res_limpio = re.sub(r"\s*```$", "", res_limpio).strip()
            es_seguro, _ = auditar_codigo(res_limpio)
            if es_seguro:
                codigo = res_limpio
    except Exception:
        pass

    if not codigo:
        codigo = _generar_plantilla(nombre, descripcion)

    es_seguro, motivo = auditar_codigo(codigo)
    if not es_seguro:
        return False, f"La habilidad no pasó la auditoría de seguridad: {motivo}"

    _asegurar_entorno()
    nom_archivo = f"habilidad_{nombre}.py"
    ruta_archivo = os.path.join(DIR_HABILIDADES, nom_archivo)

    try:
        with open(ruta_archivo, "w", encoding="utf-8") as f:
            f.write(codigo)
    except Exception as e:
        return False, f"Error al guardar archivo de habilidad: {e}"

    reg = _cargar_registro()
    reg["habilidades"][nombre] = {
        "nombre": nombre,
        "descripcion": descripcion,
        "archivo": nom_archivo,
        "estado": "pendiente",
        "creada_en": datetime.datetime.now().isoformat(),
    }
    _guardar_registro(reg)

    return True, (
        f"He preparado la nueva habilidad '{nombre}' ({descripcion}). "
        f"Código auditado y seguro. ¿Deseas que la active? Di 'aprobar habilidad {nombre}' o 'confirmar_habilidad'."
    )


def _activar_modulo_habilidad(nombre, info, app=None):
    """Carga dinámicamente un archivo de habilidad y lo registra en acciones vivas."""
    import acciones
    archivo = info.get("archivo")
    if not archivo:
        return False, "Falta archivo en el registro."

    ruta = os.path.join(DIR_HABILIDADES, archivo)
    if not os.path.exists(ruta):
        return False, f"No existe el archivo {archivo}."

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        codigo = f.read()

    es_seguro, motivo = auditar_codigo(codigo)
    if not es_seguro:
        return False, f"Fallo de seguridad al cargar: {motivo}"

    try:
        spec = importlib.util.spec_from_file_location(f"habilidades_aprendidas.{nombre}", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "ejecutar", None)
        if not callable(fn):
            return False, "El módulo no tiene función 'ejecutar'."

        def _envoltorio(arg=None):
            return fn(arg, app)

        desc = info.get("descripcion", f"Habilidad aprendida {nombre}")
        acciones.registrar(nombre, _envoltorio, desc, con_texto=True)
        return True, "Activada"
    except Exception as e:
        return False, f"Error al cargar módulo: {e}"


def confirmar_habilidad(arg=None, app=None):
    """Aprueba una habilidad pendiente y la incorpora de inmediato al repertorio."""
    reg = _cargar_registro()
    habs = reg.get("habilidades", {})

    nombre = None
    if arg and str(arg).strip():
        limpio = str(arg).strip().lower().replace(" ", "_")
        if limpio in habs:
            nombre = limpio
        else:
            # Buscar por coincidencia parcial si el usuario dijo "aprobar habilidad xyz"
            for k in habs:
                if k in limpio:
                    nombre = k
                    break

    if not nombre:
        # Tomar la última habilidad pendiente
        pendientes = [k for k, v in habs.items() if v.get("estado") == "pendiente"]
        if pendientes:
            nombre = pendientes[-1]

    if not nombre or nombre not in habs:
        return False, "No encontré ninguna habilidad pendiente de aprobación."

    info = habs[nombre]
    ok, msg = _activar_modulo_habilidad(nombre, info, app)
    if not ok:
        return False, f"No se pudo activar '{nombre}': {msg}"

    info["estado"] = "aprobada"
    info["aprobada_en"] = datetime.datetime.now().isoformat()
    _guardar_registro(reg)

    return True, f"Habilidad '{nombre}' aprobada con éxito e incorporada a mis capacidades."


def cargar_habilidades_aprendidas(app=None):
    """Carga todas las habilidades aprobadas al iniciar el sistema."""
    reg = _cargar_registro()
    habs = reg.get("habilidades", {})
    cargadas = 0
    for nombre, info in habs.items():
        if info.get("estado") == "aprobada":
            ok, _ = _activar_modulo_habilidad(nombre, info, app)
            if ok:
                cargadas += 1
    if cargadas > 0:
        print(f"[aprendiz] Se cargaron {cargadas} habilidad(es) aprendida(s).", flush=True)
    return cargadas
