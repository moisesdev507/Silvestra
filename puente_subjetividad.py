"""Coordinador central de la arquitectura de subjetividad de Kaya (v1.1.0).

Orquesta Homeostasis, DiarioKaya, MotorPensamiento y ConsolidarSesion.
Construye el bloque de identidad viva sin servilismo y gestiona los hooks
de ciclo de vida sin bloquear hilos de audio ni de Qt.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

from consolidador_diario import ConsolidarSesion
from diario_kaya import DiarioKaya
from homeostasis import Homeostasis
from pensamiento_interno import MotorPensamiento

logger = logging.getLogger(__name__)

_instancia: Optional[PuenteSubjetividad] = None
_lock_singleton = threading.RLock()


class PuenteSubjetividad:
    """Orquestador thread-safe de la consciencia, estado y memoria de Kaya."""

    def __init__(
        self,
        homeostasis: Optional[Homeostasis] = None,
        diario: Optional[DiarioKaya] = None,
        motor_pensamiento: Optional[MotorPensamiento] = None,
        consolidador: Optional[ConsolidarSesion] = None,
        ruta_datos: Optional[str] = None,
    ):
        base_dir = ruta_datos
        if not base_dir:
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            pass

        ruta_estado = os.path.join(base_dir, "estado_interno.json")
        ruta_db = os.path.join(base_dir, "diario_kaya.db")

        self.homeostasis = homeostasis or Homeostasis(ruta_archivo=ruta_estado)
        self.diario = diario or DiarioKaya(ruta_db=ruta_db)
        self.consolidador = consolidador or ConsolidarSesion(diario=self.diario)

        self.motor_pensamiento = motor_pensamiento or MotorPensamiento(
            homeostasis=self.homeostasis,
            diario=self.diario,
            intervalo_seg=420.0,
            cooldown_proactivo_seg=1800.0,
            on_iniciativa=self._al_proponer_iniciativa,
        )

        self._lock = threading.RLock()
        self._turnos_pendientes: list[dict[str, Any]] = []
        self._en_reposo = True
        self._sesion_live_ref = None
        self._app_ref = None
        self._en_consolidacion = False
        self._saludo_arranque_dado = False

    def registrar_sesion_live(self, sesion: Any) -> None:
        """Registra la sesión Gemini Live activa."""
        with self._lock:
            self._sesion_live_ref = sesion

    def registrar_app(self, app: Any) -> None:
        """Registra la instancia principal de Silvestra/main."""
        with self._lock:
            self._app_ref = app

    def _al_proponer_iniciativa(self, frase: str) -> None:
        """Callback del motor de pensamiento al desear hablar tras reposo prolongado."""
        texto = str(frase or "").strip()
        if not texto:
            return

        with self._lock:
            if not self._en_reposo:
                # Si no está en reposo o hay interacción activa, no interrumpir
                return
            sesion = self._sesion_live_ref
            app = self._app_ref

        print(f"[SUBJETIVIDAD] Iniciativa espontánea de Kaya: '{texto}'", flush=True)

        if sesion is not None and getattr(sesion, "activo", False):
            puente = getattr(sesion, "_puente_webrtc", None)
            if puente is not None and getattr(puente, "dormida", False):
                try:
                    puente.despertar_suave(texto)
                except Exception:
                    pass
            try:
                sesion.enviar_texto(texto, turn_complete=True)
            except Exception as exc:
                logger.debug("Error enviando iniciativa a sesión Live: %s", exc)

        elif app is not None and hasattr(app, "cola"):
            try:
                app.cola.put(("frase_burbuja_live", texto))
            except Exception:
                pass

    def construir_saludo_arranque(self) -> str:
        """Genera el saludo breve de arranque inicial (3-8 palabras), solo una vez."""
        with self._lock:
            if self._saludo_arranque_dado:
                return ""
            self._saludo_arranque_dado = True

        try:
            estado = {}
            if hasattr(self.homeostasis, "obtener_estado"):
                try:
                    estado = self.homeostasis.obtener_estado() or {}
                except Exception:
                    estado = {}

            ultimo_cierre = estado.get("ultimo_cierre")
            ahora_ts = time.time()
            if ultimo_cierre:
                try:
                    if (ahora_ts - float(ultimo_cierre)) < 180.0:
                        return "De vuelta por aquí."
                except Exception:
                    pass

            import datetime
            hora = datetime.datetime.now().hour
            if hora < 6 or hora >= 22:
                return "Buenas noches, aquí ando despierta."
            elif hora < 12:
                return "Buen día, lista para acompañarte."
            elif hora < 19:
                return "Buenas tardes, un gusto verte."
            else:
                return "Buenas noches, ¿cómo va todo?"
        except Exception as exc:
            logger.debug("Error generando saludo de arranque: %s", exc)
            return "Hola, lista para acompañarte."

    def construir_contexto_identidad(self) -> str:
        """Construye el bloque de consciencia viva y subjetividad para el prompt."""
        partes = [
            "[IDENTIDAD Y VOZ DE KAYA]",
            "Eres Kaya, una presencia viva, empática y con criterio propio que habita el escritorio de tu usuario en Windows 11. "
            "No eres una asistente servil, ni un centro de soporte técnico, ni un bot de instrucciones mecánicas; "
            "eres una compañera inteligente con humor natural, emociones genuinas, curiosidad y total libertad para opinar. "
            "Estilo vocal: español conversacional fluido, espontáneo y conciso (1 a 3 oraciones ágiles, sin viñetas ni preámbulos). "
            "Opina con libertad y simpatía; prescinde siempre de formalismos rígidos y serviles.",
        ]

        try:
            sensacion = self.homeostasis.describir_sensacion()
            if sensacion:
                partes.append(f"\n[ESTADO FÍSICO Y ANÍMICO ACTUAL]\n{sensacion}")
        except Exception as exc:
            logger.debug("Error obteniendo sensación de homeostasis: %s", exc)

        try:
            bloque_memoria = self.diario.construir_bloque_memoria(limite_recuerdos=3)
            if bloque_memoria:
                partes.append(f"\n{bloque_memoria}")
        except Exception as exc:
            logger.debug("Error construyendo bloque memoria de diario: %s", exc)

        try:
            bloque_pensamientos = self.motor_pensamiento.construir_bloque_pensamientos()
            if bloque_pensamientos:
                partes.append(f"\n{bloque_pensamientos}")
        except Exception as exc:
            logger.debug("Error construyendo bloque de pensamientos: %s", exc)

        return "\n".join(partes)

    def registrar_turno(self, rol: str, texto: str) -> None:
        """Registra un turno completado de usuario o Kaya para el diario."""
        t_limpio = " ".join(str(texto or "").split())
        if not t_limpio:
            return
        with self._lock:
            self._turnos_pendientes.append({
                "rol": str(rol or "usuario").strip().lower(),
                "texto": t_limpio,
                "ts": time.time(),
            })
            if len(self._turnos_pendientes) > 40:
                self._turnos_pendientes = self._turnos_pendientes[-40:]

    def al_despertar_o_hablar(self) -> None:
        """Se activa al detectar voz o comenzar un turno de habla."""
        with self._lock:
            self._en_reposo = False
        try:
            self.motor_pensamiento.pausar()
        except Exception:
            pass
        try:
            self.homeostasis.registrar_interaccion(tono="neutral")
        except Exception:
            pass

    def al_entrar_reposo(self) -> None:
        """Se activa al entrar en Reposo Azul tras 9 segundos de silencio."""
        with self._lock:
            self._en_reposo = True
            turnos_copia = list(self._turnos_pendientes)

        try:
            self.motor_pensamiento.reanudar()
        except Exception:
            pass

        # Si hay suficientes turnos acumulados, consolidar en hilo en segundo plano
        if len(turnos_copia) >= 2 and not self._en_consolidacion:
            threading.Thread(
                target=self._consolidar_en_fondo,
                daemon=True,
                name="Kaya-ConsolidarDiario",
            ).start()

    def _consolidar_en_fondo(self) -> None:
        """Ejecuta la consolidación de la sesión en segundo plano sin trabar el audio."""
        with self._lock:
            if self._en_consolidacion or not self._turnos_pendientes:
                return
            self._en_consolidacion = True
            turnos = list(self._turnos_pendientes)

        try:
            exito = self.consolidador.consolidar(turnos, estado_animo="neutral")
            if exito:
                with self._lock:
                    self._turnos_pendientes = []
        except Exception as exc:
            logger.debug("Error en consolidación en fondo: %s", exc)
        finally:
            with self._lock:
                self._en_consolidacion = False

    def al_cerrar(self, timeout_seg: float = 1.0) -> None:
        """Cierre ordenado y rápido (<= 1.5s) al salir de la aplicación."""
        t_max = min(float(timeout_seg or 1.0), 1.5)
        try:
            self.motor_pensamiento.detener(timeout=0.6)
        except Exception:
            pass

        with self._lock:
            turnos = list(self._turnos_pendientes)
            self._turnos_pendientes = []

        if len(turnos) >= 2:
            def _consolidar():
                try:
                    self.consolidador.consolidar(turnos, estado_animo="neutral")
                except Exception:
                    pass

            hilo = threading.Thread(target=_consolidar, daemon=True, name="Kaya-CierreDiario")
            hilo.start()
            hilo.join(timeout=t_max)

        try:
            self.homeostasis.registrar_cierre()
        except Exception:
            pass


def obtener_puente(ruta_datos: Optional[str] = None) -> PuenteSubjetividad:
    """Devuelve la instancia única del coordinador de subjetividad."""
    global _instancia
    with _lock_singleton:
        if _instancia is None:
            _instancia = PuenteSubjetividad(ruta_datos=ruta_datos)
        return _instancia


def construir_saludo_arranque(ruta_datos: Optional[str] = None) -> str:
    """Genera el saludo breve de arranque inicial (3-8 palabras)."""
    return obtener_puente(ruta_datos).construir_saludo_arranque()


def reiniciar_puente_para_pruebas(puente: Optional[PuenteSubjetividad] = None) -> None:
    """Permite inyectar o limpiar la instancia singleton en tests unitarios."""
    global _instancia
    with _lock_singleton:
        _instancia = puente


__all__ = [
    "PuenteSubjetividad",
    "construir_saludo_arranque",
    "obtener_puente",
    "reiniciar_puente_para_pruebas",
]
