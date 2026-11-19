"""Lógica de estado y endpoints HTTP para la Casa Virtual 2D de Silvestra."""
import json
import threading
import time

from casa_web_ui import PAGINA_CASA_HTML

_lock = threading.Lock()

FRASES_MOVER = {
    "Entrada": "Llegaste a la entrada, compa. Puerta asegurada.",
    "Sala": "Te moviste a la sala. Todo tranquilo por acá.",
    "Cocina": "Te moviste a la cocina. ¿Qué vas a preparar de rico?",
    "Cuarto": "Entraste al cuarto. Buen momento para descansar un rato.",
}

FRASES_ANILLO = {
    "Entrada": "¡Toque de anillo en la entrada! Te copio clarito.",
    "Sala": "¡Sentí el toque del anillo en la sala! Dime qué necesitas.",
    "Cocina": "¡Toque de anillo en la cocina! Estoy atenta a lo que pidas.",
    "Cuarto": "¡Toque de anillo en el cuarto! Dime qué pasó, aquí estoy.",
}


class EstadoCasaWeb:
    """Controla el estado persistente y cooldown de la casa virtual."""

    def __init__(self, app=None):
        self.app = app
        self.cuarto_actual = "Sala"
        self.luces = {
            "Sala": True,
            "Cocina": False,
            "Entrada": False,
            "Cuarto": False,
        }
        self.ultimo_evento_ts = 0.0
        self.cooldown_seg = 3.0

    def procesar_evento(self, tipo, cuarto):
        """Procesa un evento de mover, anillo o luz respetando el cooldown y voz."""
        with _lock:
            cuarto_norm = str(cuarto).strip().capitalize() if cuarto else "Sala"
            if cuarto_norm not in self.luces:
                cuarto_norm = "Sala"

            if tipo == "mover":
                self.cuarto_actual = cuarto_norm
            elif tipo == "luz":
                self.luces[cuarto_norm] = not self.luces.get(cuarto_norm, False)

            ahora = time.time()
            hablando = False
            voz = getattr(self.app, "voz", None) if self.app else None
            if voz and hasattr(voz, "ocupada"):
                try:
                    hablando = voz.ocupada()
                except Exception:
                    hablando = False

            en_cooldown = (ahora - self.ultimo_evento_ts) < self.cooldown_seg
            debe_hablar = not hablando and not en_cooldown
            frase = ""

            if debe_hablar:
                self.ultimo_evento_ts = ahora
                if tipo == "mover":
                    frase = FRASES_MOVER.get(cuarto_norm, f"Estás en la {cuarto_norm.lower()}.")
                elif tipo == "anillo":
                    frase = FRASES_ANILLO.get(cuarto_norm, "¡Sentí el toque del anillo! Estoy atenta.")
                elif tipo == "luz":
                    on = self.luces.get(cuarto_norm, False)
                    estado_txt = "encendida" if on else "apagada"
                    frase = f"Luz de la {cuarto_norm.lower()} {estado_txt}."

                if frase and self.app and hasattr(self.app, "cola"):
                    self.app.cola.put(("hablar", frase))

            # Notificar cambio a la interfaz Qt de casa.py si aplica
            if self.app and hasattr(self.app, "cola"):
                self.app.cola.put(("casa_evento", {
                    "tipo": tipo,
                    "cuarto": cuarto_norm,
                    "luces": dict(self.luces),
                }))

            return {
                "ok": True,
                "cuarto": self.cuarto_actual,
                "luces": self.luces,
                "hablo": bool(frase),
                "frase": frase,
                "cooldown": en_cooldown,
            }

    def obtener_estado(self):
        """Devuelve el estado actual para sincronización inicial."""
        with _lock:
            return {
                "ok": True,
                "cuarto": self.cuarto_actual,
                "luces": self.luces,
                "frase": f"En la {self.cuarto_actual.lower()}.",
            }


_instancia_casa_web = None


def obtener_gestor_casa(app=None):
    """Devuelve la instancia singleton del gestor de casa web."""
    global _instancia_casa_web
    with _lock:
        if _instancia_casa_web is None:
            _instancia_casa_web = EstadoCasaWeb(app)
        elif app is not None and _instancia_casa_web.app is None:
            _instancia_casa_web.app = app
        return _instancia_casa_web


def manejar_get(handler, url_parsed):
    """Maneja las rutas GET /casa y /api/casa/estado. Devuelve True si procesó."""
    path = url_parsed.path
    if path == "/casa":
        contenido = PAGINA_CASA_HTML.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(contenido)))
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        handler.wfile.write(contenido)
        return True

    if path == "/api/casa/estado":
        app = getattr(getattr(handler, "server", None), "gestor", None)
        app_ref = getattr(app, "app", None) if app else None
        gestor = obtener_gestor_casa(app_ref)
        datos = gestor.obtener_estado()
        payload = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(payload)
        return True

    return False


def manejar_post(handler, url_parsed):
    """Maneja el endpoint POST /api/casa/evento. Devuelve True si procesó."""
    if url_parsed.path != "/api/casa/evento":
        return False

    try:
        longitud = int(handler.headers.get("Content-Length", 0))
        cuerpo = handler.rfile.read(longitud).decode("utf-8") if longitud > 0 else "{}"
        params = json.loads(cuerpo) if cuerpo else {}
    except Exception:
        params = {}

    tipo = params.get("tipo", "mover")
    cuarto = params.get("cuarto", "Sala")

    app = getattr(getattr(handler, "server", None), "gestor", None)
    app_ref = getattr(app, "app", None) if app else None
    gestor = obtener_gestor_casa(app_ref)
    resultado = gestor.procesar_evento(tipo, cuarto)

    payload = json.dumps(resultado, ensure_ascii=False).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)
    return True
