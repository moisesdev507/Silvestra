"""Lo que Silvestra puede hacer en la laptop. SOLO lo que esté en esta lista."""
import subprocess
import urllib.parse
import webbrowser


def _programa(exe):
    return lambda arg=None: subprocess.Popen([exe])


def _web(url):
    return lambda arg=None: webbrowser.open(url)


def _buscar(arg):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(arg or ""))


def _youtube_buscar(arg):
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(arg or ""))


def _tecla(codigo):
    def f(arg=None):
        guion = f"(New-Object -ComObject WScript.Shell).SendKeys([char]{codigo})"
        for _ in range(5 if codigo != 173 else 1):
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", guion],
                creationflags=0x08000000,
            )
    return f


def _activar_hud(arg=None):
    import pantalla_remota_accion
    return pantalla_remota_accion.activar_hud(arg)


def _abrir_app_local(nombre):
    """Reutiliza control_laptop.abrir_app sin repetir la confirmación hablada."""
    import control_laptop

    class _ColaMuda:
        @staticmethod
        def put(_evento):
            pass

    class _AppMuda:
        cola = _ColaMuda()

    control_laptop.abrir_app(_AppMuda(), nombre)
    return True, ""


def _escribir_archivo(arg=None):
    import habilidades_archivos
    return habilidades_archivos.escribir_archivo(arg)


def _leer_archivo(arg=None):
    import habilidades_archivos
    return habilidades_archivos.leer_archivo(arg)


def _listar_archivos(arg=None):
    import habilidades_archivos
    return habilidades_archivos.listar_archivos(arg)


def _aprender_habilidad(arg=None):
    import aprendiz_habilidades
    return aprendiz_habilidades.aprender_habilidad(arg)


def _confirmar_habilidad(arg=None):
    import aprendiz_habilidades
    return aprendiz_habilidades.confirmar_habilidad(arg)


# nombre -> (función, necesita_texto, descripción para el cerebro)
ACCIONES = {
    "abrir_navegador": (_web("https://www.google.com"), False, "abre el navegador en Google"),
    "abrir_youtube": (_web("https://www.youtube.com"), False, "abre YouTube"),
    "abrir_gmail": (_web("https://mail.google.com"), False, "abre Gmail"),
    "abrir_whatsapp": (_web("https://web.whatsapp.com"), False, "abre WhatsApp Web"),
    "abrir_calculadora": (_programa("calc.exe"), False, "abre la calculadora"),
    "abrir_bloc_de_notas": (_programa("notepad.exe"), False, "abre el bloc de notas"),
    "abrir_explorador": (_programa("explorer.exe"), False, "abre el explorador de archivos"),
    "abrir_app_local": (_abrir_app_local, True, "abre una app permitida ya resuelta en local"),
    "buscar": (_buscar, True, "busca en Google lo que se le indique (lleva texto)"),
    "buscar_youtube": (_youtube_buscar, True, "busca videos en YouTube (lleva texto)"),
    "subir_volumen": (_tecla(175), False, "sube el volumen"),
    "bajar_volumen": (_tecla(174), False, "baja el volumen"),
    "silenciar": (_tecla(173), False, "silencia o reactiva el sonido"),
    "activar_hud": (_activar_hud, False, "activa el HUD de la tablet en red local y da el enlace"),
    "activar_pantalla_remota": (_activar_hud, False, "activa la pantalla remota en la tablet"),
    "activar_tablet": (_activar_hud, False, "conecta e inicia la pantalla de la tablet"),
    "abrir_hud": (_activar_hud, False, "abre e inicia el HUD de la tablet"),
    "escribir_archivo": (_escribir_archivo, True, "escribe contenido en un archivo. Obligatorio: ruta | texto completo redactado (ej: ACCION: escribir_archivo | archivo.txt | ideas o notas redactadas)"),
    "leer_archivo": (_leer_archivo, True, "lee un archivo de texto seguro autorizado"),
    "listar_archivos": (_listar_archivos, False, "lista los archivos existentes en el workspace de Lyris"),
    "aprender_habilidad": (_aprender_habilidad, True, "aprende una nueva habilidad programando código seguro"),
    "confirmar_habilidad": (_confirmar_habilidad, False, "aprueba y activa una habilidad aprendida pendiente"),
}

# Acciones especiales que maneja el programa principal (main.py).
ESPECIALES = {"descansar": "se despide y desaparece de la pantalla hasta que la llamen por su nombre"}
# Acciones "vivas": las registran otras partes del programa (la cara, la cámara...)
# para poder pedírselas por voz. nombre -> (función, descripción)
VIVAS = {}
CON_TEXTO = set()  # acciones vivas que reciben el texto que dijo el modelo


def registrar(nombre, funcion, descripcion, con_texto=False):
    VIVAS[nombre] = (funcion, descripcion)
    if con_texto:
        CON_TEXTO.add(nombre)


def describir():
    lineas = [f"- {n}: {d}" for n, (_, _, d) in ACCIONES.items()]
    lineas += [f"- {n}: {d}" for n, d in ESPECIALES.items()]
    lineas += [f"- {n}: {d}" for n, (_, d) in VIVAS.items()]
    return "\n".join(lineas)


