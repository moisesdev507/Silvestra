"""Módulo de seguridad para el control de la laptop por niveles.

Niveles:
- LIBRE (sin código): acciones seguras de control_laptop.py.
- CON CÓDIGO: apagar, reiniciar, suspender, cerrar sesión.
  Flujo interactivo: ella dice 'Dime el código' y la siguiente frase
  se compara localmente con CODIGO_SEGURIDAD de config.py.
  Entiende palabras ('dos cero cero seis') y dígitos ('2006').
  Máximo 3 intentos, caducidad de 30 s.
  El código NUNCA va al LLM, ni a logs, ni a la memoria.
- PROHIBIDO (nunca): borrar archivos, ejecutar comandos libres,
  instalar paquetes, tocar config.py / memoria / llaves.
"""
import hmac
import os
import re
import threading
import time
import unicodedata

import config

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acciones_log.txt")

MAPA_NUMEROS = {
    "cero": "0", "uno": "1", "un": "1", "una": "1",
    "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
    "diez": "10", "veinte": "20"
}

PATRONES_PROHIBIDOS = [
    r"\b(borrar|eliminar|rmdir|unlink|format|shred|del)\b",
    r"\b(cmd|powershell|bash|sh|exec|eval)\b",
    r"\b(pip\s+install|npm\s+install|setup\.py)\b",
    r"\b(config\.py|memoria\.json|dueno\.npy|voz_dueno\.npy|\.env)\b",
]


def extraer_codigo(texto):
    """Extrae dígitos de texto escrito o pronunciado (ej: 'dos cero cero seis' -> '2006')."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    palabras = re.findall(r"[a-z0-9]+", t)
    digitos = []
    for p in palabras:
        if p in MAPA_NUMEROS:
            digitos.append(MAPA_NUMEROS[p])
        elif p.isdigit():
            digitos.append(p)
    return "".join(digitos)


def registrar_log(nivel, accion, origen, estado, detalle=""):
    """Registra eventos de seguridad en acciones_log.txt sin registrar jamás el código."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        linea = f"[{ts}] [{nivel.upper()}] accion='{accion}' origen='{origen}' estado='{estado}'"
        if detalle:
            linea += f" detalle='{detalle}'"
        linea += "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linea)
    except Exception as e:
        print(f"[control_seguridad] Error al registrar log: {e}", flush=True)


def es_accion_prohibida(texto):
    """Verifica si una acción intenta ejecutar operaciones prohibidas."""
    if not texto:
        return False
    t = str(texto).lower()
    for pat in PATRONES_PROHIBIDOS:
        if re.search(pat, t):
            return True
    return False


def es_dueno_autorizado(app):
    """Valida si el solicitante es el dueño (Telegram, chat local o voz verificada CAM++)."""
    origen = getattr(app, "origen_entrada_actual", "chat")
    if origen in ("chat", "telegram"):
        return True
    voz_dueno = getattr(app, "voz_dueno", None)
    if voz_dueno is not None and getattr(voz_dueno, "activa", False):
        uv = getattr(voz_dueno, "ultima_verificacion", {})
        if not uv.get("es_dueno", True):
            return False
    return True


