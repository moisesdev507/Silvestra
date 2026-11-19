"""Manejo de respuestas en streaming para Silvestra mediante la cadena de proveedores."""
from cerebro import separar
import proveedores
import proveedores_cadenas as pc


def responder_flujo(cerebro, texto, al_frase, on_primer_token=None):
    """Genera la respuesta con streaming y conmutación automática de proveedores si hay fallos."""
    cerebro.historial.append({"role": "user", "content": texto})
    # Limitar historial a los 8 turnos más recientes para ahorrar tokens y latencia
    mensajes = [{"role": "system", "content": cerebro.instrucciones(texto)}] + cerebro.historial[-8:]

    tarea = pc.clasificar_dificultad(texto)
    try:
        crudo = proveedores.completar_flujo(mensajes, al_frase, tarea=tarea, on_primer_token=on_primer_token)
    except Exception as e:
        print(f"[respuesta_flujo] Excepción en streaming: {e}. Usando respuesta local.", flush=True)
        try:
            al_frase(pc.FRASE_EMERGENCIA_LOCAL)
        except Exception:
            pass
        crudo = pc.respuesta_emergencia_local()

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
