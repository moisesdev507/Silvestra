"""Asistente de configuración inicial de Kaya: nombre, claves, tecla y audio."""
from __future__ import annotations

import os
import re

import identidad_origen
import kaya_config_ui
import migracion_config
import persistencia_segura as ps
import rutas_app
from PySide6.QtWidgets import QApplication

BASE = rutas_app.dir_usuario()
CLAVES = ("GEMINI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY")
TECLAS = ("Ctrl + Alt + K", "Alt + Espacio", "F9", "F10")
MODOS_AUDIO = (("Audífonos", True), ("Parlantes", False))
ENLACES = {
    "GEMINI_API_KEY": "https://aistudio.google.com/app/apikey",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "DEEPGRAM_API_KEY": "https://console.deepgram.com/",
}
ETIQUETAS = {
    "GEMINI_API_KEY": "Gemini Live y visión (obligatoria)",
    "GROQ_API_KEY": "Motor clásico rápido (obligatoria)",
    "DEEPGRAM_API_KEY": "Voz en tiempo real (obligatoria)",
}
_FORMATO = re.compile(r"^[A-Za-z0-9_.\-]{12,}$")
_NOMBRE = re.compile(r"^[\w .'\-]{1,40}$", re.UNICODE)
_MARCADORES = ("tu_clave", "tuclave", "your_key", "changeme", "cambiar",
               "xxxx", "xxx", "clave-aqui", "pega_tu_clave")


def leer_env(ruta=None):
    """Lee un .env simple sin ejecutar código ni interpretar comandos."""
    ruta = ruta or os.path.join(BASE, ".env")
    datos = {}
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                if linea.lower().startswith("export "):
                    linea = linea[7:].strip()
                if "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave = clave.strip()
                if clave:
                    datos[clave] = valor.strip().strip("'\"")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[onboarding] No se pudo leer .env: {e}", flush=True)
    return datos


def cargar_env(ruta=None):
    """Vuelca el .env local en el entorno y refresca `config` sin reinicio."""
    datos = leer_env(ruta)
    for clave, valor in datos.items():
        if valor:
            os.environ[clave] = valor
    try:
        import claves_dinamicas
        claves_dinamicas.recargar(ruta)
    except Exception:
        pass
    return datos


def claves_actuales(ruta=None):
    """Combina entorno y .env; el archivo local tiene prioridad."""
    actuales = {k: str(os.environ.get(k, "") or "").strip() for k in CLAVES}
    actuales.update({k: v for k, v in leer_env(ruta).items() if k in CLAVES})
    return actuales


def validar_clave(nombre, valor):
    """Valida formato básico sin revelar ni registrar la clave."""
    valor = str(valor or "").strip()
    if not valor:
        return False, f"{nombre}: está vacía."
    if any(m in valor.lower() for m in _MARCADORES) or set(valor) <= set("xX*"):
        return False, f"{nombre}: parece un marcador de posición."
    if not _FORMATO.fullmatch(valor):
        return False, f"{nombre}: usa solo letras, números, _, . o -."
    return True, ""


def necesita_onboarding(ruta=None):
    """True si falta el .env o alguna clave obligatoria no es válida."""
    ruta = ruta or os.path.join(BASE, ".env")
    if not os.path.isfile(ruta):
        return True
    actuales = claves_actuales(ruta)
    return any(not validar_clave(k, actuales.get(k))[0] for k in CLAVES)


def guardar_configuracion(nombre, claves, base=None, ruta_env=None,
                          tecla=None, audifonos=None):
    """Guarda .env, perfil y tecla/audio elegidos, sin borrar claves previas."""
    base = base or BASE
    ruta_env = ruta_env or os.path.join(base, ".env")
    nombre = str(nombre or "").strip()
    if not _NOMBRE.fullmatch(nombre):
        return False, "Escribe un nombre válido (máximo 40 caracteres)."
    errores = []
    for clave in CLAVES:
        ok, mensaje = validar_clave(clave, (claves or {}).get(clave))
        if not ok:
            errores.append(mensaje)
    if errores:
        return False, " · ".join(errores)

    tecla = str(tecla or "").strip()
    if tecla not in TECLAS:
        tecla = TECLAS[0]
    if isinstance(audifonos, str):
        audifonos = audifonos.strip().lower() in (
            "1", "true", "si", "sí", "audifonos", "audífonos")
    valor_audio = "1" if bool(audifonos) else "0"

    try:
        ruta_datos = os.path.join(base, "datos")
        os.makedirs(ruta_datos, exist_ok=True)
        if not identidad_origen.perfil_con_usuario(base):
            if not identidad_origen.preparar_perfil_usuario(nombre, base=base):
                return False, "No se pudo guardar el perfil en datos/."
        else:
            identidad_origen.desactivar_primer_despertar_si_existe(base)

        # El nombre escrito es SOLO del usuario: nunca se convierte en "nombre" de Kaya.
        ruta_memoria = os.path.join(base, "memoria.json")
        memoria = ps.cargar_json_seguro(ruta_memoria, {})
        if not isinstance(memoria, dict):
            memoria = {}
        memoria["nombre"] = identidad_origen.NOMBRE
        # Compatibilidad: los módulos clásicos saludan con `creador`. Guardamos ahí
        # al USUARIO actual para que nunca se mencione al creador de forma espontánea.
        memoria["creador"] = nombre
        memoria["creador_real"] = identidad_origen.CREADOR
        memoria["usuario"] = nombre
        if not ps.guardar_json_atomico(ruta_memoria, memoria):
            return False, "No se pudo guardar la identidad en memoria.json."

        datos_env = {clave: claves[clave] for clave in CLAVES}
        datos_env["KAYA_TECLA"] = tecla
        datos_env["KAYA_MODO_AUDIFONOS"] = valor_audio
        if not migracion_config.escribir_env(ruta_env, datos_env):
            return False, "No se pudo guardar la configuración."
    except Exception as e:
        return False, f"Error guardando la configuración: {type(e).__name__}"

    cargar_env(ruta_env)
    return True, "Configuración guardada en esta laptop."


class OnboardingDialog(kaya_config_ui.ConfigKayaDialog):
    """Primer arranque: solo nombre, tres claves, tecla y modo de audio."""

    def __init__(self, base=None, parent=None):
        super().__init__(base=base, parent=parent, onboarding=True)


def migrar_config_local(base=None):
    """Migra claves de config.py y neutraliza el despertar en perfiles existentes."""
    base = base or BASE
    actuales = claves_actuales(os.path.join(base, ".env"))
    migradas = migracion_config.migrar_desde_config(
        base, actuales=actuales,
        es_valida=lambda nombre, valor: validar_clave(nombre, valor)[0])
    identidad_origen.desactivar_primer_despertar_si_existe(base)
    if migradas:
        cargar_env(os.path.join(base, ".env"))
    return migradas


def asegurar_configuracion(base=None):
    """Migra claves antiguas y muestra el onboarding solo si aún faltan."""
    base = base or BASE
    ruta = os.path.join(base, ".env")
    migrar_config_local(base)
    if not necesita_onboarding(ruta):
        cargar_env(ruta)
        return True
    app = QApplication.instance() or QApplication([])
    del app
    dialogo = OnboardingDialog(base=base)
    dialogo.exec()
    return bool(dialogo.resultado)
