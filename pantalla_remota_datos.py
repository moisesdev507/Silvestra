"""Módulo de recolección segura de telemetría y datos en vivo para la pantalla de la tablet."""
import ctypes
from ctypes import wintypes
import datetime
import json
import os
import time

import estado

RUTA_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_RECORDATORIOS = os.path.join(RUTA_DIR, "recordatorios.json")
RUTA_NOTAS = os.path.join(RUTA_DIR, "notas.json")

# Variables para cálculo diferencial de CPU
_last_idle = None
_last_kernel = None
_last_user = None


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullExtendedVirtual", ctypes.c_ulonglong),
    ]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def obtener_telemetria_hardware():
    """Obtiene CPU, RAM y Batería de la laptop usando APIs nativas de Windows sin dependencias."""
    global _last_idle, _last_kernel, _last_user
    cpu_pct, ram_pct = 0, 0
    bat_info = {"disponible": False, "porcentaje": 0, "cargando": False}

    try:
        # RAM
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            ram_pct = int(stat.dwMemoryLoad)

        # CPU
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            i = (idle.dwHighDateTime << 32) | idle.dwLowDateTime
            k = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
            u = (user.dwHighDateTime << 32) | user.dwLowDateTime
            if _last_idle is not None:
                usr = u - _last_user
                ker = k - _last_kernel
                idl = i - _last_idle
                sys_tot = ker + usr
                if sys_tot > 0:
                    cpu_pct = max(0, min(100, int((sys_tot - idl) * 100 / sys_tot)))
            _last_idle, _last_kernel, _last_user = i, k, u

        # Batería
        pwr = _SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(pwr)):
            flag = pwr.BatteryFlag
            pct = pwr.BatteryLifePercent
            ac = pwr.ACLineStatus
            if flag != 128 and pct <= 100:
                bat_info = {
                    "disponible": True,
                    "porcentaje": int(pct),
                    "cargando": bool(ac == 1),
                }
    except Exception:
        pass

    return cpu_pct, ram_pct, bat_info


def obtener_recordatorios(modo_privado=False):
    """Carga de forma segura los próximos recordatorios activos."""
    if modo_privado:
        return []
    if not os.path.exists(RUTA_RECORDATORIOS):
        return []
    try:
        with open(RUTA_RECORDATORIOS, "r", encoding="utf-8") as f:
            todos = json.load(f)
        ahora_ts = time.time()
        pendientes = [
            r for r in todos
            if not r.get("completado") and r.get("timestamp", 0) >= ahora_ts - 600
        ]
        pendientes.sort(key=lambda x: x.get("timestamp", 0))
        res = []
        for r in pendientes[:4]:
            txt = str(r.get("texto", "Recordatorio")).strip()
            if len(txt) > 36:
                txt = txt[:33] + "..."
            res.append({
                "hora": r.get("hora_exacta", "--:--"),
                "texto": txt,
                "id": r.get("id"),
            })
        return res
    except Exception:
        return []


def obtener_notas(modo_privado=False):
    """Carga de forma segura las últimas notas registradas."""
    if modo_privado:
        return []
    if not os.path.exists(RUTA_NOTAS):
        return []
    try:
        with open(RUTA_NOTAS, "r", encoding="utf-8") as f:
            todas = json.load(f)
        if not isinstance(todas, list):
            return []
        res = []
        for n in reversed(todas[-4:]):
            txt = str(n.get("texto", "")).strip()
            if len(txt) > 42:
                txt = txt[:39] + "..."
            res.append({
                "fecha": n.get("fecha", ""),
                "materia": n.get("materia", "General"),
                "texto": txt,
            })
        return res
    except Exception:
        return []


def obtener_reloj_fecha():
    """Genera la información horaria en formato 12 horas con fecha en español."""
    ahora = datetime.datetime.now()
    h_int = ahora.hour % 12
    if h_int == 0:
        h_int = 12
    hora_12 = f"{h_int}:{ahora.strftime('%M')}"
    ampm = "AM" if ahora.hour < 12 else "PM"

    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    fecha = f"{dias[ahora.weekday()]}, {ahora.day} de {meses[ahora.month - 1]}"
    return {
        "hora": hora_12,
        "ampm": ampm,
        "segundos": ahora.strftime("%S"),
        "fecha": fecha,
        "es_noche": (ahora.hour >= 22 or ahora.hour < 6),
    }


