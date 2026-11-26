"""Flujo único de correo: preparar en silencio, confirmar y cancelar.

Live y Celeste comparten este módulo. Ninguna llamada a ``preparar_correo``
envía nada: el envío real solo ocurre en ``confirmar_envio_correo`` después
de una confirmación explícita del usuario.
"""
import base64
import email.message
import re
import threading

CONFIRMACIONES = {
    "sí", "si", "sí, envía", "si envia", "confirma", "confirmar",
    "confirma el envío", "confirma el envio", "envíalo", "envialo",
    "adelante", "dale", "vale", "sí, adelante",
}
_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
_MAX_ASUNTO = 120
_MAX_CUERPO = 4000
_MAX_DEST = 254

_BLOQUEO = threading.RLock()
_BORRADOR = None


def _texto(datos) -> str:
    return " ".join(str(datos or "").split())


def _resultado(ok: bool, texto: str, **extra):
    return dict(ok=bool(ok), texto=_texto(texto)[:240], **extra)


def leer_correos(limite=5, solo_no_leidos=True):
    """Lectura compartida; reutiliza el conector de Gmail existente."""
    try:
        import google_workspace
        return google_workspace.resumen_correos(limite=limite, solo_no_leidos=solo_no_leidos)
    except Exception as exc:
        return _resultado(False, f"No se pudo leer Gmail ({type(exc).__name__}).", correos=[])


def hay_borrador() -> bool:
    with _BLOQUEO:
        return _BORRADOR is not None


def resumen_pendiente() -> str:
    with _BLOQUEO:
        if not _BORRADOR:
            return ""
        return _BORRADOR["resumen"]


def preparar_correo(destinatario, asunto, cuerpo):
    """Guarda un borrador pendiente y devuelve un resumen hablado; NO envía."""
    global _BORRADOR
    dest = _texto(destinatario).lower()
    asu = _texto(asunto)[:_MAX_ASUNTO]
    cue = str(cuerpo or "").strip()[:_MAX_CUERPO]
    if not _CORREO.fullmatch(dest) or len(dest) > _MAX_DEST:
        return _resultado(False, "Necesito un correo válido para el destinatario.")
    if not asu or not cue:
        return _resultado(False, "Me falta el asunto o el cuerpo del correo.")
    resumen = f"Listo: correo para {dest}, asunto «{asu}». Dime «confirma el envío» o «cancela»."
    with _BLOQUEO:
        _BORRADOR = {"destinatario": dest, "asunto": asu, "cuerpo": cue, "resumen": resumen}
    print(f"[CORREO] Borrador preparado para {dest}; sin envío.", flush=True)
    return _resultado(True, resumen, resumen=resumen, destinatario=dest)


def preparar_desde_texto(texto):
    """Prepara desde lenguaje natural: 'envía a x@y.com, asunto A, mensaje B'."""
    t = str(texto or "")
    dest = _CORREO.search(t)
    if not dest:
        return _resultado(False, "Necesito la dirección de correo del destinatario.")
    asu = re.search(
        r"(?:asunto|t[ií]tulo)\s*[:=]?\s*(.+?)(?=\s+(?:cuerpo|mensaje|dice|texto)\b|$)",
        t, re.IGNORECASE)
    cue = re.search(r"(?:cuerpo|mensaje|dice|texto)\s*[:=]?\s*(.+)$", t, re.IGNORECASE)
    return preparar_correo(dest.group(0), asu.group(1) if asu else "Sin asunto",
                           cue.group(1) if cue else t)


def _enviar_gmail(borrador):
    """Envía por la API de Gmail reutilizando el singleton OAuth del proyecto."""
    from google_workspace_oauth import conectar

    servicios, error = conectar()
    if error or not servicios:
        return False, error or "Google Workspace no está conectado."
    mensaje = email.message.EmailMessage()
    mensaje["To"] = borrador["destinatario"]
    mensaje["Subject"] = borrador["asunto"]
    mensaje.set_content(borrador["cuerpo"])
    raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode("ascii")
    servicios["gmail"].users().messages().send(userId="me", body={"raw": raw}).execute()
    return True, f"Correo enviado a {borrador['destinatario']}."


