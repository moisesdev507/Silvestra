"""Modos y rutinas compuestas bajo demanda para Silvestra / Lyris.

Reutiliza modos_sistema (persistencia, volumen y VS Code) y control_pc (solo
lectura): no duplica el lanzamiento de apps ni el control de volumen. Cada paso
está aislado para que un fallo opcional no tumbe el resto. No toca widgets Qt
ni bloquea el hilo principal.
"""
import re
import unicodedata

# modo local -> (modo de modos_sistema, etiqueta, frase hablada)
CONFIG = {
    "codigo": ("programacion", "código",
               "Modo código activado. Abrí VS Code y voy directo al grano."),
    "estudio": ("estudio", "estudio",
                "Modo estudio activado. Entorno de lectura listo y respuestas paso a paso."),
    "descanso": ("noche", "descanso",
                 "Modo descanso activado. Bajé el volumen y bajo el ritmo."),
}

ALIAS = {k: k for k in CONFIG}
for _alias in ("programar", "programacion", "dev", "desarrollo"):
    ALIAS[_alias] = "codigo"
for _alias in ("estudiar", "enfoque", "concentracion", "pomodoro"):
    ALIAS[_alias] = "estudio"
for _alias in ("relax", "noche", "nocturno", "dormir"):
    ALIAS[_alias] = "descanso"

# Preguntas teóricas nunca activan un modo ("¿qué es el modo oscuro?").
_TEORIA = re.compile(r"\b(?:que es|que significa|define|explica|para que sirve|"
                     r"diferencia entre|teoria|como funciona)\b")
_MODO = re.compile(r"\bmodo\s+(?:de\s+|el\s+|la\s+)?([a-z]+)\b")

PASOS = {
    "codigo": ("activar", "editor"),
    "estudio": ("activar", "entorno"),
    "descanso": ("activar", "calma"),
}


def _paso_activar(ctx):
    """Delega en el motor de modos existente: estado, volumen y VS Code."""
    import modos_sistema
    ok, _msg, _cfg = modos_sistema.activar_modo(
        ctx["app"], ctx["sistema"], origen="voz_local")
    ctx["activado"] = bool(ok)
    return ok


def _paso_editor(ctx):
    """Solo consulta si Code está disponible; nunca lo lanza aquí."""
    import control_pc
    ctx["extra"] = (" VS Code listo." if control_pc.resolver_ruta_vscode()
                    else " No encontré VS Code, pero el modo ya está activo.")
    return True


def _paso_entorno(ctx):
    """Confirma el modo persistido para ajustar el mensaje, sin tocar la UI."""
    import modos_sistema
    if modos_sistema.obtener_modo_activo(ctx["app"]) == "estudio":
        ctx["extra"] = " Volumen atenuado y solo el dueño."
    return True


def _paso_calma(ctx):
    ctx["extra"] = " Volumen bajo y tono tranquilo."
    return True


_OPERACIONES = {
    "activar": _paso_activar,
    "editor": _paso_editor,
    "entorno": _paso_entorno,
    "calma": _paso_calma,
}


def detectar_modo(texto):
    """Devuelve 'codigo', 'estudio' o 'descanso' solo ante una orden de modo."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower())
                if unicodedata.category(c) != "Mn")
    if not t or _TEORIA.search(t):
        return None
    for m in _MODO.finditer(t):
        if m.group(1) in ALIAS:
            return ALIAS[m.group(1)]
    return None


def detectar_y_ejecutar_modo(texto, app=None):
    """Ejecuta la rutina del modo en local; devuelve una frase corta o None."""
    modo = detectar_modo(texto)
    if not modo:
        return None
    sistema, etiqueta, frase = CONFIG[modo]
    ctx = {"app": app, "sistema": sistema, "extra": "", "activado": False}
    for nombre in PASOS[modo]:
        try:
            _OPERACIONES[nombre](ctx)
        except Exception as e:
            print(f"[modos_rutina] paso '{nombre}' omitido: {e}", flush=True)
    if not ctx["activado"]:
        return f"No pude activar el modo {etiqueta} por completo, pero sigo aquí."
    return frase + ctx["extra"]
