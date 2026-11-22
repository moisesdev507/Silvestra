"""Módulo de Mentora Socrática y Consolidación Cognitiva para Silvestra / Lyris.

Permite activar un modo de pair-programming donde Lyris actúa como una ingeniera
senior exigente y pedagógica, inyectando directivas socráticas en el prompt y
consolidando los temas técnicos trabajados directamente en el Grafo de Conocimiento.
"""
import os
import re
import threading
import time
import unicodedata

_bloqueo = threading.RLock()


def _normalizar(texto):
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class GestorMentor:
    """Gestiona el estado y comportamiento socrático de Lyris."""

    # Directiva socrática compacta (exactamente 219 caracteres <= 220)
    DIRECTIVA_SOCRATICA = (
        "[MODO MENTORA: Actúa como ingeniera senior socrática. Analiza arquitectura "
        "y código; señala fallos y buenas prácticas; en vez de código masticado, "
        "haz 1 pregunta guía que oriente al dueño a deducir la solución óptima.]"
    )

    def __init__(self):
        self._activo = False
        self._sesion_ts = 0.0
        self._temas = []

    def esta_activo(self):
        with _bloqueo:
            return self._activo

    def activar(self, motivo=""):
        with _bloqueo:
            self._activo = True
            self._sesion_ts = time.time()
            self._temas = []
        return "Modo mentora socrática activado. Analicemos tu arquitectura y código paso a paso sin prisas."

    def desactivar(self):
        with _bloqueo:
            self._activo = False
        return "Modo mentora desactivado. Volvemos al modo de asistencia habitual."

    def registrar_tema(self, tema):
        if not tema:
            return
        with _bloqueo:
            if tema not in self._temas:
                self._temas.append(str(tema).strip())

    def obtener_directiva_prompt(self):
        with _bloqueo:
            if not self._activo:
                return ""
            return self.DIRECTIVA_SOCRATICA

    def consolidar_aprendizaje_sesion(self, app=None, creador="Moisés"):
        """Registra los avances técnicos trabajados en el Grafo de Conocimiento."""
        detalles = []
        try:
            import cerebro_trabajo
            mem = cerebro_trabajo.obtener_memoria_trabajo()
            ult_arch = mem.get("ultimo_archivo")
            ult_hab = mem.get("ultima_habilidad")
        except Exception:
            ult_arch, ult_hab = None, None

        try:
            import cerebro_grafo
            cerebro_grafo.inicializar_grafo()
            if ult_arch:
                nom_arch = os.path.basename(ult_arch)
                cerebro_grafo.registrar_hecho(creador, "trabajo_en", nom_arch, tipo_sujeto="usuario", tipo_objeto="archivo")
                detalles.append(f"archivo {nom_arch}")
            if ult_hab:
                cerebro_grafo.registrar_hecho(creador, "domina_habilidad", ult_hab, tipo_sujeto="usuario", tipo_objeto="habilidad")
                detalles.append(f"habilidad {ult_hab}")
            with _bloqueo:
                for t in self._temas:
                    cerebro_grafo.registrar_hecho(creador, "estudio_tema", t, tipo_sujeto="usuario", tipo_objeto="concepto")
                    detalles.append(f"tema {t}")
        except Exception:
            pass

        if detalles:
            items_txt = ", ".join(detalles)
            return f"He consolidado los avances de la sesión en tu grafo de conocimiento: registré {items_txt}."
        return "He consolidado la sesión en tu grafo de conocimiento. Sigamos reforzando buenas prácticas."


# Instancia singleton
_gestor_mentor = GestorMentor()


def obtener_gestor_mentor():
    return _gestor_mentor


def obtener_directiva_mentor():
    """Retorna la directiva socrática compacta si el modo está encendido."""
    return _gestor_mentor.obtener_directiva_prompt()


def es_modo_mentor_activo():
    return _gestor_mentor.esta_activo()


def activar_mentor():
    return _gestor_mentor.activar()


def desactivar_mentor():
    return _gestor_mentor.desactivar()


def consolidar_aprendizaje(app=None, creador="Moisés"):
    return _gestor_mentor.consolidar_aprendizaje_sesion(app=app, creador=creador)


def detectar_orden_mentora(texto):
    """Detecta órdenes explícitas de activar, desactivar o consolidar modo mentora.
    
    Retorna tupla: (tipo_accion, respuesta_texto, emocion) o None si no coincide.
    """
    if not texto:
        return None
    norm = _normalizar(texto)

    # 1. Activación
    patrones_activar = [
        r"\b(?:activa(?:r)?|inicia(?:r)?|pon(?:er)?|entra(?:r)?\s+en)\s+(?:el\s+)?modo\s+(?:mentora|programacion|socratico|estudio)\b",
        r"\b(?:ensename|enseneme|guia(?:me)?)\s+como\s+mentora\b",
        r"^(?:modo\s+mentora|modo\s+programacion)$",
    ]
    for p in patrones_activar:
        if re.search(p, norm):
            msg = _gestor_mentor.activar()
            return ("activar", msg, "concentrada")

    # 2. Desactivación
    patrones_desactivar = [
        r"\b(?:desactiva(?:r)?|apaga(?:r)?|quita(?:r)?|sal(?:ir)?\s+de(?:l)?)\s+(?:el\s+)?modo\s+(?:mentora|programacion|socratico)\b",
        r"\b(?:vuelve\s+a(?:l)?|pon(?:er)?)\s+modo\s+normal\b",
        r"^(?:modo\s+normal|desactiva\s+mentora)$",
    ]
    for p in patrones_desactivar:
        if re.search(p, norm):
            msg = _gestor_mentor.desactivar()
            return ("desactivar", msg, "calida")

    # 3. Consolidación
    patrones_consolidar = [
        r"\b(?:consolida(?:r)?|guarda(?:r)?)\s+(?:el\s+)?(?:aprendizaje|lo\s+aprendido|la\s+sesion)\b",
        r"\bque\s+aprendimos\s+hoy\b",
    ]
    for p in patrones_consolidar:
        if re.search(p, norm):
            msg = _gestor_mentor.consolidar_aprendizaje_sesion()
            return ("consolidar", msg, "orgullosa")

    return None
