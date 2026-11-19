"""Sesión HTTP global reutilizable con pool de conexiones y keep-alive."""
import requests
from requests.adapters import HTTPAdapter

_sesion = None


def obtener_sesion():
    """Devuelve la sesión HTTP con keep-alive y pool de sockets activos."""
    global _sesion
    if _sesion is None:
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=25,
            pool_maxsize=35,
            max_retries=1,
            pool_block=False,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _sesion = s
    return _sesion
