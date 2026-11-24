"""Briefing proactivo en paralelo para el saludo inicial de Lyris.

Consulta en paralelo Gmail, Calendar y Memoria local con timeout estricto (<1.5s).
Filtra ruido publicitario/newsletter y evita repetir alertas ya avisadas.
"""
import concurrent.futures
import os
import re

import estado

PATRONES_RUIDO = (
    "no-reply", "noreply", "newsletter", "promocion", "promociones",
    "oferta", "descuento", "marketing", "publicidad", "digest",
    "noticias de", "actualizacion de terminos", "security alert",
    "recibo", "factura automatica", "mailer-daemon", "spam",
)


def _limpiar_remitente(remitente: str) -> str:
    """Extrae el nombre limpio del remitente (ej. 'GitHub <notifications@...>' -> 'GitHub')."""
    rem = str(remitente or "").strip()
    if "<" in rem:
        nombre = rem.split("<")[0].strip(" \"'")
        if nombre:
            return nombre
    if "@" in rem:
        usuario = rem.split("@")[0].strip(" \"'")
        return usuario[:25]
    return rem[:25]


def _es_correo_ruidoso(remitente: str, asunto: str) -> bool:
    """Detecta si un correo es probablemente publicitario, newsletter o bot ruidoso."""
    texto = (str(remitente or "") + " " + str(asunto or "")).lower()
    return any(p in texto for p in PATRONES_RUIDO)


def _obtener_avisados_recientes() -> list[str]:
    """Carga los identificadores de correos o eventos ya avisados en saludos previos."""
    try:
        est = estado.cargar()
        avisados = est.get("briefing_avisados", [])
        return list(avisados[-10:]) if isinstance(avisados, list) else []
    except Exception:
        return []


def registrar_alerta_avisada(identificador: str):
    """Guarda un identificador de correo o evento para no repetirlo en el próximo inicio."""
    if not identificador or not str(identificador).strip():
        return
    try:
        est = estado.cargar()
        avisados = est.get("briefing_avisados", [])
        if not isinstance(avisados, list):
            avisados = []
        token = str(identificador).strip()[:100]
        if token not in avisados:
            avisados.append(token)
        est["briefing_avisados"] = avisados[-10:]
        estado.guardar(est)
    except Exception:
        pass


def _leer_gmail_relevante() -> dict | None:
    """Lee Gmail con filtro de promociones y anti-repetición."""
    try:
        import google_workspace
        res = google_workspace.resumen_correos(limite=6, solo_no_leidos=True)
        if not isinstance(res, dict) or not res.get("ok"):
            return None
        correos = res.get("correos", [])
        if not correos:
            return None

        avisados = _obtener_avisados_recientes()
        for c in correos:
            rem = _limpiar_remitente(c.get("remitente", ""))
            asu = str(c.get("asunto", "")).strip()
            if not asu or _es_correo_ruidoso(c.get("remitente", ""), asu):
                continue
            token = f"{rem}:{asu}"
            if token in avisados:
                continue
            return {"remitente": rem, "asunto": asu, "token": token}
    except Exception:
        pass
    return None


def _leer_calendar_hoy() -> dict | None:
    """Lee el próximo evento de hoy en Google Calendar."""
    try:
        import google_workspace
        res = google_workspace.agenda_hoy(dias=1)
        if not isinstance(res, dict) or not res.get("ok"):
            return None
        eventos = res.get("eventos", [])
        if eventos and isinstance(eventos[0], dict):
            ev = eventos[0]
            tit = ev.get("titulo") or ev.get("resumen") or "evento"
            hora = ev.get("hora") or ""
            return {"titulo": tit, "hora": hora, "token": f"{tit}:{hora}"}
    except Exception:
        pass
    return None


def _leer_memoria_hilos() -> dict:
    """Extrae hilos abiertos o recuerdos de trabajo recientes."""
    datos = {}
    try:
        import hilos
        todos = hilos.cargar()
        abiertos = [h.get("texto", "").strip() for h in todos
                    if h.get("estado") == "abierto" and h.get("texto")
                    and h.get("texto").strip() != "NINGUNO."]
        if abiertos:
            datos["hilo_activo"] = abiertos[-1][:60]
    except Exception:
        pass

    try:
        import memoria_persistente as mp
        recuerdos = mp.listar_recuerdos(limite=2)
        if recuerdos:
            datos["recuerdo_reciente"] = recuerdos[0].get("valor", "")[:70]
    except Exception:
        pass
    return datos


def recopilar_briefing_arranque(timeout_total: float = 1.5) -> dict:
    """Consulta en paralelo Gmail, Calendar y Memoria con timeout estricto sin bloquear."""
    resultado = {
        "correo": None,
        "evento": None,
        "hilo_activo": "",
        "recuerdo_reciente": "",
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_gmail = executor.submit(_leer_gmail_relevante)
        fut_cal = executor.submit(_leer_calendar_hoy)
        fut_mem = executor.submit(_leer_memoria_hilos)

        # Memoria local responde casi al instante (<15ms)
        try:
            res_mem = fut_mem.result(timeout=min(0.2, timeout_total))
            if isinstance(res_mem, dict):
                resultado.update(res_mem)
        except Exception:
            pass

        # Gmail y Calendar con el resto del tiempo asignado
        try:
            res_mail = fut_gmail.result(timeout=timeout_total)
            if res_mail:
                resultado["correo"] = res_mail
        except Exception:
            pass

        try:
            res_cal = fut_cal.result(timeout=max(0.1, timeout_total - 0.2))
            if res_cal:
                resultado["evento"] = res_cal
        except Exception:
            pass

    return resultado


__all__ = [
    "recopilar_briefing_arranque",
    "registrar_alerta_avisada",
    "_es_correo_ruidoso",
    "_limpiar_remitente",
    "_obtener_avisados_recientes",
]
