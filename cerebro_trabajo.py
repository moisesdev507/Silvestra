"""Memoria de trabajo corta (Short-Term Working Memory) para Silvestra / Lyris.

Mantiene los últimos 5 elementos contextuales manipulados en la sesión:
- ultimo_archivo: Ruta/nombre del último archivo creado, modificado o leído.
- ultima_carpeta: Directorio del último archivo o exploración.
- ultima_ventana: Diccionario de la última ventana externa activa.
- ultimo_recordatorio: Dict con el texto y hora del último aviso programado.
- ultima_habilidad: Nombre de la última habilidad aprendida o ejecutada.

Permite resolución de anáforas implícitas ("léelo", "agrégale...", "ejecútala").
"""
import os
import re
import threading

_bloqueo = threading.RLock()

_memoria = {
    "ultimo_archivo": None,
    "ultima_carpeta": None,
    "ultima_ventana": None,
    "ultimo_recordatorio": None,
    "ultima_habilidad": None,
}


def actualizar_archivo(ruta_o_nombre):
    """Actualiza el último archivo y su carpeta asociada."""
    if not ruta_o_nombre or not str(ruta_o_nombre).strip():
        return
    r = str(ruta_o_nombre).strip().replace("\\", "/")
    nom = os.path.basename(r)
    carpeta = os.path.dirname(r) or "workspace_lyris"
    with _bloqueo:
        _memoria["ultimo_archivo"] = r
        _memoria["ultima_carpeta"] = carpeta


def actualizar_carpeta(ruta):
    """Actualiza la última carpeta consultada."""
    if not ruta or not str(ruta).strip():
        return
    with _bloqueo:
        _memoria["ultima_carpeta"] = str(ruta).strip().replace("\\", "/")


def actualizar_ventana(ventana):
    """Actualiza la última ventana activa Win32."""
    if not ventana:
        return
    with _bloqueo:
        if isinstance(ventana, dict):
            _memoria["ultima_ventana"] = {
                "ejecutable": ventana.get("ejecutable") or "",
                "titulo": ventana.get("titulo") or "",
                "timestamp": ventana.get("timestamp") or 0.0,
            }
        else:
            _memoria["ultima_ventana"] = str(ventana)


def actualizar_recordatorio(texto, hora=None):
    """Actualiza el último recordatorio programado."""
    if not texto or not str(texto).strip():
        return
    with _bloqueo:
        _memoria["ultimo_recordatorio"] = {
            "texto": str(texto).strip(),
            "hora": str(hora).strip() if hora else "",
        }


def actualizar_habilidad(nombre):
    """Actualiza la última habilidad invocada o aprendida."""
    if not nombre or not str(nombre).strip():
        return
    with _bloqueo:
        _memoria["ultima_habilidad"] = str(nombre).strip().lower()


def obtener_memoria_trabajo():
    """Devuelve una copia de la memoria de trabajo activa."""
    with _bloqueo:
        return dict(_memoria)


def limpiar_memoria_trabajo():
    """Restablece la memoria de trabajo corta a su estado inicial."""
    with _bloqueo:
        for k in _memoria:
            _memoria[k] = None


def resolver_referencias(texto):
    """Resuelve referencias anafóricas hacia los elementos de la memoria de trabajo.

    Ejemplos:
    - 'léelo' / 'lee el archivo que acabas de crear' -> 'lee el archivo <ultimo_archivo>'
    - 'agrégale otro punto' -> 'añade al archivo <ultimo_archivo>: otro punto'
    - 'vuelve a ejecutarla' / 'ejecútala' -> 'ejecuta la habilidad <ultima_habilidad>'
    """
    if not texto or not str(texto).strip():
        return texto

    t = str(texto).strip()
    mem = obtener_memoria_trabajo()
    ult_arch = mem.get("ultimo_archivo")
    ult_hab = mem.get("ultima_habilidad")

    # 1. Petición de lectura implícita del último archivo
    patron_leer = r"^(?:por\s+favor\s+)?(?:lee(?:lo|la)?|léelo|léela|lee\s+(?:el\s+)?(?:archivo|documento|texto)(?:\s+que\s+(?:acabas\s+de\s+crear|creaste|guardaste))?)(?:\s+por\s+favor)?[\.\?!]?$"
    if re.search(patron_leer, t, re.I):
        if ult_arch:
            nom = os.path.basename(ult_arch)
            return f"lee el archivo {nom}"

    # 2. Petición de adición / agregado implícito al último archivo
    # Ej: "agrégale otro punto", "añade un párrafo al archivo", "agrégale: pendiente dos"
    patron_agregar = r"^(?:por\s+favor\s+)?(?:agrega(?:le)?|agrégale|anade(?:le)?|añade(?:le)?|añádele|adiciona(?:le)?|adiciónale)\s+(.+?)(?:\s+al\s+(?:archivo|documento))?(?:\s+por\s+favor)?[\.\?!]?$"
    m_add = re.search(patron_agregar, t, re.I)
    if m_add and ult_arch:
        contenido_extra = m_add.group(1).strip()
        # Si el archivo existe físicamente, intentar anexar respetando el contenido actual
        ruta_completa = ult_arch
        if not os.path.isabs(ruta_completa) and not os.path.exists(ruta_completa):
            candidata = os.path.join("workspace_lyris", os.path.basename(ult_arch))
            if os.path.exists(candidata):
                ruta_completa = candidata

        nom = os.path.basename(ult_arch)
        if os.path.exists(ruta_completa):
            try:
                with open(ruta_completa, "r", encoding="utf-8", errors="replace") as f:
                    contenido_actual = f.read().rstrip()
                nuevo_contenido = f"{contenido_actual}\n- {contenido_extra}" if contenido_actual else contenido_extra
                return f"escribir_archivo {nom} | {nuevo_contenido}"
            except Exception:
                pass
        return f"escribir_archivo {nom} | {contenido_extra}"

    # 3. Petición de ejecución implícita de la última habilidad
    patron_ejecutar = r"^(?:por\s+favor\s+)?(?:ejecuta(?:la|lo)?|ejecútala|ejecútalo|vuelve\s+a\s+ejecutar(?:la|lo)?)(?:\s+por\s+favor)?[\.\?!]?$"
    if re.search(patron_ejecutar, t, re.I):
        if ult_hab:
            return f"ejecuta la habilidad {ult_hab}"

    return t


def resumen_contexto_trabajo():
    """Genera una directiva compacta (<= 140 caracteres) para el prompt del sistema."""
    mem = obtener_memoria_trabajo()
    partes = []

    if mem.get("ultimo_archivo"):
        partes.append(f"archivo={os.path.basename(mem['ultimo_archivo'])}")
    if mem.get("ultima_habilidad"):
        partes.append(f"habilidad={mem['ultima_habilidad']}")
    if mem.get("ultimo_recordatorio"):
        rec = mem["ultimo_recordatorio"]
        partes.append(f"rec={rec.get('texto', '')[:20]}")
    if mem.get("ultima_ventana") and isinstance(mem["ultima_ventana"], dict):
        ejec = mem["ultima_ventana"].get("ejecutable")
        if ejec:
            partes.append(f"ventana={ejec}")

    if not partes:
        return ""

    res = f"[TRABAJO: {', '.join(partes)}]"
    if len(res) > 140:
        res = res[:137] + "...]"
    return res
