"""Control de la laptop para Silvestra (Windows).

Acciones por niveles:
- Lista permitida para apps y sitios web (apps_permitidas.json).
- subprocess sin shell=True.
- Teclas multimedia y ventanas con ctypes y PIL.
- Tareas en segundo plano con entrega a app.cola.
- Acciones peligrosas protegidas por control_seguridad con código.
"""
import ctypes
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
import urllib.parse
import webbrowser

from PIL import ImageGrab
import requests

import acciones
import control_seguridad

APPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps_permitidas.json")
CARPETAS = {
    "escritorio": os.path.join(os.path.expanduser("~"), "Desktop"),
    "documentos": os.path.join(os.path.expanduser("~"), "Documents"),
    "descargas": os.path.join(os.path.expanduser("~"), "Downloads"),
    "proyecto": os.path.dirname(os.path.abspath(__file__)),
}
SITIOS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "correo": "https://mail.google.com",
    "github": "https://www.github.com",
    "wikipedia": "https://es.wikipedia.org",
}
PROHIBIDAS_CERRAR = {"python", "code", "antigravity", "silvestra", "main"}


def normalizar(texto):
    """Convierte a minúsculas y elimina tildes para comparaciones limpias."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def cargar_apps():
    """Carga el diccionario de apps permitidas desde apps_permitidas.json."""
    if not os.path.exists(APPS_FILE):
        defaults = {
            "chrome": "chrome.exe", "edge": "msedge.exe", "spotify": "spotify.exe",
            "notepad": "notepad.exe", "bloc de notas": "notepad.exe", "calculadora": "calc.exe",
            "explorador": "explorer.exe", "word": "winword.exe", "excel": "excel.exe"
        }
        try:
            with open(APPS_FILE, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=2)
            return defaults
        except Exception:
            return defaults
    try:
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[control_laptop] Error leyendo apps_permitidas.json: {e}", flush=True)
        return {}


def _tecla(vk, repeticiones=1):
    """Emula eventos de teclado mediante ctypes."""
    user32 = ctypes.windll.user32
    for _ in range(repeticiones):
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.03)


def abrir_app(app, nombre):
    """Abre una aplicación de la lista permitida en un hilo secundario."""
    def _tarea():
        apps = cargar_apps()
        norm = normalizar(nombre)
        exe = next((v for k, v in apps.items() if normalizar(k) == norm or normalizar(k) in norm), None)
        if not exe:
            app.cola.put(("frase", "Esa aplicación no está en la lista permitida."))
            control_seguridad.registrar_log("LIBRE", "abrir_app", "app", "RECHAZADO", f"No permitida: {nombre}")
            return
        try:
            subprocess.Popen([exe], creationflags=0x08000000)
            app.cola.put(("frase", f"Abriendo {nombre}."))
            control_seguridad.registrar_log("LIBRE", "abrir_app", "app", "EXITO", exe)
        except Exception as e:
            app.cola.put(("frase", f"No pude abrir {nombre}."))
            control_seguridad.registrar_log("LIBRE", "abrir_app", "app", "ERROR", str(e)[:80])

    threading.Thread(target=_tarea, daemon=True).start()


def cerrar_app(app, nombre):
    """Cierra una aplicación permitida usando taskkill sin /F primero."""
    def _tarea():
        norm = normalizar(nombre)
        if any(p in norm for p in PROHIBIDAS_CERRAR):
            app.cola.put(("frase", "Por seguridad no puedo cerrar esa aplicación."))
            control_seguridad.registrar_log("LIBRE", "cerrar_app", "app", "RECHAZADO", f"Protegida: {nombre}")
            return
        apps = cargar_apps()
        exe = next((v for k, v in apps.items() if normalizar(k) == norm or normalizar(k) in norm), None)
        if not exe or any(p in exe.lower() for p in PROHIBIDAS_CERRAR):
            app.cola.put(("frase", "No puedo cerrar esa aplicación."))
            control_seguridad.registrar_log("LIBRE", "cerrar_app", "app", "RECHAZADO", f"Inválida: {nombre}")
            return
        try:
            subprocess.run(["taskkill", "/IM", exe], check=False, creationflags=0x08000000)
            app.cola.put(("frase", f"Cerrando {nombre}."))
            control_seguridad.registrar_log("LIBRE", "cerrar_app", "app", "EXITO", exe)
        except Exception as e:
            app.cola.put(("frase", f"No pude cerrar {nombre}."))
            control_seguridad.registrar_log("LIBRE", "cerrar_app", "app", "ERROR", str(e)[:80])

    threading.Thread(target=_tarea, daemon=True).start()


def ir_a(app, destino):
    """Navega a carpetas o sitios permitidos, o vuelve a la ventana anterior."""
    def _tarea():
        norm = normalizar(destino)
        if "anterior" in norm or "volver" in norm:
            user32 = ctypes.windll.user32
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x09, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x09, 0, 2, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            app.cola.put(("frase", "Volviendo a la ventana anterior."))
            control_seguridad.registrar_log("LIBRE", "ir_a", "app", "EXITO", "ventana_anterior")
            return
        for k, ruta in CARPETAS.items():
            if k in norm:
                try:
                    subprocess.Popen(["explorer.exe", ruta], creationflags=0x08000000)
                    app.cola.put(("frase", f"Abriendo la carpeta {k}."))
                    control_seguridad.registrar_log("LIBRE", "ir_a", "app", "EXITO", ruta)
                except Exception as e:
                    app.cola.put(("frase", f"No pude abrir la carpeta {k}."))
                    control_seguridad.registrar_log("LIBRE", "ir_a", "app", "ERROR", str(e)[:80])
                return
        for k, url in SITIOS.items():
            if k in norm:
                try:
                    webbrowser.open(url)
                    app.cola.put(("frase", f"Abriendo {k}."))
                    control_seguridad.registrar_log("LIBRE", "ir_a", "app", "EXITO", url)
                except Exception as e:
                    app.cola.put(("frase", f"No pude abrir el sitio {k}."))
                    control_seguridad.registrar_log("LIBRE", "ir_a", "app", "ERROR", str(e)[:80])
                return
        app.cola.put(("frase", "No reconozco ese destino en la lista permitida."))
        control_seguridad.registrar_log("LIBRE", "ir_a", "app", "RECHAZADO", f"Desconocido: {destino}")

    threading.Thread(target=_tarea, daemon=True).start()


_ducking_aplicado = False
_lock_ducking = threading.Lock()


def aplicar_ducking():
    """Baja el volumen ~24% mientras Silvestra habla o atiende con música de fondo."""
    global _ducking_aplicado
    import config
    if not getattr(config, "DUCKING_AUDIO", True):
        return
    with _lock_ducking:
        if not _ducking_aplicado:
            _tecla(0xAE, 12)
            _ducking_aplicado = True


def restaurar_ducking():
    """Restaura el volumen previo al ducking."""
    global _ducking_aplicado
    import config
    if not getattr(config, "DUCKING_AUDIO", True):
        return
    with _lock_ducking:
        if _ducking_aplicado:
            _tecla(0xAF, 12)
            _ducking_aplicado = False


def musica_youtube(app, consulta):
    """Busca y reproduce música en YouTube hablando primero y buscando en segundo plano."""
    tema = consulta or "música"
    app.musica_activa = True
    app.cola.put(("frase", f"Poniendo {tema} en YouTube."))
    control_seguridad.registrar_log("LIBRE", "musica_youtube", "app", "SOLICITADO", tema)

    def _tarea():
        url_busq = f"https://www.youtube.com/results?search_query={urllib.parse.quote(tema)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        video_id = None
        try:
            resp = requests.get(url_busq, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                m = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
                if m:
                    video_id = m.group(1)
        except Exception as e:
            print(f"[control_laptop] Fallo búsqueda YouTube: {e}", flush=True)

        if video_id:
            webbrowser.open(f"https://www.youtube.com/watch?v={video_id}&autoplay=1")
            control_seguridad.registrar_log("LIBRE", "musica_youtube", "app", "EXITO", video_id)
        else:
            webbrowser.open(url_busq)
            control_seguridad.registrar_log("LIBRE", "musica_youtube", "app", "FALLBACK", tema)

    threading.Thread(target=_tarea, daemon=True).start()


MAPA_MULTIMEDIA = {
    "subir": (0xAF, 5, "Subiendo volumen.", "subir_volumen"),
    "bajar": (0xAE, 5, "Bajando volumen.", "bajar_volumen"),
    "silenciar": (0xAD, 1, "Sonido silenciado o reactivado.", "silenciar"),
    "mute": (0xAD, 1, "Sonido silenciado o reactivado.", "silenciar"),
    "pausa": (0xB3, 1, "Pausando o reanudando reproducción.", "pausa_reanudar"),
    "reanudar": (0xB3, 1, "Pausando o reanudando reproducción.", "pausa_reanudar"),
    "siguiente": (0xB0, 1, "Siguiente canción.", "siguiente_cancion"),
    "anterior": (0xB1, 1, "Canción anterior.", "anterior_cancion"),
}


def multimedia(app, orden):
    """Control multimedia, captura y bloqueo de pantalla."""
    def _tarea():
        o = normalizar(orden)
        for k, (vk, reps, msg, act) in MAPA_MULTIMEDIA.items():
            if k in o:
                _tecla(vk, reps)
                if k in ("pausa", "reanudar", "silenciar", "mute"):
                    app.musica_activa = False
                    restaurar_ducking()
                app.cola.put(("frase", msg))
                control_seguridad.registrar_log("LIBRE", act, "app", "EXITO")
                return

        if "minimizar" in o:
            u = ctypes.windll.user32
            u.keybd_event(0x5B, 0, 0, 0)
            u.keybd_event(0x44, 0, 0, 0)
            time.sleep(0.05)
            u.keybd_event(0x44, 0, 2, 0)
            u.keybd_event(0x5B, 0, 2, 0)
            # Una sola voz: la confirmación ya la dijo respuesta_flujo.
            app.cola.put(("fin_voz", None))
            control_seguridad.registrar_log("LIBRE", "minimizar_todo", "app", "EXITO")
        elif "bloquear" in o:
            ctypes.windll.user32.LockWorkStation()
            app.cola.put(("frase", "Pantalla bloqueada."))
            control_seguridad.registrar_log("LIBRE", "bloquear_pantalla", "app", "EXITO")
        elif "captura" in o:
            try:
                dest = os.path.join(os.path.expanduser("~"), "Desktop")
                nombre_arch = f"captura_{time.strftime('%Y%m%d_%H%M%S')}.png"
                img = ImageGrab.grab()
                img.save(os.path.join(dest, nombre_arch), "PNG")
                app.cola.put(("frase", "Captura de pantalla guardada en el Escritorio."))
                control_seguridad.registrar_log("LIBRE", "captura_pantalla", "app", "EXITO", nombre_arch)
            except Exception as e:
                app.cola.put(("frase", "No pude guardar la captura de pantalla."))
                control_seguridad.registrar_log("LIBRE", "captura_pantalla", "app", "ERROR", str(e)[:80])

    threading.Thread(target=_tarea, daemon=True).start()


def _registrar_peligrosa(app, nombre_accion, comando_base, frase_ejecucion):
    """Crea y registra una acción de nivel CON CÓDIGO."""
    def _invocar():
        def _ejecutar(sim=False):
            if sim:
                app.cola.put(("frase", f"[Simulación] {frase_ejecucion}"))
                control_seguridad.registrar_log("CON_CODIGO", nombre_accion, "app", "SIMULACION")
            else:
                app.cola.put(("frase", frase_ejecucion))
                subprocess.Popen(comando_base, creationflags=0x08000000)
                control_seguridad.registrar_log("CON_CODIGO", nombre_accion, "app", "EJECUTADO")
        app.control_seguridad.solicitar_accion_peligrosa(nombre_accion, _ejecutar)
    return _invocar


def instalar(app):
    """Registra todas las acciones de control de laptop y seguridad."""
    control_seguridad.instalar(app)

    reg = acciones.registrar
    # 1. Acciones libres
    for a in ("abrir_app", "abrir_programa"):
        reg(a, lambda arg: abrir_app(app, arg), "abre una app permitida", con_texto=True)
    for c in ("cerrar_app", "cerrar_programa"):
        reg(c, lambda arg: cerrar_app(app, arg), "cierra una app permitida", con_texto=True)
    for i in ("ir_a", "abrir_carpeta", "abrir_sitio"):
        reg(i, lambda arg: ir_a(app, arg), "abre carpeta/sitio o ventana anterior", con_texto=True)
    for m in ("musica_youtube", "poner_musica"):
        reg(m, lambda arg: musica_youtube(app, arg), "reproduce música en YouTube", con_texto=True)

    reg("subir_volumen", lambda: multimedia(app, "subir"), "sube el volumen")
    reg("bajar_volumen", lambda: multimedia(app, "bajar"), "baja el volumen")
    reg("silenciar", lambda: multimedia(app, "silenciar"), "silencia o reactiva el sonido")
    reg("pausar_musica", lambda: multimedia(app, "pausa"), "pausa o reanuda la música")
    reg("reanudar_musica", lambda: multimedia(app, "reanudar"), "pausa o reanuda la música")
    reg("siguiente_cancion", lambda: multimedia(app, "siguiente"), "pasa a la siguiente canción")
    reg("anterior_cancion", lambda: multimedia(app, "anterior"), "vuelve a la canción anterior")
    reg("minimizar_todo", lambda: multimedia(app, "minimizar"), "minimiza todas las ventanas")
    reg("captura_pantalla", lambda: multimedia(app, "captura"), "guarda captura en el Escritorio")
    reg("guardar_captura", lambda: multimedia(app, "captura"), "guarda captura en el Escritorio")
    reg("bloquear_pantalla", lambda: multimedia(app, "bloquear"), "bloquea la pantalla de Windows")

    # 2. Acciones con código (solo por Telegram)
    peligrosas = [
        (("apagar_laptop", "apagar_pc", "apagar_computadora"), "apagar", ["shutdown", "/s", "/t", "10", "/c", "Silvestra"], "Apagando la laptop en diez segundos."),
        (("reiniciar_laptop", "reiniciar_pc"), "reiniciar", ["shutdown", "/r", "/t", "10", "/c", "Silvestra"], "Reiniciando la laptop en diez segundos."),
        (("suspender_laptop", "suspender_pc"), "suspender", ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "Suspendiendo la laptop."),
        (("cerrar_sesion_laptop", "cerrar_sesion"), "cerrar_sesion", ["shutdown", "/l"], "Cerrando sesión de Windows."),
    ]
    for nombres, act, cmd, msg in peligrosas:
        fn = _registrar_peligrosa(app, act, cmd, msg)
        for n in nombres:
            reg(n, fn, f"{act} tras código por Telegram")

    print("[control_laptop] Acciones registradas correctamente.", flush=True)
