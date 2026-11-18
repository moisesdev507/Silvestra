"""Gestión de correcciones del usuario y lecciones aprendidas para Silvestra.

Detecta cuando el creador la corrige ("así no", "te equivocaste", etc.), guarda
en correcciones.json (máx 50) y alimenta el prompt del cerebro con las lecciones
para no repetir errores. Todo en hilo secundario sin tocar Qt.
"""
import datetime
import json
import os
import re
import threading

import acciones

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CORRECCIONES = os.path.join(BASE, "correcciones.json")
MAX_CORRECCIONES = 50

_lock = threading.Lock()

PALABRAS_PRIVACIDAD = (
    "clave",
    "password",
    "contraseñ",
    "contrasena",
    "token",
    "api_key",
    "apikey",
    "secret",
    "gsk_",
    "sk-",
    "pin de acceso",
    "credencial",
)

PATRONES_CORRECCION = [
    r"\bno,?\s+eso\s+no\b",
    r"\bas[ií]\s+no\b",
    r"\bte\s+equivocaste\b",
    r"\bte\s+confundiste\b",
    r"\bno\s+era\s+eso\b",
    r"\bmejor\s+(haz|di|dime|pon|abre|busca|responde)\b",
    r"\bno\s+me\s+digas\b",
    r"\bno\s+hagas\s+eso\b",
    r"\bno\s+vuelvas\s+a\b",
    r"\bte\s+dije\s+que\s+no\b",
    r"\bno\s+es\s+eso\b",
    r"\beso\s+est[aá]\s+mal\b",
]


def contiene_datos_sensibles(texto):
    """True si el texto contiene términos o patrones de contraseñas, tokens o claves."""
    t = (texto or "").lower()
    return any(p in t for p in PALABRAS_PRIVACIDAD)


def es_correccion(texto):
    """Detecta si la frase del usuario representa una corrección directa a Silvestra."""
    if not texto:
        return False
    t = texto.strip().lower()
    for patron in PATRONES_CORRECCION:
        if re.search(patron, t):
            return True
    return False