def recolectar_estado_completo(app, gestor):
    """Agrega toda la información en vivo para el panel Jarvis sin tocar Qt."""
    eco = getattr(gestor, "ecosistema_gestor", None)
    modo_privado = bool(eco.modo_privado()) if eco else False

    cpu_pct, ram_pct, bat_info = obtener_telemetria_hardware()

    # Silvestra en vivo
    descansando = getattr(app, "descansando", False)
    escuchando = getattr(app, "escuchando", False)
    pensando = bool(getattr(app, "pensando", False))
    hablando = False
    voz = getattr(app, "voz", None)
    if voz and hasattr(voz, "ocupada"):
        try:
            hablando = voz.ocupada()
        except Exception:
            hablando = False

    if descansando:
        estado_silv = "dormida"
    elif hablando:
        estado_silv = "hablando"
    elif pensando:
        estado_silv = "pensando"
    elif escuchando:
        estado_silv = "escuchando"
    else:
        estado_silv = "reposo"

    emocion = getattr(app, "emocion_objetivo", "neutral") or "neutral"
    vol = float(getattr(voz, "nivel_volumen", 0.0) if voz else 0.0)
    subtitulo = getattr(app, "ultimo_dicho", "") if hablando else ""

    # Tarjeta dinámica principal (lo proyectado con mostrar_en_tablet o mensaje actual)
    tarjeta = getattr(gestor, "tarjeta_principal", "")
    if not tarjeta:
        tarjeta = getattr(app, "ultimo_dicho", "") or "SILVESTRA VIRTUAL INTERFACE // SISTEMA OPERATIVO"

    # Microfono
    mic_activo = not getattr(app, "silencio_oido", False)
    mic_estado = "Escuchando" if escuchando else ("Activo" if mic_activo else "En silencio")

    # Clima
    clima = ""
    if hasattr(app, "ultimo_clima") and app.ultimo_clima:
        clima = str(app.ultimo_clima).strip()

    # Actividades recientes
    eventos = getattr(gestor, "ultimos_eventos", [])[-4:] if hasattr(gestor, "ultimos_eventos") else []
    if not eventos:
        eventos = [
            {"hora": time.strftime("%H:%M"), "texto": "Sistema HUD en línea"},
            {"hora": time.strftime("%H:%M"), "texto": "Telemetría sincronizada"},
        ]

    # Biometría en vivo
    try:
        if modo_privado: raise PermissionError("modo_privado")
        import pantalla_biometria
        bio_info = pantalla_biometria.obtener_estado_biometria(app)
    except Exception:
        bio_info = {
            "identidad": "espera",
            "solo_dueno": False,
            "similitud_voz": None,
            "umbral_voz": 0.45,
            "camara_activa": False,
            "camara_dueno": False,
            "muestras_voz": 0,
            "muestras_cara": 0,
        }

    # Telemetría del Context Engine (Etapa 4)
    ctx_info = None
    try:
        if modo_privado: raise PermissionError("modo_privado")
        import contexto_hud
        ctx_info = contexto_hud.obtener_telemetria_contexto(app)
    except Exception:
        pass

    return {
        "telemetria": {
            "cpu": cpu_pct,
            "ram": ram_pct,
            "bateria": bat_info,
            "microfono": mic_estado,
            "escuchando": escuchando,
            "modo_privado": modo_privado,
        },
        "silvestra": {
            "estado": estado_silv,
            "emocion": emocion,
            "volumen": vol,
            "subtitulo": subtitulo if not modo_privado else "",
            "tarjeta": tarjeta if not modo_privado else "MODO PRIVADO ACTIVO // INFORMACIÓN OCULTA",
        },
        "biometria": bio_info,
        "contexto": ctx_info,
        "datos": {
            "recordatorios": obtener_recordatorios(modo_privado),
            "notas": obtener_notas(modo_privado),
            "eventos": eventos,
            "reloj": obtener_reloj_fecha(),
            "clima": clima,
        },
        "ts": time.time(),
    }