def confirmar_envio_correo(confirmacion=""):
    """Envía el borrador solo si la confirmación del usuario es explícita."""
    global _BORRADOR
    if str(confirmacion or "").strip().lower() not in CONFIRMACIONES:
        return _resultado(False, "Necesito tu confirmación explícita para enviarlo.")
    with _BLOQUEO:
        if not _BORRADOR:
            return _resultado(False, "No hay ningún correo pendiente de envío.")
        borrador = dict(_BORRADOR)
    try:
        ok, texto = _enviar_gmail(borrador)
    except Exception as exc:
        return _resultado(False, f"No se pudo enviar el correo ({type(exc).__name__}). Revisa la autorización de Gmail.")
    if ok:
        with _BLOQUEO:
            _BORRADOR = None
        print(f"[CORREO] Enviado a {borrador['destinatario']}.", flush=True)
    return _resultado(ok, texto)


def gestionar(accion="", destinatario="", asunto="", cuerpo=""):
    """Único acceso del AGENTE: el envío exige una confirmación explícita."""
    accion = str(accion or "").strip().lower()
    if accion == "preparar":
        resultado = preparar_correo(destinatario, asunto, cuerpo)
    elif accion == "confirmar":
        resultado = confirmar_envio_correo("sí")
    elif accion == "cancelar":
        resultado = cancelar_correo()
    else:
        return "Acción no válida: usa preparar, confirmar o cancelar."
    return str(resultado.get("texto", ""))


def gestionar_desde_texto(texto):
    """Despacha preparar/confirmar/cancelar desde lenguaje natural (Celeste)."""
    t = " ".join(str(texto or "").lower().split())
    if any(x in t for x in ("cancela", "cancelar", "descarta", "olvida el correo")):
        return cancelar_correo()["texto"]
    if any(x in t for x in ("confirma", "confirmar", "envíalo", "envialo",
                            "adelante", "sí, envía", "si envia")):
        return confirmar_envio_correo(t)["texto"]
    return preparar_desde_texto(texto)["texto"]


def registrar_en_motor(registro):
    """Expone los tres pasos al motor concurrente con riesgo y confirmación."""
    try:
        from ejecucion_modelo import ContratoHerramienta
        pasos = (
            ("preparar_correo", preparar_desde_texto, "bajo", False),
            ("confirmar_envio_correo",
             lambda arg=None: confirmar_envio_correo(arg), "alto", True),
            ("cancelar_correo", lambda arg=None: cancelar_correo(), "bajo", False),
        )
        for nombre, handler, riesgo, confirma in pasos:
            registro.registrar(ContratoHerramienta(
                nombre=nombre, categoria="correo",
                descripcion="Prepara, confirma o cancela un correo sin envío implícito.",
                parametros_esquema={"requeridos": [], "opcionales": ["texto"]},
                handler=handler, nivel_riesgo=riesgo,
                requiere_confirmacion=confirma, cancelable=True, timeout_seg=20.0,
            ), sobrescribir=True)
        return True
    except Exception:
        return False


def cancelar_correo():
    """Descarta el borrador sin enviar nada."""
    global _BORRADOR
    with _BLOQUEO:
        tenía = _BORRADOR is not None
        _BORRADOR = None
    return _resultado(True, "Correo cancelado; no se envió nada." if tenía else "No había correo pendiente.")


def registrar_acciones():
    """Registra las acciones deterministas usadas por Celeste."""
    try:
        import acciones
        acciones.registrar(
            "preparar_correo", preparar_desde_texto,
            "prepara un correo y pide confirmación antes de enviarlo", con_texto=True)
        acciones.registrar(
            "confirmar_envio_correo",
            lambda arg=None: confirmar_envio_correo(arg)["texto"],
            "envía el correo pendiente tras tu confirmación explícita", con_texto=True)
        acciones.registrar(
            "cancelar_correo", lambda *_args: cancelar_correo()["texto"],
            "cancela el correo pendiente sin enviarlo")
        return True
    except Exception:
        return False


__all__ = [
    "leer_correos", "hay_borrador", "resumen_pendiente", "preparar_correo",
    "preparar_desde_texto", "gestionar", "gestionar_desde_texto", "confirmar_envio_correo",
    "cancelar_correo", "registrar_acciones", "registrar_en_motor",
]
