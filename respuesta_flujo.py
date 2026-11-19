"""Manejo de respuestas en streaming para Silvestra mediante la cadena de proveedores."""
from cerebro import separar
import proveedores


def responder_flujo(cerebro, texto, al_frase):
    """Genera la respuesta con streaming y conmutación automática de proveedores si hay fallos."""
    cerebro.historial.append({"role": "user", "content": texto})
    mensajes = [{"role": "system", "content": cerebro.instrucciones(texto)}] + cerebro.historial[-20:]

    crudo = proveedores.completar_flujo(mensajes, al_frase)

    respuesta, accion, recuerdo, emocion = separar(crudo)
    if recuerdo:
        cerebro.memoria.recordar(recuerdo)
    cerebro.historial.append({"role": "assistant", "content": respuesta})
    if hasattr(cerebro, "_podar_historial"):
        cerebro._podar_historial()
    try:
        import aprendizaje
        aprendizaje.registrar_interaccion(texto, respuesta, emocion)
    except Exception as e:
        print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)
    return respuesta, accion, emocion