def cargar_correcciones():
    """Lee correcciones.json de forma segura."""
    with _lock:
        if os.path.exists(ARCHIVO_CORRECCIONES):
            try:
                with open(ARCHIVO_CORRECCIONES, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    if isinstance(datos, list):
                        return datos
            except Exception as e:
                print(f"[correcciones] Error leyendo {ARCHIVO_CORRECCIONES}: {e}", flush=True)
        return []


def guardar_correcciones(lista):
    """Guarda en correcciones.json asegurando un máximo de 50 elementos (FIFO)."""
    with _lock:
        try:
            podada = lista[-MAX_CORRECCIONES:]
            with open(ARCHIVO_CORRECCIONES, "w", encoding="utf-8") as f:
                json.dump(podada, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[correcciones] Error guardando {ARCHIVO_CORRECCIONES}: {e}", flush=True)
            return False


def registrar_correccion(dijo_ella, pidio_usuario):
    """Registra una corrección descartando automáticamente datos sensibles."""
    if not pidio_usuario:
        return None

    if contiene_datos_sensibles(pidio_usuario) or contiene_datos_sensibles(dijo_ella):
        print("[correcciones] Descartada corrección por filtro de privacidad (claves/tokens).", flush=True)
        return None

    fecha_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lista = cargar_correcciones()

    # Evitar duplicados consecutivos idénticos
    if lista and lista[-1].get("pidio_usuario", "").strip().lower() == pidio_usuario.strip().lower():
        return lista[-1]

    nuevo_id = (lista[-1]["id"] + 1) if (lista and "id" in lista[-1]) else (len(lista) + 1)
    entrada = {
        "id": nuevo_id,
        "fecha": fecha_str,
        "dijo_ella": (dijo_ella or "").strip(),
        "pidio_usuario": pidio_usuario.strip(),
    }
    lista.append(entrada)
    guardar_correcciones(lista)
    print(f"[correcciones] Guardada corrección #{nuevo_id}: '{pidio_usuario[:50]}...'", flush=True)
    return entrada


def resumen_para_prompt(tema_actual=None):
    """Devuelve hasta 5 correcciones más relevantes o recientes para incluir en el prompt del sistema."""
    lista = cargar_correcciones()
    if not lista:
        return ""

    # Tomar las más relevantes según palabras compartidas o las 5 más recientes
    if tema_actual and len(lista) > 5:
        palabras_tema = set(re.findall(r"\w{4,}", tema_actual.lower()))
        def score(c):
            txt = f"{c.get('dijo_ella', '')} {c.get('pidio_usuario', '')}".lower()
            return sum(1 for p in palabras_tema if p in txt)
        seleccionadas = sorted(lista, key=score, reverse=True)[:5]
    else:
        seleccionadas = lista[-5:]

    lineas = ["Reglas aprendidas de correcciones previas de tu creador (OBLIGATORIO acatarlas para no repetir errores):"]
    for c in seleccionadas:
        ella = c.get("dijo_ella")
        pidio = c.get("pidio_usuario")
        if ella:
            lineas.append(f"- Cuando dijiste «{ella[:60]}...», él te corrigió: «{pidio}». Cumple su corrección.")
        else:
            lineas.append(f"- Corrección de tu creador: «{pidio}». Debes respetarla.")
    return "\n".join(lineas)


def accion_mis_correcciones(app):
    """Lee y muestra las correcciones guardadas."""
    def _tarea():
        lista = cargar_correcciones()
        if not lista:
            app.cola.put(("hablar", "No tengo ninguna corrección guardada todavía."))
            return

        total = len(lista)
        ultimas = lista[-5:]
        texto_voz = f"Tengo {total} correcciones guardadas. Las más recientes son: " + "; ".join(
            f"Número {c.get('id', i+1)}: {c.get('pidio_usuario')}" for i, c in enumerate(ultimas)
        )
        burbuja = f"📋 MIS CORRECCIONES ({total} en total):\n" + "\n".join(
            f"#{c.get('id', i+1)} [{c.get('fecha', '')}]: «{c.get('pidio_usuario')}»" for i, c in enumerate(ultimas)
        )
        app.cola.put(("hablar_registro", (texto_voz, burbuja)))

    threading.Thread(target=_tarea, daemon=True).start()


def accion_olvidar_correccion(app, arg):
    """Borra una corrección específica por su número."""
    def _tarea():
        if not arg:
            app.cola.put(("hablar", "Dime qué número de corrección deseas olvidar."))
            return

        m = re.search(r"\d+", str(arg))
        if not m:
            app.cola.put(("hablar", "No entendí el número de la corrección a olvidar."))
            return

        num = int(m.group(0))
        lista = cargar_correcciones()
        nueva_lista = [c for c in lista if c.get("id") != num]

        if len(nueva_lista) == len(lista):
            # Probar por posición 1..N
            if 1 <= num <= len(lista):
                eliminada = lista.pop(num - 1)
                guardar_correcciones(lista)
                print(f"[correcciones] Eliminada corrección por índice #{num}: {eliminada}", flush=True)
                app.cola.put(("hablar", f"Olvidé la corrección número {num}."))
                return
            app.cola.put(("hablar", f"No encontré ninguna corrección con el número {num}."))
            return

        guardar_correcciones(nueva_lista)
        print(f"[correcciones] Eliminada corrección id={num}.", flush=True)
        app.cola.put(("hablar", f"Olvidé la corrección número {num}."))

    threading.Thread(target=_tarea, daemon=True).start()


def instalar(app):
    """Instala el subsistema de correcciones y registra sus acciones."""
    app.correcciones = True

    acciones.registrar(
        "mis_correcciones",
        lambda: accion_mis_correcciones(app),
        "Lee o muestra las correcciones y lecciones que Moisés le ha enseñado a Silvestra.",
    )
    acciones.registrar(
        "olvidar_correccion",
        lambda arg: accion_olvidar_correccion(app, arg),
        "Olvida o elimina una corrección aprendida por su número. Lleva texto con el número.",
        con_texto=True,
    )
    print("[correcciones] Módulo de correcciones y lecciones instalado.", flush=True)
