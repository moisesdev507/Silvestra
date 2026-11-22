"""Planificador cognitivo multi-paso y auto-crítica para Lyris."""
import re
import threading

import acciones

_bloqueo = threading.RLock()
MAX_PASOS = 3


def detectar_intencion_multipaso(texto):
    """Detecta si la petición del usuario contiene múltiples acciones encadenadas."""
    if not texto or len(str(texto).strip()) < 10:
        return False
    t = str(texto).strip().lower()

    # Marcadores de encadenamiento
    conectores = [
        r"\by\s+(?:luego|despues|después|ademas|además)\b",
        r"\b(?:crea|escribe|guarda)\b.*\b(?:archivo|nota|texto)\b.*\by\s+(?:recuerda(?:me)?|avisame|avísame|alarma|pon(?:\s+un)?\s+recordatorio)\b",
        r"\b(?:busca|busca_youtube)\b.*\by\s+(?:guarda|escribe|anota)\b",
        r"\b(?:activa(?:\s+el)?\s+hud|abrir_hud)\b.*\by\s+(?:activa_modo|modo)\b",
    ]
    for patron in conectores:
        if re.search(patron, t, re.I):
            return True
    return False


def descomponer_en_pasos(texto):
    """Descompone una petición compleja en hasta MAX_PASOS subtareas ejecutables."""
    t = str(texto).strip()
    pasos = []

    # 1. Caso: Crear/escribir archivo + Recordatorio
    m_arch_rec = re.search(
        r"(?:crea|escribe|guarda)\s+(?:el\s+)?(?:archivo\s+)?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)\s+(?:con\s+)?(.*?)\s+y\s+(?:recuerda(?:me)?|avisame|avísame|pon(?:\s+un)?\s+recordatorio)\s+(.*)",
        t,
        re.I,
    )
    if m_arch_rec:
        archivo = m_arch_rec.group(1).strip()
        contenido = m_arch_rec.group(2).strip() or f"Notas para {archivo}"
        orden_rec = m_arch_rec.group(3).strip()
        pasos.append(("escribir_archivo", f"{archivo} | {contenido}"))
        pasos.append(("poner_recordatorio", f"en {orden_rec}" if not orden_rec.startswith("en ") else orden_rec))
        return pasos[:MAX_PASOS]

    # 2. Caso: Separación por conectores explícitos
    fragmentos = re.split(r"\s+y\s+(?:luego|despues|después|ademas|además)\s+|\s*&&\s*", t, flags=re.I)
    if len(fragmentos) > 1:
        for frag in fragmentos[:MAX_PASOS]:
            frag_limpio = frag.strip()
            if not frag_limpio:
                continue
            # Detectar acción asociada a cada fragmento
            if re.search(r"\b(?:crea|escribe|guardar?)\b.*\b(?:archivo|txt|py|md)\b", frag_limpio, re.I):
                m_a = re.search(r"([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)", frag_limpio)
                nom_a = m_a.group(1) if m_a else "nota.txt"
                pasos.append(("escribir_archivo", f"{nom_a} | {frag_limpio}"))
            elif re.search(r"\b(?:recuerda|avisame|recordatorio|alarma)\b", frag_limpio, re.I):
                pasos.append(("poner_recordatorio", frag_limpio))
            elif re.search(r"\b(?:activar?|abrir?)\b.*\b(?:hud|tablet)\b", frag_limpio, re.I):
                pasos.append(("activar_hud", None))
            elif re.search(r"\b(?:modo)\s+(codigo|programacion|estudio|noche|normal)\b", frag_limpio, re.I):
                m_m = re.search(r"\b(?:modo)\s+([a-zA-Z]+)", frag_limpio, re.I)
                pasos.append(("activar_modo", m_m.group(1) if m_m else "normal"))

    return pasos[:MAX_PASOS]


def ejecutar_plan_multipaso(pasos, app=None):
    """Ejecuta secuencialmente los pasos verificando el resultado de cada uno."""
    resultados = []
    exitosos = 0

    with _bloqueo:
        for i, (nom_accion, arg) in enumerate(pasos, 1):
            if nom_accion not in acciones.ACCIONES and nom_accion not in acciones.VIVAS:
                resultados.append((nom_accion, False, f"Acción '{nom_accion}' no reconocida."))
                break

            try:
                ok, mensaje = acciones.ejecutar(nom_accion, arg)
                resultados.append((nom_accion, ok, mensaje))
                if ok:
                    exitosos += 1
                else:
                    # Auto-crítica: si un paso indispensable falla, detener cadena para no desinformar
                    break
            except Exception as e:
                resultados.append((nom_accion, False, f"Excepción en paso {i}: {e}"))
                break

    return resultados


def verificar_coherencia_y_sintetizar(pasos, resultados):
    """Genera una respuesta hablada coherente evaluando los éxitos y fallos reales."""
    if not resultados:
        return "No pude ejecutar los pasos solicitados."

    total = len(pasos)
    n_ok = sum(1 for _, ok, _ in resultados if ok)

    if n_ok == total:
        detalles = []
        for accion, ok, msg in resultados:
            if accion == "escribir_archivo":
                detalles.append("guardé el archivo solicitado")
            elif accion == "poner_recordatorio":
                detalles.append("programé tu recordatorio")
            elif accion in ("activar_hud", "abrir_hud"):
                detalles.append("activé el HUD en la tablet")
            elif accion == "activar_modo":
                detalles.append("cambié el modo del sistema")
            else:
                detalles.append(f"completé {accion}")
        return f"Listo. {', '.join(detalles)} con éxito."

    # Si hubo fallo parcial o total
    fallidos = [f"en '{acc}': {msg}" for acc, ok, msg in resultados if not ok]
    if n_ok > 0:
        return f"Pude completar {n_ok} de {total} pasos, pero ocurrió un problema {'; '.join(fallidos)}."
    return f"No pude completar la solicitud porque falló {'; '.join(fallidos)}."


def procesar_turno_multipaso(cerebro, texto, al_frase=None):
    """Bucle completo planificar -> ejecutar -> verificar. Devuelve (atendido, respuesta, acciones)."""
    if not detectar_intencion_multipaso(texto):
        return False, "", []

    pasos = descomponer_en_pasos(texto)
    if not pasos or len(pasos) < 2:
        return False, "", []

    app = getattr(cerebro, "app", None)
    resultados = ejecutar_plan_multipaso(pasos, app=app)
    respuesta = verificar_coherencia_y_sintetizar(pasos, resultados)

    if callable(al_frase):
        al_frase(respuesta)

    cerebro.historial.append({"role": "user", "content": texto})
    cerebro.historial.append({"role": "assistant", "content": respuesta})
    if hasattr(cerebro, "_podar_historial"):
        cerebro._podar_historial()

    acciones_ejecutadas = [acc for acc, ok, _ in resultados if ok]
    return True, respuesta, acciones_ejecutadas
