"""Planificador cognitivo multi-paso y auto-crítica para Lyris."""
import re
import threading

import acciones

_bloqueo = threading.RLock()
MAX_PASOS = 3


def sanear_nombre_archivo(nom):
    """Normaliza nombres y extensiones de archivos mal transcritos por Whisper."""
    if not nom:
        return "archivo.txt"
    n = str(nom).strip().strip("'\"")
    # Corregir extensiones mal capturadas
    n = re.sub(r"\.(?:tgit|tequisde|tequiste|txtt|t\s*x\s*t)$", ".txt", n, flags=re.I)
    n = n.replace(" ", "_")
    if "." not in n:
        n += ".txt"
    return n.lower()


def generar_contenido_archivo(instruccion):
    """Genera contenido real estructurado mediante LLM rápido o fallback robusto."""
    if not instruccion or len(instruccion.strip()) < 3:
        return "Contenido generado para la tarea solicitada."
    inst_limpia = instruccion.strip()
    try:
        import proveedores
        prompt = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente técnico conciso. Redacta directamente el texto solicitado para guardar en un archivo. "
                    "Sin introducciones, sin saludos, sin explicaciones ni bloques de markdown vacíos. Solo el contenido útil."
                ),
            },
            {"role": "user", "content": f"Escribe el contenido para: {inst_limpia}"},
        ]
        res = proveedores.completar(prompt, max_tokens=350)
        if res and len(res.strip()) > 15:
            return res.strip()
    except Exception:
        pass

    # Fallback determinista limpio
    return f"# {inst_limpia.capitalize()}\n1. Tarea prioritaria inicial\n2. Desarrollo y pruebas unitarias\n3. Revisión y entrega"


def detectar_intencion_multipaso(texto):
    """Detecta si la petición contiene múltiples acciones encadenadas (tolerante a Whisper)."""
    if not texto or len(str(texto).strip()) < 8:
        return False
    t = str(texto).strip().lower()

    verbos_archivo = r"(?:crea|llea|lea|escribe|guarda|haz)\s+(?:un\s+)?(?:archivo\s+)?(?:llamado\s+|nombrado\s+)?[a-zA-Z0-9_\-\.]+"
    verbos_recordatorio = r"(?:recuerda(?:me)?|recuérdame|avisame|avísame|alarma|pon(?:\s+un)?\s+recordatorio)"
    if re.search(verbos_archivo, t, re.I) and re.search(verbos_recordatorio, t, re.I):
        return True

    conectores_gral = [
        r"\by\s+(?:luego|despues|después|ademas|además)\b",
        r"\b(?:busca|busca_youtube)\b.*\by\s+(?:guarda|escribe|anota)\b",
        r"\b(?:activa(?:\s+el)?\s+hud|abrir_hud)\b.*\by\s+(?:activa_modo|modo)\b",
    ]
    for patron in conectores_gral:
        if re.search(patron, t, re.I):
            return True
    return False


