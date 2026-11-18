"""Orquestación de escenas en vivo y animación de entrada de paneles."""
from collections import deque
import io
import os
import re
import threading
import time

from PIL import Image, ImageGrab
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

import ideas
import hilos
import escenario_paneles as paneles
from escenario_anillo import PanelAnillo
from proveedores import forzar_utf8

PALABRAS_SENSIBLES = (
    "clave", "token", "password", "secreto", "contraseña", "gsk_", "sk-", "api_key",
    "config", "http", "bearer", "authorization", "tarjeta", "cuenta", "dinero", "saldo", "banco", "salud"
)


def _es_seguro(texto):
    if not texto or not isinstance(texto, str):
        return False
    t = texto.lower()
    if any(p in t for p in PALABRAS_SENSIBLES):
        return False
    if re.search(r"(gsk_[a-zA-Z0-9]+|sk-[a-zA-Z0-9]+|AQ\.[a-zA-Z0-9_]+)", texto):
        return False
    return True


class EscenasEscenario:
    """Maneja el estado y datos en vivo de cada panel de escena."""

    def __init__(self, app):
        self.app = app
        self.escena_actual = "intro"
        self.opacidad = 1.0
        self.anim_fase = 1.0
        self.transicionando = False

        self.audio_muestras = deque([0.0] * 36, maxlen=36)
        self.audio_stream = None
        self.audio_activo = False
        self.pixmap_vision = None
        self.anillo = PanelAnillo()
        self._cache_cerebro = ("Groq", "openai/gpt-oss-120b", "0.80s", "0.95s")
        self._cache_cerebro_t = 0.0
        self._cache_memoria = ("", "")
        self._cache_memoria_t = 0.0

    def fijar_escena(self, nueva_escena):
        if nueva_escena == self.escena_actual:
            return
        self.escena_actual = nueva_escena
        self.opacidad = 0.0
        self.anim_fase = 0.0
        self.transicionando = True

        if self.escena_actual == "oido":
            self._iniciar_audio()
        elif self.audio_activo:
            self._detener_audio()

        if self.escena_actual == "vision":
            self._capturar_pantalla_async()

    def avanzar(self):
        self.anillo.avanzar()
        if self.transicionando:
            self.opacidad = min(1.0, self.opacidad + 1.0 / 12.0)
            self.anim_fase = min(1.0, self.anim_fase + 1.0 / 24.0)
            if self.opacidad >= 1.0 and self.anim_fase >= 1.0:
                self.transicionando = False

    def registrar_gesto(self, datos):
        self.anillo.registrar_gesto(datos)

    def cerrar(self):
        self._detener_audio()

    def _iniciar_audio(self):
        if self.audio_activo:
            return
        try:
            import numpy as np
            import sounddevice as sd

            def audio_cb(indata, frames, time_info, status):
                amp = float(np.abs(indata).mean())
                self.audio_muestras.append(amp)

            self.audio_stream = sd.InputStream(channels=1, samplerate=16000, callback=audio_cb, blocksize=512)
            self.audio_stream.start()
            self.audio_activo = True
        except Exception:
            self.audio_activo = False

    def _detener_audio(self):
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_activo = False

    def _capturar_pantalla_async(self):
        def tarea():
            try:
                img = ImageGrab.grab()
                img.thumbnail((320, 180), Image.Resampling.BILINEAR)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=60)
                qimg = QImage.fromData(buf.getvalue(), "JPEG")
                self.app.cola.put(("escenario_captura", qimg))
            except Exception:
                pass
        threading.Thread(target=tarea, daemon=True).start()

    def fijar_captura(self, qimg):
        if isinstance(qimg, QImage):
            self.pixmap_vision = QPixmap.fromImage(qimg)

    def _leer_metricas_cerebro(self):
        ahora = time.time()
        if ahora - self._cache_cerebro_t < 2.0:
            return self._cache_cerebro
        self._cache_cerebro_t = ahora
        prov, mod, pt, tot = self._cache_cerebro
        try:
            ruta_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra.log")
            if os.path.exists(ruta_log):
                with open(ruta_log, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    tam = f.tell()
                    leer_tam = min(tam, 8192)
                    f.seek(max(0, tam - leer_tam))
                    bloque = f.read().decode("utf-8", errors="ignore")
                for linea in reversed(bloque.splitlines()[-40:]):
                    if "[tiempo] cerebro" in linea:
                        m_p = re.search(r"proveedor=([^\s]+)", linea)
                        m_m = re.search(r"modelo=([^\s]+)", linea)
                        m_pt = re.search(r"primer_token=([^\s]+)", linea)
                        m_tot = re.search(r"total=([^\s]+)", linea)
                        if m_p: prov = m_p.group(1)
                        if m_m: mod = m_m.group(1)
                        if m_pt: pt = m_pt.group(1)
                        if m_tot: tot = m_tot.group(1)
                        break
                self._cache_cerebro = (prov, mod, pt, tot)
        except Exception:
            pass
        return self._cache_cerebro

    def _leer_resumen_memoria(self):
        ahora = time.time()
        if ahora - self._cache_memoria_t < 2.0:
            return self._cache_memoria
        self._cache_memoria_t = ahora
        try:
            res_ideas = forzar_utf8(ideas.resumen())
            res_hilos = forzar_utf8(hilos.resumen())
            self._cache_memoria = (res_ideas, res_hilos)
        except Exception:
            pass
        return self._cache_memoria

    def dibujar(self, p: QPainter, panel_rect: QRectF):
        p.save()
        try:
            p.setOpacity(self.opacidad)
            esc = self.escena_actual

            if esc == "oido":
                paneles.dibujar_oido(p, panel_rect, list(self.audio_muestras), self.anim_fase)
            elif esc == "cerebro":
                prov, mod, pt, tot = self._leer_metricas_cerebro()
                paneles.dibujar_cerebro(p, panel_rect, prov, mod, pt, tot, self.anim_fase)
            elif esc == "vision":
                paneles.dibujar_vision(p, panel_rect, self.pixmap_vision, self.anim_fase)
            elif esc == "casa":
                luz = getattr(self.app.casa, "luz", False) if hasattr(self.app, "casa") else False
                vent = getattr(self.app.casa, "ventilador", False) if hasattr(self.app, "casa") else False
                puerta = getattr(self.app.casa, "puerta", False) if hasattr(self.app, "casa") else False
                paneles.dibujar_casa(p, panel_rect, luz, vent, puerta, self.anim_fase)
            elif esc == "memoria":
                hechos = [forzar_utf8(he) for he in getattr(self.app.memoria, "hechos", []) if _es_seguro(he)][-2:]
                res_ideas, res_hilos = self._leer_resumen_memoria()
                paneles.dibujar_memoria(p, panel_rect, hechos, res_ideas, res_hilos, self.anim_fase)
            elif esc == "anillo":
                self.anillo.dibujar(p, panel_rect, self.app, self.anim_fase)
            elif esc == "estudio":
                paneles.dibujar_estudio(p, panel_rect, self.anim_fase)
            elif esc == "cierre":
                paneles.dibujar_cierre(p, panel_rect, self.anim_fase)
            else:
                creador = forzar_utf8(getattr(self.app.memoria, "creador", "Moisés"))
                paneles.dibujar_intro(p, panel_rect, creador, self.anim_fase)
        finally:
            p.restore()
