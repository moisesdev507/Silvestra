"""Hilo conversacional compartido entre Gemini Live y Celeste."""
import memoria_contexto

REGLA_REFERENCIAS = (
    "[Conversación reciente en curso] Resuelve siempre 'eso', 'a qué te refieres', "
    "'lo anterior' y 'sígueme contando' con los turnos reales compartidos por "
    "Gemini Live y Celeste antes de responder. Si el hilo no basta, pregunta breve sin inventar."
)


def reflejar_turno(historial, papel, contenido):
    """Añade un turno de Live al historial de Celeste sin duplicar el último."""
    rol = "assistant" if papel == "kaya" else "user"
    if (historial and historial[-1].get("role") == rol
            and historial[-1].get("content") == contenido):
        return
    historial.append({"role": rol, "content": contenido})
    if len(historial) > 24:
        del historial[:-16]


def historial_podado(historial=None, max_turnos=12, max_chars=1400):
    """Historial de Celeste enriquecido con los turnos vivos de Gemini Live."""
    propio = [{"role": h.get("role"), "content": h.get("content", "")}
              for h in (historial or [])]
    try:
        compartido = memoria_contexto.historial_conversacion_activa(max_turnos, max_chars)
    except Exception:
        compartido = []
    if compartido:
        claves = {(h["role"], h["content"]) for h in compartido}
        base = [h for h in propio if (h.get("role"), h.get("content")) not in claves][-4:]
        combinados = (base + compartido)[-max_turnos:]
    else:
        combinados = propio[-max_turnos:]
    salida = [{"role": "system", "content": REGLA_REFERENCIAS}] if combinados else []
    usados = 0
    for h in combinados:
        c = str(h.get("content") or "")
        if h.get("role") == "assistant" and len(c) > 220:
            c = c[:220].rsplit(" ", 1)[0] + "..."
        if usados + len(c) > max_chars and len(salida) > 1:
            break
        usados += len(c)
        salida.append({"role": h.get("role"), "content": c})
    return salida


__all__ = ["REGLA_REFERENCIAS", "historial_podado"]