class ControlSeguridad:
    """Controlador de autorización y códigos de seguridad para la laptop."""

    def __init__(self, app=None):
        self.app = app
        self.accion_pendiente = None
        self.callback_pendiente = None
        self.tiempo_solicitud = 0.0
        self.intentos_fallidos = 0
        self.origen_pendiente = None
        self.bloqueado_hasta = 0.0
        self.modo_simulacion = False

    def _notificar(self, mensaje):
        """Envía respuesta hablada o a la cola sin tocar Qt desde hilos secundarios."""
        if not self.app:
            return
        if hasattr(self.app, "decir") and threading.current_thread() is threading.main_thread():
            self.app.decir(mensaje, 3500)
        elif hasattr(self.app, "cola"):
            self.app.cola.put(("frase", mensaje))

    def tiene_pendiente(self):
        """Indica si hay una acción peligrosa en espera del código de seguridad."""
        if self.accion_pendiente is not None:
            if time.time() - self.tiempo_solicitud > 30.0:
                self.expirar_pendiente()
                return False
            return True
        return False

    def expirar_pendiente(self):
        """Cancela la acción pendiente por exceder el tiempo de 30 segundos."""
        if self.accion_pendiente:
            registrar_log("CON_CODIGO", self.accion_pendiente, self.origen_pendiente or "desconocido",
                          "EXPIRADO", "Tiempo límite de 30s agotado")
            self._notificar("Tiempo de espera agotado. Acción cancelada.")
        self.limpiar_pendiente()

    def limpiar_pendiente(self):
        """Restablece el estado de espera de código."""
        self.accion_pendiente = None
        self.callback_pendiente = None
        self.tiempo_solicitud = 0.0
        self.intentos_fallidos = 0
        self.origen_pendiente = None

    def solicitar_accion_peligrosa(self, nombre_accion, callback_ejecutar, origen=None):
        """Inicia el desafío de seguridad para apagar, reiniciar, suspender o cerrar sesión."""
        origen_act = origen or getattr(self.app, "origen_entrada_actual", "voz")

        if time.time() < self.bloqueado_hasta:
            restante = int(self.bloqueado_hasta - time.time())
            registrar_log("CON_CODIGO", nombre_accion, origen_act, "BLOQUEADO",
                          f"Bloqueo temporal por reintentos ({restante}s restantes)")
            self._notificar(f"Acciones de seguridad bloqueadas temporalmente. Espera {restante} segundos.")
            return False, "Bloqueado temporalmente."

        if not es_dueno_autorizado(self.app):
            registrar_log("CON_CODIGO", nombre_accion, origen_act, "RECHAZADO",
                          "Identidad no verificada como dueño")
            self._notificar("Solo Moisés puede autorizar esta acción.")
            return False, "Identidad no verificada."

        self.accion_pendiente = nombre_accion
        self.callback_pendiente = callback_ejecutar
        self.tiempo_solicitud = time.time()
        self.intentos_fallidos = 0
        self.origen_pendiente = origen_act

        registrar_log("CON_CODIGO", nombre_accion, origen_act, "SOLICITADO",
                      "Esperando código de seguridad local")
        self._notificar("Dime el código.")
        return True, "Esperando código."

    def verificar_codigo(self, texto):
        """Evalúa localmente la frase del usuario sin enviarla jamás al LLM ni a logs."""
        if not self.tiene_pendiente():
            return False

        if time.time() - self.tiempo_solicitud > 30.0:
            self.expirar_pendiente()
            return True

        codigo_real = str(getattr(config, "CODIGO_SEGURIDAD", "0000")).strip()
        codigo_dicho = extraer_codigo(texto)

        coincide = bool(codigo_dicho and hmac.compare_digest(codigo_dicho, codigo_real))

        if coincide:
            accion = self.accion_pendiente
            cb = self.callback_pendiente
            registrar_log("CON_CODIGO", accion, self.origen_pendiente, "AUTORIZADO",
                          "Código verificado correctamente")
            self.limpiar_pendiente()
            if cb:
                cb(self.modo_simulacion)
            return True
        else:
            self.intentos_fallidos += 1
            registrar_log("CON_CODIGO", self.accion_pendiente, self.origen_pendiente,
                          "INTENTO_FALLIDO", f"Intento {self.intentos_fallidos} de 3")
            if self.intentos_fallidos >= 3:
                self.bloqueado_hasta = time.time() + 60.0
                registrar_log("CON_CODIGO", self.accion_pendiente, self.origen_pendiente,
                              "BLOQUEADO", "3 intentos fallidos consecutivos")
                self.limpiar_pendiente()
                self._notificar("Código incorrecto. Tres intentos fallidos, acción bloqueada.")
                return True
            else:
                restantes = 3 - self.intentos_fallidos
                self._notificar(f"Código incorrecto. Te quedan {restantes} intentos. Dime el código.")
                return True


_control_seguridad = None


def obtener_control(app=None):
    """Devuelve la instancia singleton de ControlSeguridad."""
    global _control_seguridad
    if _control_seguridad is None:
        _control_seguridad = ControlSeguridad(app)
    elif app and _control_seguridad.app is None:
        _control_seguridad.app = app
    return _control_seguridad


def instalar(app):
    """Instala el subsistema de control de seguridad en la aplicación."""
    cs = obtener_control(app)
    app.control_seguridad = cs
    print("[control_seguridad] Módulo de seguridad por niveles instalado.", flush=True)
