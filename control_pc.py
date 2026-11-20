"""Control de funciones del PC para Silvestra con lista de permisos (allowlist) explícita.

Permite abrir programas autorizados, controlar volumen y música con teclas multimedia
nativas de Windows (ctypes), y navegar a sitios web seguros en hilos secundarios.
"""
import ctypes
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser

import acciones
import config

KEYEVENTF_KEYUP = 0x0002

# Códigos de teclas virtuales multimedia en Windows
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3


def pulsar_tecla_vk(codigo_vk, veces=1, intervalo=0.04):
    """Envía pulsaciones de teclas virtuales de Windows mediante ctypes."""
    try:
        user32 = ctypes.windll.user32
        for _ in range(veces):
            user32.keybd_event(codigo_vk, 0, 0, 0)
            user32.keybd_event(codigo_vk, 0, KEYEVENTF_KEYUP, 0)
            if veces > 1:
                time.sleep(intervalo)
    except Exception as e:
        print(f"[control_pc] Error emitiendo tecla virtual {codigo_vk}: {e}", flush=True)


def ejecutar_en_hilo(funcion, *args):
    """Lanza la ejecución de una tarea lenta en un hilo secundario daemon."""
    threading.Thread(target=funcion, args=args, daemon=True).start()


def controlar_volumen(app, modo):
    """Controla el volumen de Windows mediante teclas multimedia nativas."""
    modo_norm = (modo or "").strip().lower()
    print(f"[control_pc] volumen modo='{modo_norm}'", flush=True)

    if any(k in modo_norm for k in ("subir", "alto", "mas", "aumentar")):
        pulsar_tecla_vk(VK_VOLUME_UP, veces=5)
        app.cola.put(("hablar", "Subiendo volumen."))
    elif any(k in modo_norm for k in ("bajar", "bajo", "menos", "disminuir")):
        pulsar_tecla_vk(VK_VOLUME_DOWN, veces=5)
        app.cola.put(("hablar", "Bajando volumen."))
    elif any(k in modo_norm for k in ("silenciar", "mute", "mutear", "quitar silencio", "desmutear")):
        pulsar_tecla_vk(VK_VOLUME_MUTE, veces=1)
        app.cola.put(("hablar", "Cambiando silencio de audio."))
    else:
        print(f"[control_pc] Modo de volumen no reconocido: '{modo_norm}'", flush=True)


def controlar_musica(app, comando):
    """Controla la reproducción multimedia de Windows mediante teclas multimedia nativas."""
    cmd_norm = (comando or "").strip().lower()
    print(f"[control_pc] musica comando='{cmd_norm}'", flush=True)

    if any(k in cmd_norm for k in ("pausar", "reanudar", "reproducir", "play", "pause", "parar", "seguir")):
        pulsar_tecla_vk(VK_MEDIA_PLAY_PAUSE, veces=1)
        app.cola.put(("hablar", "Pausando o reanudando música."))
    elif any(k in cmd_norm for k in ("siguiente", "next", "pasar", "adelantar")):
        pulsar_tecla_vk(VK_MEDIA_NEXT_TRACK, veces=1)
        app.cola.put(("hablar", "Siguiente canción."))
    elif any(k in cmd_norm for k in ("anterior", "atras", "previa", "prev")):
        pulsar_tecla_vk(VK_MEDIA_PREV_TRACK, veces=1)
        app.cola.put(("hablar", "Canción anterior."))
    else:
        print(f"[control_pc] Comando de música no reconocido: '{cmd_norm}'", flush=True)


def resolver_ruta_vscode():
    """Resuelve dinámicamente la ruta absoluta de Code.exe en Windows."""
    candidatos = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return os.path.abspath(c)

    for cmd in ("code.exe", "code.cmd", "code"):
        w = shutil.which(cmd)
        if w and os.path.isfile(w):
            return os.path.abspath(w)
    return None


def obtener_programas_permitidos():
    """Devuelve el diccionario de programas permitidos combinando config y detección de VS Code."""
    programas = dict(getattr(config, "PROGRAMAS_PERMITIDOS", {}))
    ruta_vs = resolver_ruta_vscode()
    if ruta_vs:
        for alias in ("vscode", "vs code", "visual studio code", "code"):
            programas[alias] = ruta_vs
    return programas


