"""Gestión del estado persistente de Silvestra: última sesión, saludo anterior e iniciativa."""
import json
import os
import time

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado.json")


def cargar():
    """Carga el estado desde estado.json."""
    try:
        if os.path.exists(RUTA):
            with open(RUTA, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "ultima_vez": None,
        "ultimo_saludo": "",
        "iniciativa": False,
        "palabra_clave": True,
        "hud": False,
        "telegram_chat_id": None,
        "diario_ultima_fecha": None,
        "diario_ultimo_mensaje_manana": None,
        "salida_activa": None,
    }


def guardar(datos):
    """Guarda el estado en estado.json."""
    try:
        with open(RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def tiempo_transcurrido_texto(ultima_vez):
    """Devuelve una frase natural describiendo cuánto tiempo pasó desde ultima_vez."""
    if not ultima_vez:
        return "es la primera vez que interactúan recientemente"
    delta = max(0, time.time() - ultima_vez)
    minutos = int(delta // 60)
    if minutos < 2:
        return "hace un momento"
    if minutos < 60:
        return f"hace {minutos} minutos"
    horas = int(minutos // 60)
    if horas == 1:
        return "hace una hora"
    if horas < 24:
        return f"hace {horas} horas"
    dias = int(horas // 24)
    if dias == 1:
        return "hace un día"
    return f"hace {dias} días"
