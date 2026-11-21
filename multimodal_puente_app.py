"""Puente de ciclo de vida entre Silvestra y motores multimodales Fase 3."""
from __future__ import annotations

import os
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from multimodal_integracion_motor import MotorIntegracionMultimodal
from situacion_interpretacion_motor import MotorInterpretacionSituaciones

logger = logging.getLogger(__name__)


class SistemaMultimodalSilvestra:
    """Coordina contexto y observaciones pasivas sin acceder a widgets Qt."""

    def __init__(self, app, contexto=None, integrador=None, interprete=None):
        self._lock = threading.RLock()
        self.app = app
        self.contexto_motor = contexto
        self.permiso_camara = False
        self.permiso_microfono = False
        self.permitir_grabacion_continua = False
        self.autorizacion_externa = False
        self._activo = False
        self._cerrado = threading.Event()
        self._reintentos = 0
        self._max_reintentos = 3
        self._ultima_ventana_externa = {}
        self._pantalla = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SilvestraPantalla")
        self._pantalla_cerrada = False
        self._hilo_contexto = None
        self.integrador = integrador or MotorIntegracionMultimodal()
        self.interprete = interprete or MotorInterpretacionSituaciones(
            contexto_motor=contexto,
            iniciativa_contextual=getattr(app, "iniciativa", None),
            app=app,
            app_cola=getattr(app, "cola", None))
        from audio_evento_modelo import PoliticaPercepcionAuditiva
        from audio_percepcion_motor import MotorInteligenciaAuditiva
        self.motor_audio = MotorInteligenciaAuditiva(
            politica=PoliticaPercepcionAuditiva(permiso_microfono=False,
                permitir_grabacion_continua=False, permitir_envio_externo=False),
            voz=getattr(app, "voz", None))
        self.contexto_audio = self.motor_audio.temporal

    def iniciar(self):
        with self._lock:
            if self._activo:
                return self.estado_salud()
            self._cerrado.clear()
            self._reintentos = 0
            if self._pantalla_cerrada:
                self._pantalla = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SilvestraPantalla")
                self._pantalla_cerrada = False
            self._activo = True
            self._hilo_contexto = threading.Thread(target=self._actualizar_contexto,
                name="SilvestraContextoMultimodal", daemon=True)
            self._hilo_contexto.start()
        return self.estado_salud()

    def detener(self):
        with self._lock:
            self._activo = False
            self._cerrado.set()
        try:
            self._pantalla.shutdown(wait=False, cancel_futures=True)
            self._pantalla_cerrada = True
        except Exception:
            pass
        return self.estado_salud()

    def activar_fuente(self, fuente, permiso=False, autorizacion_externa=False,
                       permitir_grabacion_continua=False):
        nombre = str(fuente or "").lower()
        if not permiso:
            return {"ok": False, "motivo": "permiso_explicito_requerido"}
        if nombre in ("camara", "microfono"):
            if nombre == "camara":
                with self._lock:
                    self.permiso_camara = True
            else:
                with self._lock:
                    self.permiso_microfono = True
                    self.permitir_grabacion_continua = bool(permitir_grabacion_continua)
                    self.motor_audio.politica.permiso_microfono = True
                    self.motor_audio.politica.permitir_grabacion_continua = self.permitir_grabacion_continua
        elif nombre in ("vision_externa", "audio_externo"):
            if not autorizacion_externa:
                return {"ok": False, "motivo": "autorizacion_externa_requerida"}
            self.autorizacion_externa = True
        elif nombre not in ("contexto_windows", "pantalla"):
            return {"ok": False, "motivo": "fuente_desconocida"}
        return {"ok": True, "fuente": nombre}

    def desactivar_fuente(self, fuente):
        nombre = str(fuente or "").lower()
        with self._lock:
            if nombre == "camara":
                self.permiso_camara = False
            elif nombre == "microfono":
                self.permiso_microfono = False
                self.permitir_grabacion_continua = False
                self.motor_audio.politica.permiso_microfono = False
                self.motor_audio.politica.permitir_grabacion_continua = False
            elif nombre in ("vision_externa", "audio_externo"):
                self.autorizacion_externa = False
        return {"ok": True, "fuente": nombre, "activa": False}

    def estado_salud(self):
        with self._lock:
            return {"activo": self._activo, "reintentos": self._reintentos,
                    "permiso_camara": self.permiso_camara,
                    "permiso_microfono": self.permiso_microfono,
                    "permitir_grabacion_continua": self.permitir_grabacion_continua,
                    "autorizacion_externa": self.autorizacion_externa,
                    "ultima_ventana_externa": dict(self._ultima_ventana_externa)}

    @staticmethod
    def _normalizar_ventana(datos):
        if not isinstance(datos, dict):
            return None
        try:
            hwnd, pid = int(datos.get("hwnd") or 0), int(datos.get("pid") or 0)
        except (TypeError, ValueError):
            return None
        clase = str(datos.get("clase") or "")
        if not hwnd or not pid or pid == os.getpid() or clase in {
                "WorkerW", "Progman", "Shell_TrayWnd"}:
            return None
        titulo = str(datos.get("titulo") or "").strip()
        from gui_seguridad import titulo_es_sensible
        omitido = titulo_es_sensible(titulo)
        return {"hwnd": hwnd, "pid": pid,
                "titulo": "" if omitido else titulo[:180],
                "titulo_omitido": omitido,
                "ejecutable": os.path.basename(str(datos.get("ejecutable") or ""))[:180],
                "timestamp": float(datos.get("timestamp") or time.time()),
                "disponible": True}

    @staticmethod
    def _enumerar_ventana_externa():
        """Recupera la primera ventana externa válida en orden Z."""
        from multimodal_ventana_win32 import enumerar_ventana_externa
        return enumerar_ventana_externa()

    def _registrar_ventana(self, ventana, fuente="foreground"):
        if not ventana:
            logger.info("[multimodal] ventana_activa=%s titulo=%s fuente=%s",
                        "no_disponible", "omitido", fuente)
            return {}
        with self._lock:
            self._ultima_ventana_externa = ventana
        titulo_log = "[omitido por privacidad]" if ventana["titulo_omitido"] else ventana["titulo"]
        logger.info("[multimodal] ventana_activa=%s titulo=%s fuente=%s",
                    ventana["ejecutable"] or ventana["pid"], titulo_log, fuente)
        obs = self.integrador.ingerir_contexto_windows(ventana)
        self._interpretar(obs)
        return dict(ventana)

    def _actualizar_contexto(self):
        if not self._activo or self._cerrado.is_set():
            return None
        try:
            from contexto_windows import obtener_contexto_windows
            actual = self._normalizar_ventana(obtener_contexto_windows())
        except Exception:
            self._reintentos = min(self._reintentos + 1, self._max_reintentos)
            actual = None
        if actual:
            self._reintentos = 0
            return self._registrar_ventana(actual, "foreground")
        try:
            respaldo = self._normalizar_ventana(self._enumerar_ventana_externa())
        except Exception:
            respaldo = None
        if respaldo:
            return self._registrar_ventana(respaldo, "zorder")
        with self._lock:
            previa = dict(self._ultima_ventana_externa)
        if previa:
            logger.info("[multimodal] ventana_activa=%s titulo=%s fuente=%s",
                        previa.get("ejecutable") or previa.get("pid"),
                        "[omitido por privacidad]" if previa.get("titulo_omitido") else previa.get("titulo", ""),
                        "cache")
            return previa
        return self._registrar_ventana(None, "cache")

    def registrar_vision(self, resultado):
        obs = self.integrador.ingerir_vision(resultado)
        self._interpretar(obs)
        return obs

    def registrar_camara(self, resultado):
        with self._lock:
            permitido = self.permiso_camara
        if not permitido:
            return None
        obs = self.integrador.ingerir_camara(resultado)
        self._interpretar(obs)
        return obs

    def registrar_audio(self, evento):
        with self._lock:
            permitido = self.permiso_microfono
        if not permitido and getattr(evento, "fuente", "") in ("microfono", "live"):
            return None
        obs = self.integrador.ingerir_audio(evento)
        self._interpretar(obs)
        return obs

    def registrar_interfaz(self, mapa, cambio=None):
        obs = self.integrador.ingerir_interfaz(mapa, cambio)
        self._interpretar(obs)
        return obs

    def _interpretar(self, observacion):
        if observacion is None:
            return None
        situacion = self.integrador.consultar_situacion_actual().get("situacion")
        if situacion is None:
            return None
        try:
            return self.interprete.interpretar(situacion)
        except Exception:
            return None

    def consultar_entorno_actual(self, pregunta=""):
        pide_pantalla = any(x in str(pregunta).lower() for x in ("pantalla", "ventana"))
        if not pide_pantalla:
            captura = "no solicitada"
        elif threading.current_thread() is threading.main_thread():
            if self._pantalla_cerrada:
                captura = "captura no disponible; puente detenido"
            else:
                self._pantalla.submit(self._captura_temporal_segura)
                captura = "captura diferida para proteger el hilo Qt"
        else:
            try:
                captura = self._pantalla.submit(self._captura_temporal_segura).result(timeout=2.0)
            except TimeoutError:
                captura = "captura supero 2 s; se conserva solo el contexto"
        ventana = self._actualizar_contexto() or dict(self._ultima_ventana_externa)
        situacion = self.interprete.consultar_interpretacion_actual(pregunta).get("respuesta", "")
        estado_audio = "sin observaciones auditivas recientes"
        if self.contexto_audio is not None:
            try:
                estado_audio = self.contexto_audio.consultar_contexto_auditivo(pregunta).get("respuesta", estado_audio)
            except Exception:
                pass
        return {"ventana": ventana, "captura_pantalla": captura,
                "audio": estado_audio, "situacion": situacion,
                "permiso_microfono": self.permiso_microfono,
                "permiso_camara": self.permiso_camara}

    @staticmethod
    def _captura_temporal_segura():
        imagen = None
        try:
            from gui_seguridad import escritorio_de_entrada_activo, titulo_es_sensible
            from contexto_windows import obtener_contexto_windows
            contexto = obtener_contexto_windows() or {}
            if not escritorio_de_entrada_activo() or titulo_es_sensible(contexto.get("titulo", "")):
                return "captura omitida por seguridad de ventana/escritorio"
            from PIL import ImageGrab
            imagen = ImageGrab.grab()
            return f"captura efimera disponible ({imagen.width}x{imagen.height}); no almacenada ni enviada"
        except Exception:
            return "captura no disponible; se conserva solo el contexto de ventana"
        finally:
            if imagen is not None:
                try:
                    imagen.close()
                except Exception:
                    pass
