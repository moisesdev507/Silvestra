"""Conector de Google Workspace: Calendar, Gmail y Drive.

Sin credenciales o sin librerías instaladas degrada limpiamente: ninguna
función lanza excepciones y todas devuelven un dict con ``texto`` y ``ok``.
El flujo OAuth y los mocks están en ``google_workspace_oauth.py``.
"""
import datetime as dt
import re

from google_workspace_oauth import (
    MENSAJE_CONFIG, conectar, reiniciar, set_servicio_mock, set_servicios_mock,
)


def _fallo(mensaje, **datos):
    return dict(ok=False, texto=mensaje, **datos)


def _entero(valor, por_defecto, minimo=1, maximo=25):
    try:
        return max(minimo, min(maximo, int(valor)))
    except Exception:
        return por_defecto


def _hora(valor):
    texto = str(valor or "")
    if not texto:
        return "hora por definir"
    try:
        fecha = dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.astimezone()
        return fecha.strftime("%H:%M")
    except Exception:
        return texto[:16]


def autorizar_google():
    """Inicia el flujo OAuth local y guarda el token ignorado por Git."""
    servicios, error = conectar(autorizar=True)
    if error:
        return _fallo(error)
    return {"ok": True,
            "texto": "Google Workspace autorizado. Calendar, Gmail y Drive listos.",
            "servicios": list(servicios)}


def agenda_hoy(dias=2):
    """Próximos eventos de Calendar con título, hora local y descripción."""
    servicios, error = conectar()
    if error:
        return _fallo(error, eventos=[])
    dias = _entero(dias, 2, 1, 31)
    inicio = dt.datetime.now().astimezone()
    fin = inicio + dt.timedelta(days=dias)
    try:
        respuesta = servicios["calendario"].events().list(
            calendarId="primary", timeMin=inicio.isoformat(),
            timeMax=fin.isoformat(), singleEvents=True,
            orderBy="startTime", maxResults=25).execute()
    except Exception as exc:
        return _fallo(f"No se pudo leer Calendar ({type(exc).__name__})", eventos=[])
    eventos = []
    for item in (respuesta or {}).get("items", [])[:25]:
        comienzo = ((item.get("start") or {}).get("dateTime")
                    or (item.get("start") or {}).get("date") or "")
        eventos.append({"titulo": item.get("summary", "Sin título"),
                        "hora": _hora(comienzo),
                        "descripcion": item.get("description", ""),
                        "inicio": comienzo})
    if not eventos:
        return {"ok": True, "eventos": [],
                "texto": f"No tienes eventos en los próximos {dias} días."}
    resumen = " | ".join(f"{e['hora']} {e['titulo']}" for e in eventos[:8])
    return {"ok": True, "eventos": eventos, "texto": f"Agenda próxima: {resumen}"}


def crear_evento_calendario(titulo, fecha_iso, duracion_min=60):
    """Crea un evento en Calendar; sin fecha, usa la hora siguiente."""
    servicios, error = conectar()
    if error:
        return _fallo(error)
    titulo = str(titulo or "").strip()
    if not titulo:
        return _fallo("Dime el título del evento que quieres agendar.")
    try:
        if str(fecha_iso or "").strip():
            inicio = dt.datetime.fromisoformat(str(fecha_iso).strip().replace("Z", "+00:00"))
        else:
            inicio = dt.datetime.now().astimezone() + dt.timedelta(hours=1)
        if inicio.tzinfo is None:
            inicio = inicio.astimezone()
        fin = inicio + dt.timedelta(minutes=_entero(duracion_min, 60, 5, 480))
        zona = str(inicio.tzinfo)
        cuerpo = {"summary": titulo, "description": "Agendado por Lyris",
                  "start": {"dateTime": inicio.isoformat(), "timeZone": zona},
                  "end": {"dateTime": fin.isoformat(), "timeZone": zona}}
    except Exception:
        return _fallo("No pude interpretar la fecha. Usa ISO: 2026-11-24T10:00:00")
    try:
        creado = servicios["calendario"].events().insert(
            calendarId="primary", body=cuerpo).execute() or {}
    except Exception as exc:
        return _fallo(f"No se pudo crear el evento ({type(exc).__name__})")
    enlace = creado.get("htmlLink", "")
    return {"ok": True, "evento": creado,
            "texto": f"Evento creado: {titulo} a las {_hora(inicio)}"
                     + (f". Enlace: {enlace[:160]}" if enlace else ".")}


def _limpiar_texto_tts(texto: str) -> str:
    """Elimina entidades HTML, caracteres invisibles Unicode, tags y normaliza espacios para voz natural."""
    if not texto:
        return ""
    import html
    t = html.unescape(str(texto))
    # Quitar tags HTML si vienen en snippets
    t = re.sub(r"<[^>]+>", " ", t)
    # Quitar emails entre <...>
    t = re.sub(r"<[^@\s]+@[^@\s]+>", " ", t)
    # Quitar entidades residuales tipo &nbsp;
    t = re.sub(r"&[a-zA-Z0-9#]+;", " ", t)
    # Quitar caracteres invisibles / formato Unicode:
    # \u034f (grapheme joiner), \u200b-\u200f (zero width, marcas bidi), \ufeff (BOM), \u00a0 (nbsp), \xad (soft hyphen)
    t = re.sub(r"[\u034f\u200b-\u200f\u2028-\u202f\ufeff\u00ad\xa0]", " ", t)
    # Limpiar comillas, corchetes y caracteres técnicos raros
    t = t.replace('"', '').replace("'", "").replace("[", "").replace("]", "")
    # Espacios múltiples
    t = " ".join(t.split()).strip()
    return t