def descomponer_en_pasos(texto):
    """Descompone una petición compleja en hasta MAX_PASOS subtareas ejecutables."""
    t = str(texto).strip()
    pasos = []

    # 1. Caso: Crear/escribir archivo + Recordatorio (tolerante a Whisper: crea, llea, lea, etc.)
    m_arch_rec = re.search(
        r"(?:crea|llea|lea|escribe|guarda|haz)\s+(?:un\s+)?(?:archivo\s+)?(?:llamado\s+|nombrado\s+)?([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?)\s+(?:con\s+)?(.*?)\s+y\s+(?:recuerda(?:me)?|recuérdame|avisame|avísame|pon(?:\s+un)?\s+recordatorio|alarma)\s+(.*)",
        t,
        re.I,
    )
    if m_arch_rec:
        archivo_raw = m_arch_rec.group(1).strip()
        archivo = sanear_nombre_archivo(archivo_raw)
        desc_contenido = m_arch_rec.group(2).strip() or f"Notas para {archivo}"
        orden_rec = m_arch_rec.group(3).strip()

        # Generar contenido real para el archivo
        contenido_real = generar_contenido_archivo(desc_contenido)

        # Extraer únicamente la cláusula limpia del recordatorio
        tiempo_limpio = "en 5 minutos"
        que_limpio = f"revisar {archivo}"
        m_tiempo = re.search(
            r"(?:en\s+(?:\d+|un|una|uno|medio|media|dos|tres|cinco|diez|quince|veinte|treinta)\s*(?:minutos?|mins?|segundos?|segs?|horas?|h\b)|mañana(?:\s+a\s+las\s+\d+)?|a\s+las\s+\d+)",
            orden_rec,
            re.I,
        )
        if m_tiempo:
            tiempo_limpio = m_tiempo.group(0).strip()
            resto_rec = (orden_rec[:m_tiempo.start()] + " " + orden_rec[m_tiempo.end():]).strip()
            resto_rec = re.sub(r"\b(avísame|avisame|recuérdame|recuerdame|que|de|para|sobre|por\s+favor)\b", "", resto_rec, flags=re.I).strip()
            if resto_rec:
                que_limpio = resto_rec
        elif orden_rec:
            que_limpio = orden_rec

        pasos.append(("escribir_archivo", f"{archivo} | {contenido_real}"))
        pasos.append(("poner_recordatorio", f"{tiempo_limpio} | {que_limpio}"))
        return pasos[:MAX_PASOS]

    # 2. Caso: Separación por conectores explícitos
    fragmentos = re.split(r"\s+y\s+(?:luego|despues|después|ademas|además)\s+|\s*&&\s*", t, flags=re.I)
    if len(fragmentos) > 1:
        for frag in fragmentos[:MAX_PASOS]:
            frag_limpio = frag.strip()
            if not frag_limpio:
                continue
            if re.search(r"\b(?:crea|llea|lea|escribe|guardar?)\b.*\b(?:archivo|txt|py|md)\b", frag_limpio, re.I):
                m_a = re.search(r"([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?)", frag_limpio)
                nom_a = sanear_nombre_archivo(m_a.group(1)) if m_a else "nota.txt"
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
    with _bloqueo:
        for i, (nom_accion, arg) in enumerate(pasos, 1):
            if nom_accion in ("poner_recordatorio", "recordar"):
                try:
                    import recordatorios
                    rec_mgr = getattr(app, "recordatorios", None)
                    if not rec_mgr:
                        rec_mgr = recordatorios.Recordatorios(app)
                    res = rec_mgr.poner_recordatorio(arg)
                    resultados.append((nom_accion, True, res))
                    continue
                except Exception as e:
                    resultados.append((nom_accion, False, f"Error en recordatorio: {e}"))
                    break

            if nom_accion not in acciones.ACCIONES and nom_accion not in acciones.VIVAS:
                resultados.append((nom_accion, False, f"Acción '{nom_accion}' no reconocida."))
                break

            try:
                ok, mensaje = acciones.ejecutar(nom_accion, arg)
                resultados.append((nom_accion, ok, mensaje))
                if ok and nom_accion == "escribir_archivo" and arg:
                    try:
                        import cerebro_trabajo
                        cerebro_trabajo.actualizar_archivo(arg.split("|")[0].strip())
                    except Exception:
                        pass
                if not ok:
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
                # Extraer nombre guardado del mensaje si está disponible
                m_nom = re.search(r"'([^']+)'", msg or "")
                nom = m_nom.group(1) if m_nom else "el archivo"
                detalles.append(f"guardé '{nom}' con su contenido")
            elif accion == "poner_recordatorio":
                detalles.append("programé tu recordatorio")
            elif accion in ("activar_hud", "abrir_hud"):
                detalles.append("activé el HUD en la tablet")
            elif accion == "activar_modo":
                detalles.append("cambié el modo del sistema")
            else:
                detalles.append(f"completé {accion}")
        return f"Listo. {', y '.join(detalles)} con éxito."

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
