"""Puente compartido de capacidades locales para Gemini Live y el motor clásico.

Expone visión de pantalla, portapapeles, ventanas, procesos, HUD y multimedia
con APIs tolerantes a fallos. No toca widgets Qt ni escribe imágenes en disco.
"""
import threading
import unicodedata

_bloqueo = threading.RLock()
_catalogo = None
_supervisor = None


def _norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _contexto_gui():
    """Catálogo y supervisor mínimos para consultas GUI de solo lectura."""
    global _catalogo, _supervisor
    with _bloqueo:
        if _catalogo is None:
            from procesos_seguridad import CatalogoAppsAutorizadas
            _catalogo = CatalogoAppsAutorizadas()
        if _supervisor is None:
            from procesos_operaciones import SupervisorProcesosSilvestra
            _supervisor = SupervisorProcesosSilvestra()
        return _catalogo, _supervisor


def revisar_pantalla(pregunta: str = "") -> str:
    """Mira la pantalla y responde a la pregunta del usuario."""
    import vision_compartida
    return vision_compartida.revisar_pantalla(pregunta or vision_compartida.PREGUNTA_DEFECTO)


def leer_portapapeles(max_chars: int = 1800) -> str:
    """Devuelve el texto copiado, listo para que el modelo lo analice."""
    try:
        import portapapeles
        texto = portapapeles.leer_portapapeles(max_chars=max_chars)
    except Exception:
        texto = ""
    if not texto:
        return "No hay texto en el portapapeles. Copia algo con Control C y vuelve a pedírmelo."
    return f"El portapapeles contiene:\n{texto}"


def listar_ventanas(limite: int = 12) -> str:
    """Lista las ventanas visibles con título, marcando la que está activa."""
    try:
        import gui_ventanas
        catalogo, supervisor = _contexto_gui()
        datos = gui_ventanas.listar_ventanas({
            "_catalogo": catalogo,
            "_supervisor": supervisor,
            "limite": max(1, min(30, int(limite))),
        })
        ventanas = datos.get("ventanas", []) if isinstance(datos, dict) else []
    except Exception as exc:
        return f"No pude listar las ventanas: {exc}"
    titulos = []
    for ventana in ventanas:
        titulo = str((ventana or {}).get("titulo") or "").strip()
        if not titulo or ventana.get("protegida"):
            continue
        titulos.append(titulo + (" (activa)" if ventana.get("activa") else ""))
    if not titulos:
        return "No encontré ventanas visibles con título."
    return "Ventanas abiertas: " + "; ".join(titulos[:12]) + "."


def ventana_activa() -> str:
    """Devuelve el título de la ventana en primer plano."""
    try:
        import gui_ventanas
        catalogo, supervisor = _contexto_gui()
        datos = gui_ventanas.ventana_activa({
            "_catalogo": catalogo,
            "_supervisor": supervisor,
        })
    except Exception as exc:
        return f"No pude identificar la ventana activa: {exc}"
    titulo = str((datos or {}).get("titulo") or "").strip()
    if not titulo:
        return "No pude leer el título de la ventana activa (puede ser una app protegida)."
    return f"La ventana activa es: {titulo}."


def listar_procesos(nombre: str = "", limite: int = 12) -> str:
    """Lista procesos activos, opcionalmente filtrados por nombre."""
    try:
        import procesos_operaciones
        _, supervisor = _contexto_gui()
        datos = procesos_operaciones.consultar_procesos({
            "_supervisor": supervisor,
            "nombre": str(nombre or ""),
            "limite": max(1, min(40, int(limite))),
        })
        procesos = datos.get("procesos", []) if isinstance(datos, dict) else []
    except Exception as exc:
        return f"No pude consultar los procesos: {exc}"
    nombres, vistos = [], set()
    for proceso in procesos:
        actual = str((proceso or {}).get("nombre") or "").strip()
        if actual and actual.lower() not in vistos:
            vistos.add(actual.lower())
            nombres.append(actual)
    if not nombres:
        return "No encontré procesos activos con ese filtro."
    filtro = f" que coincidan con '{nombre}'" if str(nombre).strip() else ""
    return f"Procesos activos{filtro}: " + ", ".join(nombres[:12]) + "."


def activar_hud(app=None) -> str:
    """Activa el HUD remoto de la tablet y devuelve la dirección."""
    try:
        import pantalla_remota_accion
        return str(pantalla_remota_accion.activar_hud(app=app))
    except Exception as exc:
        return f"No pude activar el HUD: {exc}"


class _ColaMuda:
    def put(self, *args, **kwargs):
        return None


class _AppMuda:
    """Evita que control_laptop duplique la confirmación hablada."""

    cola = _ColaMuda()
    musica_activa = False


def _multimedia(orden: str, mensaje: str) -> str:
    try:
        import control_laptop
        control_laptop.multimedia(_AppMuda(), orden)
        return mensaje
    except Exception as exc:
        return f"No pude controlar la reproducción: {exc}"


def control_multimedia(orden: str) -> str:
    """Pausa, reanuda, adelanta o retrocede la reproducción actual."""
    o = _norm(orden)
    if any(k in o for k in ("pausa", "pausar", "deten la musica", "detener la musica")):
        return _multimedia("pausa", "Pausando o reanudando la reproducción.")
    if any(k in o for k in ("reanuda", "reanudar", "continua", "continuar")):
        return _multimedia("reanudar", "Reanudando la reproducción.")
    if any(k in o for k in ("siguiente", "pasa la cancion", "pasa la pista")):
        return _multimedia("siguiente", "Poniendo la siguiente canción.")
    if any(k in o for k in ("anterior", "cancion anterior", "pista anterior")):
        return _multimedia("anterior", "Volviendo a la canción anterior.")
    return "No entendí qué hacer con la reproducción."


def detectar_y_ejecutar(texto, app=None, incluir_portapapeles: bool = True):
    """Atajo por lenguaje natural compartido; devuelve texto o None si no aplica."""
    t = _norm(texto)
    if not t:
        return None
    try:
        import vision_pantalla
        if vision_pantalla.detectar_peticion_vision(texto):
            return revisar_pantalla(str(texto))
    except Exception:
        pass
    try:
        import pantalla_remota_accion
        if pantalla_remota_accion.detectar_orden_hud(texto):
            return activar_hud(app=app)
    except Exception:
        pass
    if incluir_portapapeles and any(
        k in t for k in ("portapapeles", "porta papeles", "lo que copie", "lo que copie")
    ):
        return leer_portapapeles()
    if any(k in t for k in ("ventana activa", "ventana en foco", "en que ventana estoy")):
        return ventana_activa()
    if any(k in t for k in (
        "ventanas abiertas", "ventanas tengo", "que ventanas",
        "tengo abierto", "tengo abiertas",
    )):
        return listar_ventanas()
    if any(k in t for k in (
        "procesos", "que esta corriendo", "programas corriendo", "esta corriendo",
    )):
        return listar_procesos()
    if any(k in t for k in (
        "pausa la musica", "pausar la musica", "reanuda la musica",
        "siguiente cancion", "cancion anterior", "pasa la cancion",
    )):
        return control_multimedia(texto)
    return None


__all__ = [
    "revisar_pantalla",
    "leer_portapapeles",
    "listar_ventanas",
    "ventana_activa",
    "listar_procesos",
    "activar_hud",
    "control_multimedia",
    "detectar_y_ejecutar",
]
