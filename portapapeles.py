"""Copiloto de portapapeles bajo demanda: lectura segura y contexto puntual.

No abre ventanas, no toca widgets Qt y solo se activa cuando el usuario pide
explícitamente revisar lo que copió. Nunca inyecta el portapapeles en otros turnos.
"""
import re

SIN_TEXTO = ("No tengo nada de texto en el portapapeles. "
             "Cópialo con Control C y vuelve a decirme.")

_PLANTILLA = (
    "[PORTAPAPELES DEL USUARIO]\n{texto}\n[/PORTAPAPELES]\n"
    "Responde de forma hablada, breve y directa (1-3 frases) indicando la causa "
    "y cómo solucionarlo sin leer código línea por línea."
)

_ACCION = (r"(?:revisa|revisar|explica|explicar|corrige|corregir|resume|resumir|"
           r"traduce|traducir|analiza|analizar|mira|mirar|lee|leer|arregla|arreglar|"
           r"describe|describir)")
_OBJETO = (r"(?:copi[ée]|copiado|copiada|portapapeles|porta[\s_-]?papeles|"
           r"error|traceback|c[oó]digo|esto|lo que tengo)")
_PATRONES = (
    re.compile(rf"\b{_ACCION}\b[^.!?]{{0,60}}\b{_OBJETO}\b", re.I),
    re.compile(r"\bpor\s+qu[eé]\s+(?:falla|no\s+funciona|est[aá]\s+mal)\s+"
               r"(?:esto|el\s+c[oó]digo|lo\s+que\s+copi[eé])", re.I),
    re.compile(r"\bqu[eé]\s+dice\s+(?:el\s+)?"
               r"(?:portapapeles|copiado|lo\s+que\s+copi[eé])", re.I),
)


def pide_portapapeles(texto):
    """True solo ante una petición explícita de usar/revisar lo copiado."""
    t = " ".join(str(texto or "").split())
    if not t:
        return False
    return any(p.search(t) for p in _PATRONES)


def _leer_win32():
    """Lee CF_UNICODETEXT con Win32 puro; devuelve '' ante imagen/archivo o error."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(0):
            return ""
        try:
            if not user32.IsClipboardFormatAvailable(13):
                return ""
            handle = user32.GetClipboardData(13)
            if not handle:
                return ""
            puntero = kernel32.GlobalLock(handle)
            if not puntero:
                return ""
            try:
                return ctypes.wstring_at(puntero)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


def _limpiar(texto, max_chars):
    """Normaliza saltos, quita caracteres de control y recorta por palabra/línea."""
    t = str(texto or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    t = "".join(ch for ch in t if ch in "\n\t" or ord(ch) >= 32)
    t = "\n".join(linea.rstrip() for linea in t.split("\n"))
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    t = t.strip()
    if len(t) <= max_chars:
        return t
    sufijo = "\n…[recortado]"
    corte = t[:max(0, max_chars - len(sufijo))]
    borde = max(corte.rfind("\n"), corte.rfind(" "))
    if borde >= len(corte) // 2:
        corte = corte[:borde]
    return corte.rstrip() + sufijo


def leer_portapapeles(max_chars=2500):
    """Devuelve el texto del portapapeles limpio y recortado, o '' si no aplica."""
    try:
        return _limpiar(_leer_win32(), max(5, int(max_chars)))
    except Exception:
        return ""


def construir_contexto_portapapeles(texto_usuario):
    """Bloque compacto para este turno, SIN_TEXTO si no hay nada, o '' si no aplica."""
    if not pide_portapapeles(texto_usuario):
        return ""
    contenido = leer_portapapeles()
    if not contenido:
        return SIN_TEXTO
    return _PLANTILLA.format(texto=contenido)
