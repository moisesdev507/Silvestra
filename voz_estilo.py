"""Voz neuronal y estilo dinámico F.R.I.D.A.Y. / Her para Lyris.

Toda la configuración se lee de ``estado.json`` en cada síntesis, de modo que
los cambios del HUD se aplican en caliente sin reiniciar la aplicación.
"""
import estado

VOCES = {
    "es-CO-SalomeNeural": "Salomé (CO)",
    "es-ES-XimenaNeural": "Ximena (ES)",
    "es-PA-MargaritaNeural": "Margarita (PA)",
}
VOZ_DEFECTO = "es-CO-SalomeNeural"
VOZ_FALLBACK = "es-PA-MargaritaNeural"

ESTILOS = {
    "auto": "Automática (F.R.I.D.A.Y. / Her)",
    "friday": "F.R.I.D.A.Y.",
    "her": "Her",
}
ESTILO_DEFECTO = "auto"

# Cadencia ágil/ejecutiva frente a cercana/pausada.
FRIDAY = {"rate": "+2%", "pitch": "+1Hz"}
HER = {"rate": "-2%", "pitch": "-1Hz"}
CERCANAS = ("calida", "cercana", "tierna", "cariñosa", "afectuosa", "amable")


def _leer():
    try:
        return estado.cargar()
    except Exception:
        return {}


def normalizar_voz(valor):
    """Voz válida: vacío -> Salomé, desconocida -> Margarita."""
    voz = str(valor or "").strip()
    if not voz:
        return VOZ_DEFECTO
    return voz if voz in VOCES else VOZ_FALLBACK


def voz_actual():
    return normalizar_voz(_leer().get("voz_edge"))


def normalizar_estilo(valor):
    estilo = str(valor or "").strip().lower().replace("á", "a")
    return estilo if estilo in ESTILOS else ESTILO_DEFECTO


def estilo_actual():
    return normalizar_estilo(_leer().get("estilo_voz"))


def es_cercana(emocion):
    return str(emocion or "").strip().lower().replace("á", "a") in CERCANAS


def estilo_para(emocion, estilo=None):
    """En 'auto': Her si la emoción es cercana; F.R.I.D.A.Y. en el resto."""
    modo = estilo_actual() if estilo is None else normalizar_estilo(estilo)
    if modo == "auto":
        return "her" if es_cercana(emocion) else "friday"
    return modo


def ajustes(emocion, base=None):
    """Devuelve rate/pitch del estilo activo conservando el volumen emocional."""
    plantilla = HER if estilo_para(emocion) == "her" else FRIDAY
    return {
        "rate": plantilla["rate"],
        "pitch": plantilla["pitch"],
        "volume": (base or {}).get("volume", "+0%"),
    }


def guardar(voz=None, estilo=None):
    """Persiste voz/estilo e invalida el caché de audio."""
    datos = _leer()
    if voz is not None:
        datos["voz_edge"] = normalizar_voz(voz)
    if estilo is not None:
        datos["estilo_voz"] = normalizar_estilo(estilo)
    estado.guardar(datos)
    try:
        import voz_cache
        voz_cache.limpiar()
    except Exception:
        pass
    return voz_actual(), estilo_actual()