def es_minimizar(texto):
    """Tolera erratas de Whisper: 'minimaliza/minimizar la ventana'."""
    import re
    import unicodedata
    norm = "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower())
                   if unicodedata.category(c) != "Mn")
    if re.search(r"\bno\s+(?:minimi|minimaliz)", norm):
        return False
    return bool(re.search("minim(?:i|ali)za", norm)
                and re.search("ventana|escritorio|pantalla|todo", norm))


# Variantes típicas de Whisper -> clave real de apps_permitidas.json (más largas primero).
_VARIANTES_APPS = tuple(sorted((
    ("visual estilo code", "visual studio code"),
    ("visual studio code", "visual studio code"),
    ("explorador de archivos", "explorador"),
    ("microsoft edge", "edge"),
    ("google chrome", "chrome"),
    ("studio code", "visual studio code"),
    ("visual code", "visual studio code"),
    ("bloc de notas", "bloc de notas"),
    ("vs code", "visual studio code"),
    ("calculadora", "calculadora"),
    ("explorador", "explorador"),
    ("spotify", "spotify"),
    ("notepad", "notepad"),
    ("vscode", "visual studio code"),
    ("chrome", "chrome"),
    ("edge", "edge"),
    ("notas", "notas"),
    ("calc", "calc"),
    ("powerpoint", "powerpoint"),
    ("excel", "excel"),
    ("word", "word"),
    ("code", "code"),
), key=lambda v: -len(v[0])))

_ABRIR_VERBOS = ("abre", "abrir", "abras", "abra", "abreme", "inicia", "iniciar",
                 "ejecuta", "ejecutar", "lanza", "lanzar", "arranca", "arrancar")

_CHARLA_APPS = (
    r"\bcomo\s+(?:abro|abre|abrir|uso|usar|se\s+usa|funciona|configuro|configurar|instalo|instalar|hago)\b",
    r"\bque\s+es\b", r"\bpara\s+que\s+(?:sirve|vale)\b", r"\bayudame\s+con\b",
    r"\bdime\s+(?:como|que|si)\b", r"\bexplicame\b", r"\bse\s+puede\s+abrir\b",
)


def extraer_app_abrir(texto):
    """Devuelve la app permitida si es una orden directa de abrirla; si no, None."""
    import re
    import unicodedata
    norm = "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower())
                   if unicodedata.category(c) != "Mn")
    if any(re.search(pat, norm) for pat in _CHARLA_APPS):
        return None
    verbo = None
    for pat in _ABRIR_VERBOS:
        m = re.search(r"\b" + pat + r"\b", norm)
        if m and (verbo is None or m.start() < verbo.start()):
            verbo = m
    if verbo is None or re.search(r"\bno\b", norm[:verbo.start()]):
        return None

    hallazgos = []
    for variante, canonico in _VARIANTES_APPS:
        for m in re.finditer(r"\b" + re.escape(variante) + r"\b", norm):
            hallazgos.append((m.start(), m.end(), canonico))
    if not hallazgos:
        return None
    utiles = []
    for ini, fin, canonico in hallazgos:
        if not any(ini >= oi and fin <= of and (of - oi) > (fin - ini)
                   for oi, of, _ in hallazgos):
            utiles.append(canonico)
    if len(set(utiles)) != 1:
        return None

    try:
        import control_laptop
        apps = control_laptop.cargar_apps()
        normalizar = control_laptop.normalizar
    except Exception:
        return None
    objetivo = normalizar(utiles[0])
    return next((k for k in apps if normalizar(k) == objetivo), None)


def interpretar(linea):
    """'buscar | recetas de arroz' -> ('buscar', 'recetas de arroz')."""
    if not linea:
        return None, None
    partes = linea.split("|", 1)
    nombre = partes[0].strip().lower().replace(" ", "_")
    arg = partes[1].strip() if len(partes) > 1 else None
    if nombre in ("ninguna", "ninguno", "nada", ""):
        return None, None
    if nombre in ("minimizar", "minimizar_ventanas", "minimizar_todas",
                  "minimizar_ventana_actual", "minimalizar_ventanas"):
        nombre = "minimizar_todo"
    return nombre, arg


def ejecutar(nombre, arg=None):
    """Devuelve (ok, mensaje). Ignora todo lo que no esté en la lista."""
    if nombre in VIVAS:
        try:
            if nombre in CON_TEXTO:
                ret = VIVAS[nombre][0](arg)
            else:
                ret = VIVAS[nombre][0]()
            if isinstance(ret, tuple) and len(ret) == 2:
                return ret
            if isinstance(ret, str):
                return True, ret
            return True, "Listo."
        except Exception as e:
            print(f"[acciones] Error ejecutando acción viva '{nombre}': {e}", flush=True)
            return False, f"Hubo un error al ejecutar {nombre}."
    if nombre not in ACCIONES:
        return False, "Eso todavía no sé hacerlo."
    funcion, necesita_texto, _ = ACCIONES[nombre]
    if necesita_texto and not arg:
        return False, "Falta el argumento para ejecutar la acción."
    try:
        ret = funcion(arg)
        if isinstance(ret, tuple) and len(ret) == 2:
            return ret
        if isinstance(ret, str):
            return True, ret
        return True, "Listo."
    except Exception as e:
        return False, "No pude hacerlo: " + str(e)[:100]