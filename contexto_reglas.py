"""Reglas deterministas y puras para el Silvestra Context Engine (Etapa 2).

Procesa datos detectados por sensores y genera interpretaciones de nivel 'probable',
con cálculo explícito de confianza (0.0 a 1.0) y nombre de la regla aplicada.
Garantiza cero efectos secundarios y 'permite_accion_automatica: False'.
"""
from __future__ import annotations

import datetime
import re
import time
from typing import Any

# Categorías de ejecutables reconocidos
EJECUTABLES_DEV = {
    "code.exe",
    "devenv.exe",
    "pycharm64.exe",
    "sublime_text.exe",
    "windowsterminal.exe",
    "powershell.exe",
    "cmd.exe",
    "git-bash.exe",
}
EJECUTABLES_WEB = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
}
EJECUTABLES_COMUNICACION = {
    "telegram.exe",
    "discord.exe",
    "slack.exe",
    "whatsapp.exe",
    "teams.exe",
}
EJECUTABLES_MULTIMEDIA = {
    "spotify.exe",
    "vlc.exe",
    "wmplayer.exe",
    "musicbee.exe",
}

DIAS_SEMANA_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def determinar_franja_horaria(hora_24: int) -> str:
    """Clasifica la hora del día en 4 franjas humanas deterministas."""
    if 0 <= hora_24 < 6:
        return "madrugada"
    if 6 <= hora_24 < 12:
        return "mañana"
    if 12 <= hora_24 < 19:
        return "tarde"
    return "noche"


def generar_contexto_temporal(tiempo_inicio_motor: float) -> dict[str, Any]:
    """Genera datos temporales de fecha, hora y franja panameña/local."""
    ahora = datetime.datetime.now()
    h_12 = ahora.hour % 12 or 12
    mer = "p. m." if ahora.hour >= 12 else "a. m."
    return {
        "hora": f"{h_12}:{ahora.minute:02d} {mer}",
        "franja": determinar_franja_horaria(ahora.hour),
        "dia_semana": DIAS_SEMANA_ES[ahora.weekday()],
        "sesion_seg": round(time.time() - tiempo_inicio_motor, 1),
    }


def extraer_proyecto_de_titulo(titulo: str, ejecutable: str) -> dict[str, Any] | None:
    """Extrae heurísticamente el nombre del proyecto o espacio de trabajo activo."""
    if not titulo:
        return None

    exe = (ejecutable or "").lower()

    # Patrón común en VS Code: "[● ]archivo.py - NombreProyecto - Visual Studio Code"
    if "code.exe" in exe or "visual studio code" in titulo.lower():
        m = re.search(r"^(?:●\s*)?.*?\s+-\s+([^\-]+)\s+-\s+Visual Studio Code", titulo, re.I)
        if m:
            proy = m.group(1).strip()
            if proy and proy.lower() not in ("welcome", "bienvenido"):
                return {
                    "valor": proy,
                    "confianza": 0.85,
                    "regla": "titulo_vscode_workspace",
                    "permite_accion_automatica": False,
                }

    # Patrón general de editores/consolas: "archivo - proyecto" o "proyecto [rama]"
    m_gen = re.search(r"\[([^\]]+)\]", titulo)
    if m_gen:
        val = m_gen.group(1).strip()
        if len(val) >= 3:
            return {
                "valor": val,
                "confianza": 0.60,
                "regla": "titulo_corchetes_proyecto",
                "permite_accion_automatica": False,
            }

    return None


def clasificar_actividad(
    ejecutable: str,
    titulo: str,
    inactividad_seg: float,
    ausente_presencia: bool = False,
) -> dict[str, Any]:
    """Infiere la actividad probable actual a partir de la ventana y el tiempo de inactividad."""
    # 1. Ausencia física comprobada
    if ausente_presencia or inactividad_seg >= 300.0:
        return {
            "valor": "ausente",
            "confianza": 0.95 if ausente_presencia else 0.90,
            "regla": "ausente_presencia" if ausente_presencia else "inactividad_superior_300s",
            "permite_accion_automatica": False,
        }

    exe = (ejecutable or "").lower()

    # 2. Programación / Desarrollo
    if exe in EJECUTABLES_DEV:
        return {
            "valor": "programando",
            "confianza": 0.85,
            "regla": "ejecutable_editor_desarrollo",
            "permite_accion_automatica": False,
        }

    # 3. Navegación Web
    if exe in EJECUTABLES_WEB:
        conf = 0.75
        regla = "ejecutable_navegador_web"
        # Refuerzo por título si consulta documentación o código
        tit_low = (titulo or "").lower()
        if any(w in tit_low for w in ("github", "stackoverflow", "docs", "python", "api")):
            return {
                "valor": "investigando_codigo",
                "confianza": 0.85,
                "regla": "navegador_con_titulo_tecnico",
                "permite_accion_automatica": False,
            }
        return {
            "valor": "navegando",
            "confianza": conf,
            "regla": regla,
            "permite_accion_automatica": False,
        }

    # 4. Comunicación
    if exe in EJECUTABLES_COMUNICACION:
        return {
            "valor": "comunicacion",
            "confianza": 0.80,
            "regla": "ejecutable_mensajeria",
            "permite_accion_automatica": False,
        }

    # 5. Multimedia
    if exe in EJECUTABLES_MULTIMEDIA:
        return {
            "valor": "multimedia",
            "confianza": 0.80,
            "regla": "ejecutable_multimedia",
            "permite_accion_automatica": False,
        }

    # 6. Ejecutable genérico conocido
    if exe:
        return {
            "valor": "actividad_general",
            "confianza": 0.50,
            "regla": "ejecutable_sin_categoria_especifica",
            "permite_accion_automatica": False,
        }

    return {
        "valor": "desconocida",
        "confianza": 0.20,
        "regla": "sin_ventana_activa_registrada",
        "permite_accion_automatica": False,
    }


def evaluar_sesion_continua(duracion_sesion_seg: float, inactividad_seg: float) -> dict[str, Any]:
    """Evalúa si la sesión de trabajo continuo ha sido prolongada (>= 90 minutos)."""
    es_prolongada = duracion_sesion_seg >= 5400.0 and inactividad_seg < 300.0
    return {
        "valor": bool(es_prolongada),
        "confianza": 0.85 if es_prolongada else 0.90,
        "regla": "sesion_activa_mayor_90min" if es_prolongada else "sesion_dentro_del_limite",
        "permite_accion_automatica": False,
    }


def evaluar_disponibilidad_usuario(
    inactividad_seg: float,
    modo_sistema: str,
    actividad_probable: str,
) -> dict[str, Any]:
    """Infiere el grado de disponibilidad o interrupción aceptable del usuario."""
    if actividad_probable == "ausente" or inactividad_seg >= 300.0:
        return {
            "valor": "no_disponible",
            "confianza": 0.90,
            "regla": "usuario_ausente_o_inactivo",
            "permite_accion_automatica": False,
        }

    if modo_sistema in ("estudio", "noche"):
        return {
            "valor": "enfoque_alto",
            "confianza": 0.85,
            "regla": "modo_sistema_restringido",
            "permite_accion_automatica": False,
        }

    if actividad_probable == "programando":
        return {
            "valor": "concentrado",
            "confianza": 0.75,
            "regla": "actividad_desarrollo_en_curso",
            "permite_accion_automatica": False,
        }

    return {
        "valor": "disponible",
        "confianza": 0.70,
        "regla": "actividad_estandar_sin_restriccion",
        "permite_accion_automatica": False,
    }
