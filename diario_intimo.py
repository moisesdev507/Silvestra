"""Fachada compartida del diario íntimo de Kaya para ambos motores.

Tanto Gemini Live como el motor clásico llaman a estas funciones: el usuario
aporta un tema, y Kaya redacta y guarda SIEMPRE en primera persona, sin copiar
su texto literal. No toca widgets Qt: devuelve frases para el canal de voz.
"""
import diario_helpers as dh

_VERBOS_LEER = ("leer", "lee", "muestra", "abre", "cual", "cuál")


def _contexto(app=None):
    """Contexto real y breve del día para que la reflexión tenga sentido."""
    try:
        import hilos
        import ideas
        memoria = getattr(app, "memoria", None)
        hechos = "; ".join(str(h) for h in getattr(memoria, "hechos", [])[-5:]) or "estudio y programación"
        hilos_txt = hilos.resumen() or "ninguno"
        ideas_txt = ideas.resumen() or "ninguna"
        historial = getattr(getattr(app, "cerebro", None), "historial", [])[-4:]
        charla = "\n".join(
            f"{m.get('role', '').upper()}: {m.get('content', '')}"
            for m in historial if m.get("content")
        )[-350:]
        return f"Hechos: {hechos}. Hilos: {hilos_txt}. Ideas: {ideas_txt}. Charla: {charla}"
    except Exception:
        return ""


def escribir(tema="", app=None):
    """Escribe una entrada íntima en primera persona y devuelve True si se guardó."""
    tema = dh.extraer_tema(tema)
    return dh.redactar_y_guardar(tema, _contexto(app))


def leer(app=None):
    """Devuelve la frase con la última entrada de Kaya."""
    ultima = dh.leer_ultima()
    if not ultima:
        return "Todavía no he escrito nada en mi diario. Al final del día anotaré mi primera entrada."
    return f"Te leo mi última entrada del diario: {ultima}"


def reflexionar(app=None):
    """Reflexión ligera de cierre si hubo interacción real y no se escribió hoy."""
    dia = None
    try:
        import diario
        dia = diario.obtener_instancia()
    except Exception:
        pass
    if dia is not None:
        return dia.reflexion_automatica()

    # Adaptador mudo de Gemini Live: misma disciplina sin instancia de Diario.
    import datetime
    try:
        import estado
        hoy = datetime.datetime.now().strftime("%Y-%m-%d")
        if str(estado.cargar().get("diario_ultima_fecha", "")) == hoy:
            return False
    except Exception:
        pass
    cerebro = getattr(app, "cerebro", None)
    historial = getattr(cerebro, "historial", []) or []
    turnos = sum(
        1 for m in historial
        if m.get("role") == "user" and str(m.get("content") or "").strip()
    )
    if turnos < 2:
        return False
    return dh.redactar_y_guardar("", _contexto(app))


def atender(texto, app=None):
    """Atiende una orden de diario en lenguaje natural: (respuesta, emoción) o None."""
    if not dh.es_orden_diario(texto):
        return None
    t = dh._normal(texto)
    if any(word in t for word in ("borra", "borrar")):
        try:
            import diario
            dia = diario.obtener_instancia()
            if dia is not None:
                dia.borrar_diario()
        except Exception:
            pass
        return "Listo, borré mi diario.", "neutral"
    if any(word in t for word in _VERBOS_LEER) and not any(
        word in t for word in dh.VERBOS_ESCRITURA
    ):
        return leer(app), "calida"
    ok = escribir(str(texto or ""), app)
    if ok:
        return "Ya lo anoté en mi diario, desde mi perspectiva.", "calida"
    return "No pude redactar mi entrada ahora mismo; lo intentaré más tarde.", "seria"


__all__ = ["escribir", "leer", "reflexionar", "atender"]
