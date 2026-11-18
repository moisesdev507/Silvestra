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


# nombre -> (función, necesita_texto, descripción para el cerebro)
ACCIONES = {
    "abrir_navegador": (_web("https://www.google.com"), False, "abre el navegador en Google"),
    "abrir_youtube": (_web("https://www.youtube.com"), False, "abre YouTube"),
    "abrir_gmail": (_web("https://mail.google.com"), False, "abre Gmail"),
    "abrir_whatsapp": (_web("https://web.whatsapp.com"), False, "abre WhatsApp Web"),
    "abrir_calculadora": (_programa("calc.exe"), False, "abre la calculadora"),
    "abrir_bloc_de_notas": (_programa("notepad.exe"), False, "abre el bloc de notas"),
    "abrir_explorador": (_programa("explorer.exe"), False, "abre el explorador de archivos"),
    "buscar": (_buscar, True, "busca en Google lo que se le indique (lleva texto)"),
    "buscar_youtube": (_youtube_buscar, True, "busca videos en YouTube (lleva texto)"),
    "subir_volumen": (_tecla(175), False, "sube el volumen"),
    "bajar_volumen": (_tecla(174), False, "baja el volumen"),
    "silenciar": (_tecla(173), False, "silencia o reactiva el sonido"),
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


def interpretar(linea):
    """'buscar | recetas de arroz' -> ('buscar', 'recetas de arroz')."""
    if not linea:
        return None, None
    partes = linea.split("|", 1)
    nombre = partes[0].strip().lower().replace(" ", "_")
    arg = partes[1].strip() if len(partes) > 1 else None
    if nombre in ("ninguna", "ninguno", "nada", ""):
        return None, None
    return nombre, arg


def ejecutar(nombre, arg=None):
    """Devuelve (ok, mensaje). Ignora todo lo que no esté en la lista."""
    if nombre in VIVAS:
        if nombre in CON_TEXTO:
            VIVAS[nombre][0](arg)
        else:
            VIVAS[nombre][0]()
        return True, "Listo."
    if nombre not in ACCIONES:
        return False, "Eso todavía no sé hacerlo."
    funcion, necesita_texto, _ = ACCIONES[nombre]
    if necesita_texto and not arg:
        return False, "No me dijiste qué buscar."
    try:
        funcion(arg)
        return True, "Listo."
    except Exception as e:
        return False, "No pude hacerlo: " + str(e)[:100]