"""Política única de ventana de historial para cerebro y respuesta_flujo."""
RAPIDO = {"mensajes": 8, "caracteres": 2400, "max_mensaje": 600}
PRO = {"mensajes": 16, "caracteres": 6000, "max_mensaje": 1000}


def _config(carril):
    return PRO if str(carril).lower() in ("pro", "profesional", "avanzado") else RAPIDO


def recortar(texto, maximo):
    """Recorta por palabras conservando la cola legible."""
    contenido = str(texto or "")
    maximo = max(1, int(maximo))
    if len(contenido) <= maximo:
        return contenido
    return contenido[:maximo].rsplit(" ", 1)[0].rstrip() + "..."


def podar(historial):
    """Mantiene la compatibilidad de cerebro: 10 si superaba 16 mensajes."""
    lista = list(historial or [])
    return lista[-10:] if len(lista) > 16 else lista


def ventana(historial, carril="rapido", presupuesto=None):
    """Selecciona los turnos más recientes que caben en el presupuesto real."""
    cfg = _config(carril)
    limite = cfg["caracteres"] if presupuesto is None else max(1, int(presupuesto))
    recientes = list(historial or [])[-cfg["mensajes"]:]
    elegidos, usado = [], 0
    for mensaje in reversed(recientes):
        contenido = recortar(mensaje.get("content", ""), cfg["max_mensaje"])
        coste = len(contenido) + 16  # envoltorio role/content estimado
        if usado + coste > limite and elegidos:
            break
        elegidos.append({"role": mensaje.get("role", "user"), "content": contenido})
        usado += coste
        if usado >= limite:
            break
    elegidos.reverse()
    return elegidos


def construir_ventana(historial, carril="rapido", instrucciones=None,
                      presupuesto=None):
    """Devuelve [system] + ventana; `instrucciones` ya incluye memoria/RAG."""
    mensajes = ventana(historial, carril, presupuesto)
    if instrucciones:
        mensajes = [{"role": "system", "content": str(instrucciones)}] + mensajes
    return mensajes
