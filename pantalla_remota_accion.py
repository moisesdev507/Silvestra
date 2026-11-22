"""Acción para activar el HUD remoto de la tablet en LAN y detección rápida por voz."""
import os
import re
import unicodedata

_app_ref = None
_gestor_ref = None


def fijar_app(app, gestor=None):
    global _app_ref, _gestor_ref
    if app:
        _app_ref = app
    if gestor:
        _gestor_ref = gestor


def fijar_gestor(gestor):
    global _gestor_ref
    if gestor:
        _gestor_ref = gestor


def obtener_app():
    global _app_ref
    return _app_ref


def obtener_gestor():
    global _gestor_ref
    return _gestor_ref


def activar_hud(arg=None, app=None, hablar_cola=False):
    """Inicia el servidor HUD en red local HTTPS y devuelve la URL para la tablet."""
    ap = app or obtener_app()
    gestor = getattr(ap, "pantalla_remota", None) or obtener_gestor()

    if gestor is None:
        return "No pude conectar con el gestor de pantalla remota."

    # Si el servidor no está corriendo, levantarlo en LAN con TLS si hay certificados
    if getattr(gestor, "_servidor", None) is None:
        cert_ok = os.path.exists("hud_cert.pem") and os.path.exists("hud_key.pem")
        if cert_ok:
            gestor.activar_red_tls("hud_cert.pem", "hud_key.pem", "0.0.0.0")
        else:
            gestor.iniciar_servidor("0.0.0.0")

        gestor.activa = True
        try:
            import estado
            d = estado.cargar()
            d["remota_activa"] = True
            estado.guardar(d)
        except Exception:
            pass

    url = gestor.obtener_url_completa()

    if ap and hasattr(ap, "cola") and ap.cola:
        try:
            ap.cola.put(("copiar_portapapeles", url))
        except Exception:
            pass

    try:
        gestor.registrar_evento("HUD activado por voz")
    except Exception:
        pass

    msg = f"Listo, el HUD ya está activo en tu tablet. Puedes abrir {url}"
    if hablar_cola and ap and hasattr(ap, "cola") and ap.cola:
        try:
            ap.cola.put(("hablar", msg))
        except Exception:
            pass

    return msg


def registrar_acciones_hud(app, gestor=None):
    """Registra la acción activar_hud y sus alias en acciones.py."""
    fijar_app(app, gestor)
    import acciones

    desc = "activa el HUD de la tablet en la red local y entrega la dirección de acceso."
    for alias in ("activar_hud", "activar_pantalla_remota", "activar_tablet", "abrir_hud"):
        acciones.registrar(alias, lambda a=None: activar_hud(a, app, hablar_cola=True), desc)


def normalizar_texto(texto):
    """Limpia tildes y caracteres extraños para comparaciones fonéticas."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^\w\s]", " ", t)


def detectar_orden_hud(texto):
    """Detecta si el usuario está pidiendo encender o abrir el HUD o pantalla de la tablet."""
    if not texto or not isinstance(texto, str):
        return False

    t = normalizar_texto(texto)
    palabras = set(t.split())

    verbos = {
        "activa", "activar", "activame", "abre", "abrir", "abreme",
        "conecta", "conectar", "conectame", "inicia", "iniciar",
        "pon", "poner", "ponme", "muestra", "mostrar", "muestrame", "levantar", "levanta"
    }
    objetivos = {
        "hud", "had", "jud", "hvd", "ut", "tablet", "tabla", "notable", "remota"
    }

    if verbos.intersection(palabras) and objetivos.intersection(palabras):
        return True

    frases_directas = (
        "pantalla de la tablet", "pantalla remota", "pantalla notable", "pantalla tabla",
        "activar hud", "activa hud", "abrir hud", "abre hud", "conectar tablet", "conecta tablet",
        "activa la tablet", "activar la tablet", "abre la tablet", "abrir la tablet",
        "el hud en la tabla", "activa el hud", "abre el hud", "inicia el hud"
    )
    return any(f in t for f in frases_directas)
