"""Módulo auxiliar para telemetría y controles biométricos del HUD de la tablet."""
import os
import time

_cache = {
    "voz_mtime": 0.0,
    "voz_count": 0,
    "cara_mtime": 0.0,
    "cara_count": 0,
    "ultimo_reforzar": 0.0,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_VOZ = os.path.join(BASE_DIR, "voz_dueno.npy")
RUTA_CARA = os.path.join(BASE_DIR, "dueno.npy")


def contar_muestras_voz(app=None):
    """Cuenta las muestras del banco de voz (en memoria o caché por mtime)."""
    if app and hasattr(app, "voz_dueno") and getattr(app.voz_dueno, "banco_dueno", None) is not None:
        try:
            return len(app.voz_dueno.banco_dueno)
        except Exception:
            pass
    try:
        if not os.path.exists(RUTA_VOZ):
            return 0
        mt = os.path.getmtime(RUTA_VOZ)
        if mt != _cache["voz_mtime"]:
            import numpy as np
            banco = np.load(RUTA_VOZ)
            _cache["voz_mtime"] = mt
            _cache["voz_count"] = len(banco) if getattr(banco, "ndim", 1) == 2 else 1
        return _cache["voz_count"]
    except Exception:
        return 0


def contar_muestras_cara(app=None):
    """Cuenta las muestras del banco facial (en memoria o caché por mtime)."""
    if app and hasattr(app, "camara") and getattr(app.camara, "dueno", None) is not None:
        try:
            return len(app.camara.dueno)
        except Exception:
            pass
    try:
        if not os.path.exists(RUTA_CARA):
            return 0
        mt = os.path.getmtime(RUTA_CARA)
        if mt != _cache["cara_mtime"]:
            import numpy as np
            banco = np.load(RUTA_CARA)
            _cache["cara_mtime"] = mt
            _cache["cara_count"] = len(banco) if getattr(banco, "ndim", 1) == 2 else 1
        return _cache["cara_count"]
    except Exception:
        return 0


def obtener_estado_biometria(app):
    """Construye el snapshot de biometría en vivo para el HUD de la tablet."""
    import estado

    d_est = estado.cargar()
    solo_dueno = bool(
        getattr(getattr(app, "voz_dueno", None), "modo_solo_dueno", d_est.get("modo_solo_dueno", False))
    )

    vd = getattr(app, "voz_dueno", None)
    uv = getattr(vd, "ultima_verificacion", {}) if vd else {}
    umbral = float(getattr(vd, "umbral", d_est.get("umbral_voz_dueno", 0.45)))

    similitud = None
    if uv and uv.get("motivo") != "inicial" and "similitud" in uv and uv["similitud"] is not None:
        try:
            similitud = round(float(uv["similitud"]), 2)
        except Exception:
            similitud = None

    # Cámara
    cam = getattr(app, "camara", None)
    cam_activa = bool(cam and getattr(cam, "activa", False))
    cam_dueno = False
    if cam_activa:
        ult = getattr(cam, "ult_dueno", 0.0) or 0.0
        cam_dueno = bool(time.time() - ult < 6.0)

    # Identidad: 'dueno', 'invitado', 'espera'
    if uv and uv.get("motivo") not in (None, "", "inicial"):
        identidad = "dueno" if uv.get("es_dueno", False) else "invitado"
    elif cam_activa and cam_dueno:
        identidad = "dueno"
    else:
        identidad = "espera"

    return {
        "identidad": identidad,
        "solo_dueno": solo_dueno,
        "similitud_voz": similitud,
        "umbral_voz": umbral,
        "camara_activa": cam_activa,
        "camara_dueno": cam_dueno,
        "muestras_voz": contar_muestras_voz(app),
        "muestras_cara": contar_muestras_cara(app),
    }


def toggle_solo_dueno(app, activar=None):
    """Alterna o establece modo_solo_dueno de forma persistente sin interrumpir por voz."""
    import estado

    d = estado.cargar()
    actual = bool(d.get("modo_solo_dueno", False))
    nuevo = (not actual) if activar is None else bool(activar)
    d["modo_solo_dueno"] = nuevo
    estado.guardar(d)

    if hasattr(app, "voz_dueno") and app.voz_dueno:
        app.voz_dueno.modo_solo_dueno = nuevo

    print(f"[tablet] solo_dueno={nuevo}", flush=True)
    return obtener_estado_biometria(app)


def disparar_reforzar_voz(app):
    """Encola 'reforzar_mi_voz' al bucle principal de Qt con anti-doble toque."""
    ahora = time.time()
    if ahora - _cache["ultimo_reforzar"] < 3.0:
        return False, "Espera unos segundos antes de solicitar otro refuerzo.", obtener_estado_biometria(app)

    _cache["ultimo_reforzar"] = ahora
    try:
        app.cola.put(("ejecutar_accion", "reforzar_mi_voz"))
        print("[tablet] Solicitud de refuerzo de voz encolada a app.cola", flush=True)
        return True, "Refuerzo de voz solicitado con éxito.", obtener_estado_biometria(app)
    except Exception as e:
        return False, f"Error al encolar refuerzo: {e}", obtener_estado_biometria(app)