def _limpiar_remitente(remitente: str) -> str:
    """Extrae el nombre limpio del remitente, sin dirección de correo."""
    raw = str(remitente or "").strip()
    if "<" in raw and ">" in raw:
        nombre = raw.split("<", 1)[0].strip()
        if nombre:
            return _limpiar_texto_tts(nombre)
        dir_mail = raw.split("<", 1)[1].split(">", 1)[0].strip()
        usuario = dir_mail.split("@", 1)[0]
        return _limpiar_texto_tts(usuario.replace(".", " ").replace("_", " "))
    r = _limpiar_texto_tts(raw)
    if "@" in r and " " not in r:
        r = r.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    return r or "un remitente"


def _formatear_frase_correo(rem: str, asu: str) -> str:
    """Genera una frase corta y natural para TTS sobre un correo."""
    rem_limpio = _limpiar_remitente(rem)
    asu_limpio = _limpiar_texto_tts(asu)
    if asu_limpio and asu_limpio.lower() != "sin asunto":
        return f"Tienes un correo de {rem_limpio} sobre {asu_limpio}."
    return f"Tienes un correo de {rem_limpio}."


def resumen_correos(limite=5, solo_no_leidos=True):
    """Remitente, asunto y snippet de los últimos correos de Gmail formateados para TTS."""
    servicios, error = conectar()
    if error:
        return _fallo(error, correos=[])
    limite = _entero(limite, 5, 1, 20)
    consulta = "is:unread" if str(solo_no_leidos).lower() not in ("false", "0", "no") else ""
    try:
        mensajes = servicios["gmail"].users().messages().list(
            userId="me", q=consulta, maxResults=limite).execute() or {}
        correos = []
        frases_habladas = []
        for mensaje in mensajes.get("messages", [])[:limite]:
            detalle = servicios["gmail"].users().messages().get(
                userId="me", id=mensaje.get("id"), format="metadata",
                metadataHeaders=["From", "Subject"]).execute() or {}
            cabeceras = {h.get("name", "").lower(): h.get("value", "")
                         for h in (detalle.get("payload") or {}).get("headers", [])}
            rem = _limpiar_remitente(cabeceras.get("from", "desconocido"))
            asu = _limpiar_texto_tts(cabeceras.get("subject", "sin asunto"))
            snip = _limpiar_texto_tts(detalle.get("snippet", ""))
            correos.append({"remitente": rem, "asunto": asu, "snippet": snip})
            # Frase natural para voz sin truncamientos rotos
            frase = _formatear_frase_correo(rem, asu).rstrip(".")
            frases_habladas.append(frase)
    except Exception as exc:
        return _fallo(f"No se pudo leer Gmail ({type(exc).__name__})", correos=[])
    if not correos:
        return {"ok": True, "correos": [], "texto": "No hay correos nuevos por ahora."}
    texto = ". ".join(frases_habladas) + "."
    return {"ok": True, "correos": correos, "texto": texto}


def buscar_drive(consulta, limite=5):
    """Busca archivos en Drive por nombre o texto completo."""
    servicios, error = conectar()
    if error:
        return _fallo(error, archivos=[])
    aguja = str(consulta or "").strip().replace("'", "\\'")[:120]
    if not aguja:
        return _fallo("Dime qué quieres buscar en Drive.", archivos=[])
    limite = _entero(limite, 5, 1, 20)
    consulta_q = f"fullText contains '{aguja}' or name contains '{aguja}'"
    try:
        respuesta = servicios["drive"].files().list(
            q=consulta_q, pageSize=limite, spaces="drive",
            fields="files(id,name,mimeType,webViewLink)").execute() or {}
    except Exception as exc:
        return _fallo(f"No se pudo buscar en Drive ({type(exc).__name__})", archivos=[])
    archivos = [{"nombre": f.get("name", "sin nombre"),
                 "tipo": f.get("mimeType", "desconocido"),
                 "enlace": f.get("webViewLink", "")}
                for f in respuesta.get("files", [])[:limite]]
    if not archivos:
        return {"ok": True, "archivos": [], "texto": f"Sin resultados en Drive para «{aguja[:60]}»."}
    texto = " | ".join(f"{a['nombre']} ({a['tipo']}) {a['enlace'][:100]}"
                       for a in archivos[:6])
    return {"ok": True, "archivos": archivos, "texto": "Drive: " + texto}


__all__ = ["MENSAJE_CONFIG", "autorizar_google", "set_servicios_mock",
           "set_servicio_mock", "reiniciar", "agenda_hoy",
           "crear_evento_calendario", "resumen_correos", "buscar_drive"]
