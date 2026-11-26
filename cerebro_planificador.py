"""Planificador cognitivo multi-paso y auto-crítica para Lyris.

Reutiliza el bus de herramientas y el cerebro único; el parseo heredado vive
en ``cerebro_planificador_base.py`` para no exceder 10 KB.
"""
import re
import threading

import acciones
from cerebro_planificador_base import (
    detectar_intencion_multipaso, generar_contenido_archivo,
    pasos_legacy, sanear_nombre_archivo,
)

_bloqueo = threading.RLock()
MAX_PASOS = 5


def _clasificar(frag):
    """Clasifica un fragmento en una acción cognitiva segura y verificable."""
    f = frag.strip()
    if re.search(r"https?://|www\.|youtube|resum(?:e|ir)\s+(?:el\s+)?(?:link|enlace|video)", f, re.I):
        return "resumir_enlace_o_video", f
    if re.search(r"pantalla|ventana|mirar|mirá|describe lo que ves|error en pantalla", f, re.I):
        return "revisar_pantalla", f
    if re.search(r"internet|web|busca en google|noticias|documentación|documentacion", f, re.I):
        return "herramienta_permitida", f"buscar_web|{f}"
    return "consultar_conocimiento_local", f


def descomponer_en_pasos(objetivo, contexto=""):
    """Divide un objetivo compuesto en 2-5 pasos atómicos y verificables."""
    t = str(objetivo or "").strip()
    if not t:
        return []
    legacy = pasos_legacy(t.lower() if detectar_intencion_multipaso(t) else t)
    if legacy:
        return legacy[:MAX_PASOS]
    texto = f"{t} {str(contexto or '').strip()}".strip()
    trozos = [x.strip() for x in re.split(
        r"\s+(?:y|luego|después|despues|además|ademas)\s+|\s*;\s*|\s*&&\s*",
        texto, flags=re.I) if x.strip()]
    pasos, vistos = [], set()
    for frag in trozos[:MAX_PASOS - 1]:
        accion, arg = _clasificar(frag)
        if (accion, arg) in vistos:
            continue
        vistos.add((accion, arg))
        pasos.append((accion, arg))
    if len(pasos) == 1:
        pasos.insert(0, ("contexto_unico", t))
    if pasos:
        pasos.append(("resumen", f"Integra los resultados y responde: {t}"))
    return pasos[:MAX_PASOS]


def _ejecutar_cognitivo(accion, arg, app):
    """Ejecuta pasos cognitivos reutilizando motores existentes; None si no aplica."""
    if accion == "consultar_conocimiento_local":
        import herramientas_cerebro
        return True, herramientas_cerebro.consultar_conocimiento_local(arg)
    if accion == "resumir_enlace_o_video":
        import herramientas_cerebro
        return True, herramientas_cerebro.resumir_enlace_o_video(arg)
    if accion == "revisar_pantalla":
        import capacidades_extra
        return True, str(capacidades_extra.revisar_pantalla(str(arg or "")))[:1200]
    if accion == "contexto_unico":
        import cerebro_unico
        return True, cerebro_unico.compilar_contexto_unico(str(arg or ""), max_chars=900, estable=True)
    if accion == "resumen":
        return True, str(arg or "Resumen listo.")
    if accion == "herramienta_permitida":
        import agente_herramientas
        nom, _, valor = str(arg or "").partition("|")
        if nom.strip() not in agente_herramientas.CATALOGO:
            return False, f"Herramienta '{nom.strip()}' no permitida."
        return True, agente_herramientas.ejecutar(nom.strip(), valor.strip())
    return None