def abrir_programa(app, nombre, hablar=True):
    """Abre un ejecutable validado estrictamente contra la lista de programas permitidos."""
    nom_norm = (nombre or "").strip().lower().replace("_", " ")
    programas = obtener_programas_permitidos()

    # Búsqueda exacta o coincidencia en lista permitida
    exe_encontrado = None
    for clave, ejecutable in programas.items():
        if clave in nom_norm or nom_norm in clave:
            exe_encontrado = ejecutable
            nom_norm = clave
            break

    if not exe_encontrado:
        print(f"[control_pc] Programa no permitido bloqueado: '{nombre}'", flush=True)
        if hablar and app and hasattr(app, "cola"):
            app.cola.put(("hablar", f"El programa {nombre} no está en mi lista de permitidos por seguridad."))
        return False

    print(f"[control_pc] Abriendo programa permitido: '{nom_norm}' -> {exe_encontrado}", flush=True)
    try:
        flags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            [exe_encontrado],
            shell=False,
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if hablar and app and hasattr(app, "cola"):
            app.cola.put(("hablar", f"Abriendo {nom_norm}."))
        return True
    except Exception as e:
        print(f"[control_pc] Error iniciando programa {exe_encontrado}: {e}", flush=True)
        if hablar and app and hasattr(app, "cola"):
            app.cola.put(("hablar", f"No pude abrir {nom_norm} en el sistema."))
        return False


def abrir_web(app, sitio):
    """Abre un sitio web validado estrictamente contra la lista permitida."""
    sitio_norm = (sitio or "").strip().lower()
    sitios = getattr(config, "SITIOS_PERMITIDOS", {})
    dominios_permitidos = getattr(config, "DOMINIOS_WEB_PERMITIDOS", [])

    url_final = None
    # 1. Búsqueda por alias permitido (ej. 'youtube', 'github', 'wikipedia')
    for clave, url in sitios.items():
        if clave in sitio_norm or sitio_norm in clave:
            url_final = url
            break

    # 2. Validación de URL directa https contra dominios permitidos
    if not url_final:
        parsed = urllib.parse.urlparse(sitio_norm if "://" in sitio_norm else f"https://{sitio_norm}")
        if parsed.scheme == "https":
            netloc = parsed.netloc.lower()
            if any(dom in netloc for dom in dominios_permitidos):
                url_final = parsed.geturl()

    if not url_final:
        print(f"[control_pc] Sitio web no permitido bloqueado: '{sitio}'", flush=True)
        app.cola.put(("hablar", f"El sitio web {sitio} no está en mi lista permitida de navegación."))
        return

    print(f"[control_pc] Abriendo sitio web permitido: '{sitio_norm}' -> {url_final}", flush=True)
    try:
        webbrowser.open(url_final)
        app.cola.put(("hablar", f"Abriendo {sitio_norm}."))
    except Exception as e:
        print(f"[control_pc] Error abriendo navegador para {url_final}: {e}", flush=True)


def buscar_youtube(app, texto):
    """Abre una búsqueda en YouTube para el texto especificado."""
    query = (texto or "").strip()
    if not query:
        url = "https://www.youtube.com"
        msg = "Abriendo YouTube."
    else:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        msg = f"Buscando en YouTube {query}."

    print(f"[control_pc] Buscando en YouTube: '{query}' -> {url}", flush=True)
    try:
        webbrowser.open(url)
        app.cola.put(("hablar", msg))
    except Exception as e:
        print(f"[control_pc] Error buscando en YouTube: {e}", flush=True)


def instalar(app):
    """Registra las acciones de control de PC en acciones.py con validación allowlist."""
    acciones.registrar(
        "abrir_programa",
        lambda arg: ejecutar_en_hilo(abrir_programa, app, arg),
        "Abre un programa permitido de la PC (bloc de notas, calculadora, navegador, explorador, VS Code). Lleva texto con el nombre.",
        con_texto=True,
    )
    acciones.registrar(
        "volumen",
        lambda arg: ejecutar_en_hilo(controlar_volumen, app, arg),
        "Controla el volumen de Windows (subir, bajar, silenciar). Lleva texto con la orden.",
        con_texto=True,
    )
    acciones.registrar(
        "musica",
        lambda arg: ejecutar_en_hilo(controlar_musica, app, arg),
        "Controla la reproducción de música (pausar, reanudar, siguiente, anterior). Lleva texto con la orden.",
        con_texto=True,
    )
    acciones.registrar(
        "abrir_web",
        lambda arg: ejecutar_en_hilo(abrir_web, app, arg),
        "Abre un sitio web seguro permitido (YouTube, Google, GitHub, Wikipedia, Gmail). Lleva texto con el sitio.",
        con_texto=True,
    )
    acciones.registrar(
        "buscar_youtube",
        lambda arg: ejecutar_en_hilo(buscar_youtube, app, arg),
        "Busca videos o música en YouTube. Lleva texto con el término de búsqueda.",
        con_texto=True,
    )
    print("[control_pc] Módulo de control de PC instalado con éxito.", flush=True)
