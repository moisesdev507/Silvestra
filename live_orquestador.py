"""Coordinador unificado para alternar entre espera local y sesión Gemini Live en main.py.

Gestiona las transiciones en PortAudio y sincroniza el orbe de cara_qt:
1. Inicia en espera local por palabra clave con Silero VAD y Vosk (0 gasto de cuota).
2. Al invocar 'Kaya', abre sesión Gemini Live si hay clave y no hay enfriamiento de cuota.
3. Si Live falla o la cuota se agota (429), conmuta de inmediato al motor clásico (Groq/Celeste).
4. Cierra limpiamente la sesión Live a los 9 segundos de silencio volviendo a espera local.
"""
import os
import threading
import time
from typing import Optional

import live_audio
import live_motor


class CoordinadorLiveSilvestra:
    """Controla la sesión Live dentro del contexto de Silvestra (main.py)."""

    def __init__(self, app):
        self.app = app
        self.sesion_live: Optional[live_motor.SesionKayaLive] = None
        self._bloqueo = threading.RLock()
        self.modo_live_habilitado = bool(
            live_audio.obtener_api_key()
            and self.modo_voz_configurado() != "clasico"
            and os.environ.get("KAYA_MODO", "").strip().lower() != "clasico"
        )

    def modo_voz_configurado(self) -> str:
        try:
            import estado
            return str(estado.cargar().get("modo_voz_principal", "gemini_live")).strip().lower()
        except Exception:
            return "gemini_live"

    def es_modo_principal(self) -> bool:
        return bool(
            self.modo_live_habilitado
            and self.modo_voz_configurado() != "clasico"
            and not live_motor.esta_en_enfriamiento_cuota()
        )

    def actualizar_modo_voz(self, modo: str):
        with self._bloqueo:
            habilitado = bool(
                live_audio.obtener_api_key()
                and str(modo).strip().lower() != "clasico"
                and os.environ.get("KAYA_MODO", "").strip().lower() != "clasico"
            )
            self.modo_live_habilitado = habilitado
            if not habilitado and self.sesion_live:
                try:
                    self.sesion_live.detener()
                except Exception:
                    pass
                self.sesion_live = None
                self._reanudar_captura_local()
        print(f"[COORDINADOR] Modo voz configurado: '{modo}' (live={self.modo_live_habilitado})", flush=True)

    def _al_estado(self, estado: str):
        cara = getattr(self.app, "cara", None)
        if not cara:
            return
        if estado == "escuchando":
            self.app.cola.put(("cara_metodo", ("poner_escuchando", True)))
            self.app.cola.put(("cara_metodo", ("poner_hablando", False)))
        elif estado == "hablando":
            self.app.cola.put(("cara_metodo", ("poner_hablando", True)))
            self.app.cola.put(("cara_metodo", ("poner_escuchando", False)))
        elif estado in ("reposo", "conectando"):
            self.app.cola.put(("cara_metodo", ("poner_hablando", False)))
            self.app.cola.put(("cara_metodo", ("poner_escuchando", False)))

    def _al_nivel_voz(self, nivel: float):
        cara = getattr(self.app, "cara", None)
        if cara:
            cara.nivel_volumen = nivel

    def _a_transcripcion(self, rol: str, texto: str):
        if rol == "kaya" and texto:
            self.app.cola.put(("frase_burbuja_live", texto))

    def _pausar_captura_local(self):
        inv = getattr(self.app, "invocacion", None)
        if inv and hasattr(inv, "pausar"):
            try:
                inv.pausar()
            except Exception:
                pass
        oid = getattr(self.app, "oido", None)
        if oid and hasattr(oid, "pausar"):
            try:
                oid.pausar()
            except Exception:
                pass

    def _reanudar_captura_local(self):
        oid = getattr(self.app, "oido", None)
        if oid and hasattr(oid, "reanudar"):
            try:
                oid.reanudar()
            except Exception:
                pass
        inv = getattr(self.app, "invocacion", None)
        if inv and hasattr(inv, "reanudar"):
            try:
                inv.reanudar()
            except Exception:
                pass

    def _al_cierre_automatico(self):
        """Invocado por el watchdog de 9 segundos de silencio o cierre de Live."""
        print("[COORDINADOR] Regresando a escucha local por palabra clave.", flush=True)
        with self._bloqueo:
            self.sesion_live = None
        self._reanudar_captura_local()

    def precalentar_en_paralelo(self):
        """Inicia la sesión Live en fondo de inmediato mientras cara_qt termina de dibujar."""
        if not self.es_modo_principal() or live_motor.esta_en_enfriamiento_cuota():
            return
        def _arranque_fondo():
            with self._bloqueo:
                if self.sesion_live and self.sesion_live.activo:
                    return
                print("[COORDINADOR] Pre-calentando sesión Gemini Live en paralelo...", flush=True)
                self.intentar_activar_live("¡Hola Kaya! Ya encendió el equipo, saluda breve.")
        threading.Thread(target=_arranque_fondo, daemon=True, name="live-precalentar").start()

    def intentar_activar_live(self, orden_inicial: str = "") -> bool:
        """Intenta activar Gemini Live al detectar invocación. Devuelve True si Live tomó el turno."""
        if not self.modo_live_habilitado or self.modo_voz_configurado() == "clasico" or live_motor.esta_en_enfriamiento_cuota():
            return False

        with self._bloqueo:
            if self.sesion_live and self.sesion_live.activo:
                if orden_inicial:
                    self.sesion_live.enviar_texto(orden_inicial)
                return True

            self._pausar_captura_local()

            self.sesion_live = live_motor.SesionKayaLive(
                on_estado=self._al_estado,
                on_nivel_voz=self._al_nivel_voz,
                on_transcripcion=self._a_transcripcion,
                on_cierre_automatico=self._al_cierre_automatico,
                orden_inicial=orden_inicial,
            )

            ok = self.sesion_live.iniciar()
            if not ok:
                self.sesion_live = None
                self._reanudar_captura_local()
                return False

            print("[COORDINADOR] Sesión Gemini Live iniciada exitosamente.", flush=True)
            return True

    def enviar_orden(self, texto: str) -> bool:
        """Envía una orden por texto a la sesión Live en curso."""
        with self._bloqueo:
            if self.sesion_live and self.sesion_live.activo:
                return self.sesion_live.enviar_texto(texto)
        return False

    def esta_live_activo(self) -> bool:
        with self._bloqueo:
            return bool(self.sesion_live and self.sesion_live.activo)

    def cerrar(self):
        with self._bloqueo:
            if self.sesion_live:
                try:
                    self.sesion_live.detener()
                except Exception:
                    pass
                self.sesion_live = None
        self._reanudar_captura_local()


def despachar_evento_live(app, tipo: str, texto) -> bool:
    """Atiende eventos de UI y sincronización visual de Live."""
    if tipo == "cara_metodo":
        if isinstance(texto, (tuple, list)) and len(texto) >= 2:
            metodo, val = texto[0], texto[1]
            c = getattr(app, "cara", None)
            if c and hasattr(c, metodo):
                try:
                    getattr(c, metodo)(val)
                except Exception:
                    pass
        return True
    if tipo in ("poner_hablando", "poner_escuchando"):
        c = getattr(app, "cara", None)
        if c and hasattr(c, tipo):
            try:
                getattr(c, tipo)(bool(texto))
            except Exception:
                pass
        return True
    if tipo == "frase_burbuja_live":
        if hasattr(app, "cara") and app.cara:
            app.cara.decir(str(texto), 5000, con_voz=False)
        return True
    return False