def ejecutar_plan_multipaso(pasos, app=None):
    """Ejecuta los pasos en secuencia; un fallo no cancela los siguientes."""
    resultados = []
    with _bloqueo:
        for i, paso in enumerate(pasos, 1):
            if isinstance(paso, dict):
                nom_accion = str(paso.get("accion", "")).strip()
                arg = paso.get("arg", "")
            elif isinstance(paso, (tuple, list)) and paso:
                nom_accion = str(paso[0]).strip()
                arg = paso[1] if len(paso) > 1 else None
            else:
                resultados.append(("paso", False, "Paso no válido"))
                continue
            try:
                resultado = _ejecutar_cognitivo(nom_accion, arg, app)
                if resultado is not None:
                    ok, mensaje = resultado
                    resultados.append((nom_accion, bool(ok), str(mensaje or "")[:1200]))
                    continue
            except Exception as exc:
                resultados.append((nom_accion, False, f"Excepción en paso {i}: {type(exc).__name__}"))
                continue
            if nom_accion in ("poner_recordatorio", "recordar"):
                try:
                    import recordatorios
                    gestor = getattr(app, "recordatorios", None)
                    if not gestor:
                        gestor = recordatorios.Recordatorios(app)
                    resultados.append((nom_accion, True, gestor.poner_recordatorio(arg)))
                except Exception as exc:
                    resultados.append((nom_accion, False, f"Error en recordatorio: {exc}"))
                continue
            if nom_accion not in acciones.ACCIONES and nom_accion not in acciones.VIVAS:
                resultados.append((nom_accion, False, f"Acción '{nom_accion}' no reconocida."))
                continue
            try:
                ok, mensaje = acciones.ejecutar(nom_accion, arg)
                resultados.append((nom_accion, bool(ok), mensaje))
                if ok and nom_accion == "escribir_archivo" and arg:
                    try:
                        import cerebro_trabajo
                        cerebro_trabajo.actualizar_archivo(str(arg).split("|")[0].strip())
                    except Exception:
                        pass
            except Exception as exc:
                resultados.append((nom_accion, False, f"Excepción en paso {i}: {exc}"))
    return resultados


def _natural(texto):
    """Deja a lo sumo tres frases limpias, listas para leer en voz alta."""
    limpio = " ".join(str(texto or "").replace("\n", " ").split())
    return " ".join(re.split(r"(?<=[.!?])\s+", limpio)[:3]).strip()


def verificar_coherencia_y_sintetizar(pasos, resultados):
    """Síntesis breve y natural con base en los éxitos y fallos reales."""
    if not resultados:
        return "No pude ejecutar los pasos solicitados."
    total = len(pasos)
    n_ok = sum(1 for _, ok, _ in resultados if ok)
    if n_ok == total:
        nombres = {
            "poner_recordatorio": "programé tu recordatorio",
            "activar_hud": "activé el HUD", "abrir_hud": "activé el HUD",
            "activar_modo": "cambié el modo",
            "consultar_conocimiento_local": "consulté tu conocimiento local",
            "resumir_enlace_o_video": "resumí el enlace",
            "revisar_pantalla": "miré la pantalla",
            "contexto_unico": "reuní el contexto",
            "escribir_archivo": "guardé el archivo",
        }
        detalles = []
        for accion, _, mensaje in resultados[:3]:
            if accion == "escribir_archivo":
                hallazgo = re.search(r"'([^']+)'", str(mensaje or ""))
                detalles.append(f"guardé '{hallazgo.group(1)}'" if hallazgo else "guardé el archivo")
            else:
                detalles.append(nombres.get(accion, f"completé {accion}"))
        return _natural(f"Listo. {', '.join(detalles)}.")
    fallidos = [f"en '{acc}': {msg}" for acc, ok, msg in resultados if not ok]
    if n_ok:
        return _natural(f"Pude completar {n_ok} de {total} pasos, pero ocurrió un problema "
                        f"{'; '.join(fallidos[:2])}.")
    return _natural(f"No pude completar la solicitud porque falló {'; '.join(fallidos[:2])}.")


def procesar_turno_multipaso(cerebro, texto, al_frase=None):
    """Bucle completo planificar -> ejecutar -> verificar. Devuelve (atendido, respuesta, acciones)."""
    if not detectar_intencion_multipaso(texto):
        return False, "", []
    pasos = descomponer_en_pasos(texto)
    if len(pasos) < 2:
        return False, "", []
    resultados = ejecutar_plan_multipaso(pasos, app=getattr(cerebro, "app", None))
    respuesta = verificar_coherencia_y_sintetizar(pasos, resultados)
    if callable(al_frase):
        al_frase(respuesta)
    cerebro.historial.append({"role": "user", "content": texto})
    cerebro.historial.append({"role": "assistant", "content": respuesta})
    if hasattr(cerebro, "_podar_historial"):
        cerebro._podar_historial()
    return True, respuesta, [acc for acc, ok, _ in resultados if ok]


__all__ = [
    "sanear_nombre_archivo", "generar_contenido_archivo", "detectar_intencion_multipaso",
    "descomponer_en_pasos", "ejecutar_plan_multipaso", "verificar_coherencia_y_sintetizar",
    "procesar_turno_multipaso",
]
