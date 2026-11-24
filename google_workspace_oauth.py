"""Carga de credenciales y construcción de servicios Google (importación lazy).

Toda la manipulación de tokens y mocks vive aquí; la API pública queda en
``google_workspace.py``. Nunca se escriben secretos fuera del archivo de token
local ignorado por Git.
"""
import glob
import os
import threading

RAIZ = os.path.dirname(os.path.abspath(__file__))
HOGAR = os.path.expanduser("~")
NOMBRES_TOKEN = ("google_token.json", "token.json")
SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)
MENSAJE_CONFIG = (
    "Google Workspace aún no está autorizado. Configuración en 1 paso: "
    "coloca credentials.json en C:\\Proyecto_Silvestra y di «autorizar Google»."
)

_bloqueo = threading.RLock()
_servicios = {"calendario": None, "gmail": None, "drive": None, "mock": False}


def librerias():
    """Importa las librerías Google solo cuando se necesitan."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        return build, Credentials, Request, InstalledAppFlow
    except Exception:
        return None


def ruta(nombres):
    for directorio in (RAIZ, HOGAR):
        for nombre in nombres:
            candidato = os.path.join(directorio, nombre)
            if os.path.isfile(candidato):
                return candidato
    return None


def ruta_cliente():
    encontrado = ruta(("credentials.json",))
    if encontrado:
        return encontrado
    for directorio in (RAIZ, HOGAR):
        candidatos = sorted(glob.glob(os.path.join(directorio, "client_secret*.json")))
        if candidatos:
            return candidatos[0]
    return None


def guardar_token(creds, destino=None):
    destino = destino or os.path.join(RAIZ, "google_token.json")
    try:
        with open(destino, "w", encoding="utf-8") as archivo:
            archivo.write(creds.to_json())
        return True
    except Exception:
        return False


def conectar(autorizar=False):
    """Devuelve ``(servicios, error)``; error vacío significa listo."""
    with _bloqueo:
        if _servicios["mock"]:
            return _servicios, ""
        if all(_servicios[k] for k in ("calendario", "gmail", "drive")):
            return _servicios, ""
    paquetes = librerias()
    if paquetes is None:
        return None, MENSAJE_CONFIG + " (faltan google-api-python-client y google-auth-oauthlib)."
    build, Credentials, Request, InstalledAppFlow = paquetes
    ruta_token = ruta(NOMBRES_TOKEN)
    creds = None
    if ruta_token:
        try:
            creds = Credentials.from_authorized_user_file(ruta_token, SCOPES)
        except Exception:
            creds = None
    if creds is not None and not getattr(creds, "valid", False):
        if getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        else:
            creds = None
    if creds is None:
        if not autorizar:
            return None, MENSAJE_CONFIG
        cliente = ruta_cliente()
        if not cliente:
            return None, MENSAJE_CONFIG
        try:
            flujo = InstalledAppFlow.from_client_secrets_file(cliente, SCOPES)
            creds = flujo.run_local_server(port=0)
        except Exception as exc:
            return None, f"No se pudo autorizar Google ({type(exc).__name__})."
        guardar_token(creds)
    try:
        nuevos = {
            "calendario": build("calendar", "v3", credentials=creds),
            "gmail": build("gmail", "v1", credentials=creds),
            "drive": build("drive", "v3", credentials=creds),
        }
    except Exception as exc:
        return None, f"No se pudieron crear los servicios de Google ({type(exc).__name__})."
    with _bloqueo:
        _servicios.update(nuevos)
    return _servicios, ""


def set_servicios_mock(calendario=None, gmail=None, drive=None):
    with _bloqueo:
        _servicios.update({"calendario": calendario, "gmail": gmail,
                           "drive": drive, "mock": True})
    return True


def set_servicio_mock(servicio=None, nombre="calendario"):
    clave = str(nombre or "calendario").lower()
    if clave not in ("calendario", "gmail", "drive"):
        return False
    with _bloqueo:
        _servicios["mock"] = True
        _servicios[clave] = servicio
    return True


def reiniciar():
    with _bloqueo:
        for clave in ("calendario", "gmail", "drive"):
            _servicios[clave] = None
        _servicios["mock"] = False
    return True


__all__ = ["RAIZ", "MENSAJE_CONFIG", "librerias", "conectar",
           "set_servicios_mock", "set_servicio_mock", "reiniciar"]
