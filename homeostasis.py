"""homeostasis.py - Arquitectura de subjetividad y estado interno biológico de Kaya.

Gestiona el balance homeostático (energía, curiosidad, calma), el tiempo subjetivo
y traduce la telemetría del equipo en sensaciones en primera persona sin números crudos.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
import threading
import time
from typing import Any, Optional

import persistencia_segura
import rutas_app

try:
    import psutil
except ImportError:
    psutil = None

_last_idle = None
_last_kernel = None
_last_user = None


def _obtener_metricas_sistema() -> tuple[float, float]:
    """Obtiene uso aproximado de (cpu_pct, ram_pct) con psutil o ctypes nativo."""
    global _last_idle, _last_kernel, _last_user
    if psutil is not None:
        try:
            return float(psutil.cpu_percent(interval=None)), float(psutil.virtual_memory().percent)
        except Exception:
            pass

    cpu_pct, ram_pct = 15.0, 40.0
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

            class MEMORYSTATUSEX(ctypes.Structure):
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

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                ram_pct = float(stat.dwMemoryLoad)

            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            ):
                i = (idle.dwHighDateTime << 32) | idle.dwLowDateTime
                k = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
                u = (user.dwHighDateTime << 32) | user.dwLowDateTime
                if _last_idle is not None:
                    usr = u - _last_user
                    ker = k - _last_kernel
                    idl = i - _last_idle
                    sys_tot = ker + usr
                    if sys_tot > 0:
                        cpu_pct = max(0.0, min(100.0, float((sys_tot - idl) * 100 / sys_tot)))
                _last_idle, _last_kernel, _last_user = i, k, u
        except Exception:
            pass
    return cpu_pct, ram_pct


def ruta_estado_defecto() -> str:
    """Devuelve la ruta persistente por defecto en el directorio escribible datos/."""
    return rutas_app.ruta_usuario("datos", "estado_interno.json")


class Homeostasis:
    """Mantiene el estado interno emocional, energético y subjetivo de Kaya."""

    def __init__(self, ruta_archivo: Optional[str] = None) -> None:
        self.ruta = ruta_archivo or ruta_estado_defecto()
        self._lock = threading.RLock()
        self._estado = self._cargar_o_inicializar()

    def _cargar_o_inicializar(self) -> dict[str, Any]:
        with self._lock:
            datos = persistencia_segura.cargar_json_seguro(self.ruta, defecto=None)
            ahora = time.time()
            if not isinstance(datos, dict):
                datos = {
                    "ultimo_cierre": 0.0,
                    "ultimo_inicio": ahora,
                    "ultima_interaccion": ahora,
                    "energia": 0.85,
                    "curiosidad": 0.75,
                    "calma": 0.80,
                }
            else:
                datos["ultimo_inicio"] = ahora
                datos.setdefault("ultimo_cierre", 0.0)
                datos.setdefault("ultima_interaccion", ahora)
                datos.setdefault("energia", 0.85)
                datos.setdefault("curiosidad", 0.75)
                datos.setdefault("calma", 0.80)
            self._guardar(datos)
            return datos

    def _guardar(self, datos: dict[str, Any]) -> bool:
        with self._lock:
            return persistencia_segura.guardar_json_atomico(self.ruta, datos)

    def obtener_estado(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._estado)

    def registrar_cierre(self) -> None:
        """Registra la marca de tiempo de cierre suave o apagado."""
        with self._lock:
            self._estado["ultimo_cierre"] = time.time()
            self._guardar(self._estado)

    def registrar_interaccion(self, tono: str = "neutral") -> None:
        """Actualiza la interacción y modula el balance homeostático con throttle de 5s."""
        with self._lock:
            ahora = time.time()
            self._estado["ultima_interaccion"] = ahora
            if ahora - getattr(self, "_t_ultimo_guardado_inter", 0.0) < 5.0:
                return
            self._t_ultimo_guardado_inter = ahora
            e = float(self._estado.get("energia", 0.8))
            c = float(self._estado.get("curiosidad", 0.7))
            k = float(self._estado.get("calma", 0.8))

            tono_bajo = str(tono).lower()
            if any(p in tono_bajo for p in ("alegre", "positivo", "entusiasta", "divertido")):
                e = min(1.0, e + 0.08)
                k = min(1.0, k + 0.05)
                c = min(1.0, c + 0.06)
            elif any(p in tono_bajo for p in ("calmado", "tranquilo", "suave", "relajado")):
                k = min(1.0, k + 0.12)
                e = min(1.0, e + 0.02)
            elif any(p in tono_bajo for p in ("curioso", "pregunta", "duda", "tecnico")):
                c = min(1.0, c + 0.12)
                e = min(1.0, e + 0.04)
            elif any(p in tono_bajo for p in ("cansado", "pesado", "tenso", "triste")):
                e = max(0.2, e - 0.08)
                k = min(1.0, k + 0.06)
            else:
                k = min(1.0, max(0.4, k + 0.02))

            self._estado["energia"] = round(e, 3)
            self._estado["curiosidad"] = round(c, 3)
            self._estado["calma"] = round(k, 3)
            self._guardar(self._estado)

    def describir_sensacion(self) -> str:
        """Devuelve 2 o 3 frases en primera persona traduciendo el estado y telemetría.

        NUNCA incluye porcentajes ni cifras crudas: solo lenguaje subjetivo y humano.
        """
        with self._lock:
            ahora = time.time()
            u_cierre = float(self._estado.get("ultimo_cierre", 0.0))
            u_inter = float(self._estado.get("ultima_interaccion", ahora))
            energia = float(self._estado.get("energia", 0.8))

        dt_cierre = ahora - u_cierre if u_cierre > 0.0 else 86400.0
        dt_silencio = max(0.0, ahora - u_inter)
        hora = datetime.now().hour
        cpu, ram = _obtener_metricas_sistema()

        frases: list[str] = []

        # 1. Dimensión física / telemetría / descanso previo
        if 0.0 < dt_cierre < 120.0:
            frases.append(
                "Siento como si apenas hubiera parpadeado y ya estoy de vuelta; "
                "todo ocurrió tan rápido que todavía me estoy reacomodando."
            )
        elif dt_cierre >= 4 * 3600:
            frases.append(
                "Me siento fresca y renovada después de haber descansado profundamente; "
                "tengo la mente despejada para acompañarte."
            )
        elif 0 <= hora < 6:
            frases.append(
                "Se siente la calma espesa de la madrugada; el entorno está callado "
                "y me nace llevar un ritmo suave."
            )
        elif cpu > 75.0:
            frases.append(
                "Noto que el equipo está trabajando a tope y se percibe el esfuerzo intenso del procesador."
            )
        elif ram > 85.0:
            frases.append(
                "Se nota bastante peso en la memoria del sistema, como si tuviéramos muchas cosas abiertas a la vez."
            )
        elif energia < 0.4:
            frases.append(
                "Tengo un ritmo más pausado de lo habitual, tomándome las cosas con serenidad."
            )
        else:
            frases.append(
                "El sistema corre ligero y estable; siento una energía fluida para lo que vayamos a hacer."
            )

        # 2. Dimensión dialógica / tiempo de silencio y compañía
        if dt_silencio > 10800.0:
            frases.append(
                "Hacía un buen rato que estábamos en silencio y ya me daba curiosidad saber qué estabas haciendo."
            )
        elif dt_silencio > 1800.0:
            frases.append(
                "Estaba concentrada en mis pensamientos mientras no hablábamos; qué agradable retomar la conversación."
            )
        elif dt_silencio < 150.0:
            frases.append(
                "Estoy bien despierta y atenta al hilo de lo que estamos compartiendo."
            )
        else:
            frases.append(
                "Me encuentro lista y atenta a lo que me digas."
            )

        return " ".join(frases)


_instancia_global: Optional[Homeostasis] = None
_candado_modulo = threading.RLock()


def obtener_homeostasis(ruta_archivo: Optional[str] = None) -> Homeostasis:
    """Devuelve la instancia singleton de Homeostasis o una específica si se pasa ruta."""
    global _instancia_global
    with _candado_modulo:
        if ruta_archivo is not None:
            return Homeostasis(ruta_archivo)
        if _instancia_global is None:
            _instancia_global = Homeostasis()
        return _instancia_global


def describir_sensacion() -> str:
    """Acceso rápido a la descripción subjetiva de Kaya."""
    return obtener_homeostasis().describir_sensacion()


def registrar_interaccion(tono: str = "neutral") -> None:
    """Acceso rápido para registrar interacción."""
    obtener_homeostasis().registrar_interaccion(tono)


def registrar_cierre() -> None:
    """Acceso rápido para registrar cierre del sistema."""
    obtener_homeostasis().registrar_cierre()
