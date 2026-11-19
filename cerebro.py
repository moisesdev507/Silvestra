"""Coordinador del cerebro de Silvestra, historial de diálogo y reflexión."""
import re
import time

from config import MODELOS
from cerebro_parser import separar, _respuesta_parcial, _cortar
from cerebro_prompt import (
    DIAS,
    MESES,
    SOBRE_MI,
    cargar_alma,
    obtener_hora_panama,
    construir_prompt,
)


def ahora_texto():
    """Devuelve la fecha y hora oficial de Panamá."""
    return obtener_hora_panama()


class Cerebro:
    def __init__(self, cliente, memoria):
        self.cliente = cliente
        self.memoria = memoria
        self.historial = []
        self.modelos = list(MODELOS)
        self.ultima_reflexion = 0.0

    def reiniciar(self):
        self.historial = []

    def _podar_historial(self):
        if len(self.historial) > 16:
            self.historial = self.historial[-10:]

    def _obtener_historial_podado(self):
        """Devuelve los últimos 4 turnos recortando respuestas largas para no inflar tokens."""
        hist_reciente = self.historial[-4:]
        hist_podado = []
        for h in hist_reciente:
            c = h.get("content", "")
            if h.get("role") == "assistant" and len(c) > 150:
                c = c[:150].rsplit(" ", 1)[0] + "..."
            hist_podado.append({"role": h.get("role"), "content": c})
        return hist_podado

    def instrucciones(self, texto_actual=None):
        return construir_prompt(self.memoria, texto_actual, self._obtener_historial_podado())

    def _pedir(self, mensajes, tarea="charla"):
        import proveedores
        return proveedores.completar(mensajes, tarea=tarea)

    def responder(self, texto):
        """Devuelve (respuesta, accion, emocion). accion es None o 'nombre' / 'nombre | texto'."""
        import proveedores_cadenas as pc
        self.ultimo_texto_usuario = texto
        self.historial.append({"role": "user", "content": texto})
        prompt = self.instrucciones(texto)
        mensajes = [{"role": "system", "content": prompt}] + self._obtener_historial_podado()
        tarea = pc.clasificar_dificultad(texto)
        try:
            crudo = self._pedir(mensajes, tarea=tarea)
        except Exception as e:
            print(f"[cerebro] Excepción no controlada: {e}. Usando respuesta local.", flush=True)
            crudo = pc.respuesta_emergencia_local()
        respuesta, accion, recuerdo, emocion = separar(crudo)
        if recuerdo:
            self.memoria.recordar(recuerdo)
        self.historial.append({"role": "assistant", "content": respuesta})
        self._podar_historial()
        try:
            import aprendizaje
            aprendizaje.registrar_interaccion(texto, respuesta, emocion)
        except Exception as e:
            print(f"[aprendizaje] Error al registrar interacción: {e}", flush=True)

        turnos_u = sum(1 for m in self.historial if m.get("role") == "user")
        if turnos_u > 0 and turnos_u % 3 == 0:
            import threading
            threading.Thread(
                target=self.memoria.extraer_hechos_conversacion,
                args=(list(self.historial[-6:]), self._pedir),
                daemon=True,
            ).start()

        return respuesta, accion, emocion

    def reflexionar(self, modulo_hilos):
        """Reflexiona sobre la conversación reciente para extraer hechos y temas pendientes."""
        try:
            ultimos = self.historial[-20:]
            intervenciones = sum(1 for m in ultimos if m.get("role") == "user")
            if intervenciones < 4:
                return

            ahora = time.time()
            if ahora - self.ultima_reflexion < 600:
                return
            self.ultima_reflexion = ahora

            charla = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in ultimos)
            sistema = (
                f"Eres {self.memoria.nombre or 'Silvestra'}. Analiza la charla reciente y extrae aprendizajes duraderos.\n"
                "1. Hasta 3 líneas 'HECHO: <dato duradero sobre el usuario (gustos, rutina, proyectos)>'.\n"
                "2. Hasta 2 líneas 'PREGUNTA: <tema de seguimiento para la próxima>'.\n"
                "Sin datos sensibles ni contraseñas. Si no hay nada nuevo: NINGUNO."
            )
            mensajes = [
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Esta fue la conversación reciente:\n{charla}"},
            ]
            crudo = self._pedir(mensajes)
            for linea in (crudo or "").splitlines():
                s = linea.strip()
                if re.match(r"^HECHO\s*:\s*", s, re.I):
                    dato = re.sub(r"^HECHO\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if dato and dato.lower() not in ("ninguno", "ninguna", "nada"):
                        self.memoria.recordar(dato)
                elif re.match(r"^PREGUNTA\s*:\s*", s, re.I):
                    preg = re.sub(r"^PREGUNTA\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if preg and preg.lower() not in ("ninguno", "ninguna", "nada"):
                        modulo_hilos.anotar_pendiente(preg)

            import threading
            threading.Thread(
                target=self.memoria.extraer_hechos_conversacion,
                args=(list(ultimos), self._pedir),
                daemon=True,
            ).start()
        except Exception:
            pass
