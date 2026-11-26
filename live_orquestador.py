"""Coordinador unificado para alternar entre espera local y sesión Gemini Live en main.py.

Gestiona las transiciones en PortAudio y sincroniza el orbe de cara_qt:
1. Inicia en espera local por palabra clave con Silero VAD y Vosk (0 gasto de cuota).
2. Al invocar 'Kaya', abre sesión Gemini Live si hay clave y no hay enfriamiento de cuota.
3. Si Live falla o la cuota se agota (429), conmuta de inmediato al motor clásico (Groq/Kaya).
4. Cierra limpiamente la sesión Live a los 9 segundos de silencio volviendo a espera local.
"""
import os
import queue
import threading
import time
from typing import Optional

import despertar_local
import estado_emocional_kaya
import live_audio
import live_motor


class CoordinadorLiveSilvestra:
    """Controla la sesión Live dentro del contexto de Silvestra (main.py)."""

    def __init__(self, app):
        self.app = app
        try:
            import cerebro_sistema2
            cerebro_sistema2.configurar_app(app)
        except Exception:
            pass
        self.sesion_live: Optional[live_motor.SesionKayaLive] = None
        self.despertar_local: Optional[despertar_local.EscuchaDespertarLocal] = None
        self._bloqueo = threading.RLock()
        self._generacion = 0
        self._pausado_por_live = False
        self._saludo_inicial_enviado = False
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

    @staticmethod
    def _detener_sesion_seguro(sesion):
        """Cierra una sesión Live sin propagar fallos al hilo que la cierra."""
        try:
            sesion.detener()
        except Exception as exc:
            print(f"[COORDINADOR] Cierre Live en segundo plano: {exc}", flush=True)

    def actualizar_modo_voz(self, modo: str):
        """Conmuta en caliente: el estado cambia ya, el cierre pesado va a fondo."""
        with self._bloqueo:
            habilitado = bool(
                live_audio.obtener_api_key()
                and str(modo).strip().lower() != "clasico"
                and os.environ.get("KAYA_MODO", "").strip().lower() != "clasico"
            )
            self.modo_live_habilitado = habilitado
            sesion = self.sesion_live
            self.sesion_live = None
            self._generacion += 1
            gen = self._generacion
        print(f"[COORDINADOR] Modo voz configurado: '{modo}' (live={self.modo_live_habilitado})", flush=True)
        threading.Thread(
            target=self._conmutar_en_fondo,
            args=(sesion, habilitado, gen),
            daemon=True,
            name="motor-switch",
        ).start()

    def _conmutar_en_fondo(self, sesion, habilitado, gen):
        """Prepara el motor destino sin tocar Qt ni bloquear el hilo principal."""
        if sesion is not None:
            self._detener_sesion_seguro(sesion)
        with self._bloqueo:
            if gen != self._generacion:
                return
        try:
            import voz_ws
            voz_ws.detener()
            if not habilitado:
                self.detener_despertar_local()
            if habilitado:
                self._pausar_captura_local()
            else:
                self._reanudar_captura_local()
        except Exception as exc:
            print(f"[COORDINADOR] Preparación de motor clásico/Live: {exc}", flush=True)

    def _al_estado(self, estado: str):
        cara = getattr(self.app, "cara", None)
        if not cara:
            return
        if estado == "escuchando":
            self.app.cola.put(("cara_metodo", ("poner_escuchando", True)))
            self.app.cola.put(("cara_metodo", ("poner_hablando", False)))
            self.app.cola.put(("micro_live_estado", False))
        elif estado == "hablando":
            self.app.cola.put(("cara_metodo", ("poner_hablando", True)))
            self.app.cola.put(("cara_metodo", ("poner_escuchando", False)))
        elif estado in ("reposo", "en_reposo", "conectando"):
            self.app.cola.put(("cara_metodo", ("poner_hablando", False)))
            self.app.cola.put(("cara_metodo", ("poner_escuchando", False)))
            self.app.cola.put(("micro_live_estado", True))

    def _al_nivel_voz(self, nivel: float):
        cola = getattr(self.app, "cola", None)
        if cola is not None:
            cola.put(("nivel_voz_live", float(nivel)))

    def _a_transcripcion(self, rol: str, texto: str):
        if rol == "kaya" and texto:
            self.app.cola.put(("frase_burbuja_live", texto))

    def aislar_motores_locales(self):
        """Pausa invocación, Deepgram y Celeste antes de precalentar Live."""
        self._pausar_captura_local()

    def sincronizar_por_cuota(self):
        """Reanuda los motores locales solo si Live entró en enfriamiento 429."""
        if (self._pausado_por_live and not self.es_modo_principal()
                and live_motor.esta_en_enfriamiento_cuota()):
            self._reanudar_captura_local()

    def _pausar_captura_local(self):
        self._pausado_por_live = True
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
        voz = getattr(self.app, "voz", None)
        if voz and hasattr(voz, "pausar"):
            try:
                voz.pausar()
            except Exception:
                pass

    def _reanudar_captura_local(self):
        self._pausado_por_live = False
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
        voz = getattr(self.app, "voz", None)
        if voz and hasattr(voz, "reanudar"):
            try:
                voz.reanudar()
            except Exception:
                pass

    def _al_cierre_automatico(self):
        """Tras 9 s sin voz: reposo Live con wake-word local y 0 tokens."""
        print("[COORDINADOR] Reposo Live: escuchando 'Kaya' en local (0 tokens).", flush=True)
        with self._bloqueo:
            self.sesion_live = None
        self._iniciar_despertar_local()

    def _iniciar_despertar_local(self):
        with self._bloqueo:
            actual = self.despertar_local
            if actual is not None and actual.activa:
                return
            wake = despertar_local.EscuchaDespertarLocal(self._al_despertar_local)
            self.despertar_local = wake
        if not wake.iniciar():
            with self._bloqueo:
                if self.despertar_local is wake:
                    self.despertar_local = None

    def detener_despertar_local(self):
        with self._bloqueo:
            wake = self.despertar_local
            self.despertar_local = None
        if wake is not None:
            try:
                wake.detener()
            except Exception as exc:
                print(f"[COORDINADOR] Cierre wake local: {exc}", flush=True)

    def _al_despertar_local(self, texto, audio_inicial):
        """El hilo monitor del wake-word reactiva Live sin tocar el orbe."""
        print("[COORDINADOR] 'Kaya' detectado en local: reconectando Gemini Live.", flush=True)

        def _reactivar():
            wake = self.despertar_local
            if self.intentar_activar_live("", audio_inicial=audio_inicial, wake=wake):
                self.app.cola.put(("micro_live_estado", False))
            self.detener_despertar_local()

        threading.Thread(target=_reactivar, daemon=True, name="live-wake").start()

    def alternar_microfono(self) -> bool:
        """Acción principal del orbe: cerrar o abrir el micrófono Live."""
        with self._bloqueo:
            sesion = self.sesion_live
        if sesion is not None and sesion.activo:
            self.detener_despertar_local()
            self._detener_sesion_seguro(sesion)
            with self._bloqueo:
                if self.sesion_live is sesion:
                    self.sesion_live = None
            self._iniciar_despertar_local()
            self.app.cola.put(("micro_live_estado", True))
            return False
        self.detener_despertar_local()
        if self.intentar_activar_live(""):
            self.app.cola.put(("micro_live_estado", False))
            return True
        self._iniciar_despertar_local()
        return False

    def precalentar_en_paralelo(self):
        """Inicia la sesión Live en fondo de inmediato mientras cara_qt termina de dibujar."""
        if not self.es_modo_principal() or live_motor.esta_en_enfriamiento_cuota():
            return
        # Un único saludo: main.saludar() no debe repetir esta instrucción.
        self._saludo_inicial_enviado = True
        def _arranque_fondo():
            with self._bloqueo:
                if self.sesion_live and self.sesion_live.activo:
                    return
                print("[COORDINADOR] Pre-calentando sesión Gemini Live en paralelo...", flush=True)
                self.intentar_activar_live("¡Hola Kaya! Ya encendió el equipo, saluda breve.")
        threading.Thread(target=_arranque_fondo, daemon=True, name="live-precalentar").start()

    def intentar_activar_live(self, orden_inicial: str = "", audio_inicial=None, wake=None) -> bool:
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

            if wake is not None and hasattr(wake, "drenar_posteriores"):
                extra = wake.drenar_posteriores()
                if extra:
                    audio_inicial = list(audio_inicial or []) + extra

            ok = self.sesion_live.iniciar()
            if ok:
                # El motor decide si hubo >2h; nunca bloquea ni toca Qt.
                estado_emocional_kaya.registrar_si_disponible("despertar_tras_abandono")
            if not ok:
                self.sesion_live = None
                self._saludo_inicial_enviado = False
                self._reanudar_captura_local()
                return False

            if audio_inicial:
                for frame in audio_inicial:
                    try:
                        self.sesion_live.cola_audio_entrada.put_nowait(frame)
                    except queue.Full:
                        break

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
        """Cierre de aplicación: desengancha la sesión Live y la cierra en fondo."""
        self.detener_despertar_local()
        with self._bloqueo:
            sesion = self.sesion_live
            self.sesion_live = None
            self._generacion += 1
        if sesion is not None:
            threading.Thread(
                target=self._detener_sesion_seguro,
                args=(sesion,),
                daemon=True,
                name="live-cierre",
            ).start()


def despachar_evento_live(app, tipo: str, texto) -> bool:
    """Atiende eventos de UI y sincronización visual de Live."""
    if tipo == "toggle_micro_live":
        coordinator = getattr(app, "coordinador_live", None)
        if coordinator is not None:
            threading.Thread(
                target=coordinator.alternar_microfono,
                daemon=True, name="orbe-mic",
            ).start()
        return True
    if tipo == "nivel_voz_live":
        cara = getattr(app, "cara", None)
        if cara is not None:
            nivel = float(texto)
            cara.nivel_volumen = nivel
            voz = getattr(cara, "_ref_voz", None) or getattr(app, "voz", None)
            if voz is not None and hasattr(voz, "nivel_volumen"):
                voz.nivel_volumen = nivel
        return True
    if tipo == "micro_live_estado":
        cara = getattr(app, "cara", None)
        if cara is not None:
            cerrado = bool(texto)
            cara.micro_live_cerrado = cerrado
            cara.poner_escuchando(not cerrado)
            cara.update()
        return True
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
