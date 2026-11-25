"""Coordinador unificado para Kaya Live y modo clásico de Silvestra.

Gestiona las transiciones atómicas en PortAudio entre:
1. Modo Reposo (Vosk local buscando 'kaya' en cualquier posición).
2. Modo Live (Gemini Live API con voz Achernar y tools completas).
3. Fallback automático al Modo Clásico (Groq/Piper) ante cuota agotada o fallos.
4. Coordinación sin choques para avisos de recordatorios e iniciativa.
"""
import asyncio
import os
import queue
import threading
import time
from typing import Callable, Optional

import audio_lock
import cara_qt
import invocacion_lyris
import kaya_live_audio
import kaya_live_conexion
import kaya_live_nucleo
import kaya_live_puente
from kaya_live_app import PuenteLiveQt


class OrquestadorKayaLive:
    """Controla el ciclo unificado sobre la ventana Cara de PySide6."""

    def __init__(
        self,
        app_clasica,
        cara: cara_qt.Cara,
        modelo: str = kaya_live_nucleo.MODELO_DEFECTO,
        voz: str = kaya_live_nucleo.VOZ_DEFECTO,
        timeout_silencio: float = kaya_live_nucleo.TIMEOUT_SILENCIO_DEFECTO,
        iniciar_en_live: bool = True,
    ):
        self.app = app_clasica
        self.cara = cara
        self.modelo = modelo
        self.voz = voz
        self.timeout_silencio = timeout_silencio
        self.iniciar_en_live = iniciar_en_live

        self.sesion: Optional[kaya_live_nucleo.SesionKayaLive] = None
        self.puente: Optional[PuenteLiveQt] = None
        self.loop_async: Optional[asyncio.AbstractEventLoop] = None
        self.hilo_async: Optional[threading.Thread] = None

        self._bloqueo = threading.RLock()
        self._modo_actual = "iniciando"  # "live", "reposo_vosk", "clasico"
        self._cerrando = False
        self._silencio_total = False
        self._hilo_vigilante_vosk = None
        self._parada_vosk = threading.Event()

        kaya_live_puente.registrar_callback_reposo(self._al_solicitar_reposo_desde_live)

    def iniciar(self):
        """Inicia el orquestador según la configuración inicial."""
        if self.iniciar_en_live:
            print("[ORQUESTADOR] Iniciando en Modo Live interactivo...", flush=True)
            self.activar_live()
        else:
            print("[ORQUESTADOR] Iniciando en Modo Reposo local (esperando 'Kaya')...", flush=True)
            self.entrar_en_reposo_vosk()

    def activar_live(self, texto_inicial: str = ""):
        """Activa la sesión Live liberando previamente el micrófono de Vosk."""
        with self._bloqueo:
            if self._cerrando:
                return
            self._modo_actual = "live"
            self._detener_vigilante_vosk()

        time.sleep(0.15)

        with self._bloqueo:
            self._detener_sesion_live_interna()
            self.sesion = kaya_live_nucleo.SesionKayaLive(
                modelo=self.modelo,
                voz=self.voz,
                timeout_silencio=self.timeout_silencio,
                saludar_al_iniciar=(not bool(texto_inicial)),
            )
            cb_orig_estado = self.sesion.on_estado

            def _on_estado_orquestador(est):
                if cb_orig_estado:
                    cb_orig_estado(est)
                if est in ("reposo", "error") and self._modo_actual == "live" and not self._cerrando:
                    threading.Thread(target=self._post_live_reposo, daemon=True).start()

            self.sesion.on_estado = _on_estado_orquestador
            self.puente = PuenteLiveQt(self.cara, self.sesion)

            self.cara.mostrar()
            self.cara.poner_escuchando(True)

            self.hilo_async = threading.Thread(
                target=self._hilo_live_async,
                args=(texto_inicial,),
                name="orquestador-live-async",
                daemon=True,
            )
            self.hilo_async.start()

    def _hilo_live_async(self, texto_inicial: str = ""):
        self.loop_async = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop_async)
        try:
            if texto_inicial:
                async def _tarea_con_orden():
                    t_ej = asyncio.create_task(self.sesion.ejecutar())
                    for _ in range(40):
                        if getattr(self.sesion, "_session", None) is not None:
                            break
                        await asyncio.sleep(0.05)
                    if getattr(self.sesion, "_session", None) is not None:
                        try:
                            from google.genai import types
                            await self.sesion._session.send(input=texto_inicial, end_of_turn=True)
                        except Exception as e:
                            print(f"[ORQUESTADOR] No se pudo inyectar orden inicial: {e}", flush=True)
                    await t_ej

                self.loop_async.run_until_complete(_tarea_con_orden())
            else:
                self.loop_async.run_until_complete(self.sesion.ejecutar())
        except Exception as exc:
            if not self._cerrando:
                print(f"[ORQUESTADOR] Excepción en bucle Live: {exc}", flush=True)
                if kaya_live_conexion.es_error_cuota(exc):
                    print("[ORQUESTADOR] Error de cuota 429 detectado. Fallback a clásico.", flush=True)
                    self.activar_fallback_clasico(f"Cuota Live agotada: {exc}")
        finally:
            try:
                pendientes = asyncio.all_tasks(self.loop_async)
                for t in pendientes:
                    t.cancel()
                if pendientes:
                    self.loop_async.run_until_complete(asyncio.gather(*pendientes, return_exceptions=True))
                self.loop_async.close()
            except Exception:
                pass

    def _post_live_reposo(self):
        time.sleep(0.3)
        with self._bloqueo:
            if self._modo_actual == "live" and not self._cerrando and not self._silencio_total:
                self.entrar_en_reposo_vosk()

    def entrar_en_reposo_vosk(self):
        """Pasa a reposo cerrando Live y activando la escucha local de 'Kaya'."""
        with self._bloqueo:
            self._modo_actual = "reposo_vosk"
            self._detener_sesion_live_interna()

        time.sleep(0.15)
        self.cara.poner_escuchando(False)
        self.cara.poner_hablando(False)
        self.cara.nivel_volumen = 0.0

        with self._bloqueo:
            if not self._silencio_total and not self._cerrando:
                self._iniciar_vigilante_vosk()

    def _al_solicitar_reposo_desde_live(self):
        if self.sesion:
            for _ in range(60):
                if getattr(self.sesion, "_cola_salida", None) and self.sesion._cola_salida.empty():
                    break
                time.sleep(0.05)
            time.sleep(0.3)
            self.sesion.detener()
        self.entrar_en_reposo_vosk()

    def _iniciar_vigilante_vosk(self):
        self._parada_vosk.clear()
        if self._hilo_vigilante_vosk and self._hilo_vigilante_vosk.is_alive():
            return
        self._hilo_vigilante_vosk = threading.Thread(
            target=self._bucle_vigilante_vosk,
            name="orquestador-vigilante-vosk",
            daemon=True,
        )
        self._hilo_vigilante_vosk.start()

    def _detener_vigilante_vosk(self):
        self._parada_vosk.set()
        if hasattr(self.app, "oido") and self.app.oido:
            try:
                self.app.oido.liberar_microfono()
            except Exception:
                pass
        h = self._hilo_vigilante_vosk
        if h and h.is_alive() and threading.current_thread() is not h:
            try:
                h.join(timeout=0.4)
            except Exception:
                pass
        self._hilo_vigilante_vosk = None

    def _bucle_vigilante_vosk(self):
        print("[ORQUESTADOR] Escucha en reposo activa. Di 'Kaya' para despertar.", flush=True)
        while not self._parada_vosk.is_set() and not self._cerrando:
            if self._modo_actual != "reposo_vosk":
                break
            try:
                oido_inst = getattr(self.app, "oido", None)
                if oido_inst is None:
                    time.sleep(0.5)
                    continue

                texto = oido_inst.escuchar(rec_vosk=getattr(self.app, "rec_vosk", None))
                if not texto or self._parada_vosk.is_set():
                    continue

                detectado, alias, orden = invocacion_lyris.detectar(texto)
                if detectado:
                    print(f"[ORQUESTADOR] 'Kaya' detectada ('{texto}'). Despertando Live...", flush=True)
                    self.activar_live(texto_inicial=orden)
                    break
            except Exception:
                if not self._parada_vosk.is_set():
                    time.sleep(0.3)
                break

    # ------------------ Coordinación de Avisos / Recordatorios ------------------

    def coordinar_aviso_externo(self, texto_aviso: str, es_recordatorio: bool = False) -> bool:
        """Coordina avisos de recordatorios e iniciativa evitando colisiones y doble voz."""
        if not texto_aviso:
            return False

        if self._modo_actual == "live" and self.sesion and self.loop_async:
            # En Live: mostrar burbuja e inyectar en Gemini para voz Achernar (cero TTS local)
            try:
                self.cara.decir(texto_aviso, 4500)
                if getattr(self.sesion, "_session", None):
                    prompt = f"[Aviso del sistema para comunicar a Moisés en voz alta ahora]: {texto_aviso}"
                    asyncio.run_coroutine_threadsafe(
                        self.sesion._session.send(input=prompt, end_of_turn=True),
                        self.loop_async,
                    )
                return True
            except Exception as e:
                print(f"[ORQUESTADOR] Error inyectando aviso en Live: {e}", flush=True)
                return False

        if self._modo_actual == "reposo_vosk":
            self.cara.decir(texto_aviso, 5000)
            if es_recordatorio and not self._silencio_total:
                # Alerta importante: despertar Live mediante transición atómica para anunciarlo
                prompt_rec = f"[Alerta de recordatorio programado]: {texto_aviso}"
                threading.Thread(target=self.activar_live, args=(prompt_rec,), daemon=True).start()
                return True
            # Iniciativa en reposo: solo visual en la esfera para no interrumpir
            return True

        return False  # En modo clásico o desconocido, permitir despacho normal

    def activar_fallback_clasico(self, motivo: str = ""):
        with self._bloqueo:
            self._modo_actual = "clasico"
            self._detener_sesion_live_interna()
            self._detener_vigilante_vosk()

        time.sleep(0.2)
        print(f"[ORQUESTADOR] Activando Modo Clásico por: {motivo}", flush=True)
        try:
            self.cara.decir("Sin conexión Live, pasando a modo clásico", 4000)
            kaya_live_nucleo.registrar_log_live(f"Fallback a modo clásico: {motivo}")
        except Exception:
            pass

        try:
            if hasattr(self.app, "iniciar_modo_clasico"):
                self.app.iniciar_modo_clasico()
            elif hasattr(self.app, "escuchar"):
                self.app.conversacion = True
                threading.Thread(target=self.app.escuchar, name="silvestra-clasico", daemon=True).start()
        except Exception as e:
            print(f"[ORQUESTADOR] Error activando app clásica: {e}", flush=True)

    def al_conversar(self):
        if self._modo_actual == "live" and self.sesion:
            if self.sesion._pausado:
                self.sesion.reanudar()
            else:
                self.sesion.pausar()
        elif self._modo_actual == "reposo_vosk":
            self.activar_live()
        elif self._modo_actual == "clasico":
            if hasattr(self.app, "alternar_conversacion"):
                self.app.alternar_conversacion()

    def al_descansar(self):
        self._silencio_total = True
        if self._modo_actual == "live" and self.sesion:
            self.sesion.pausar()
        self._detener_vigilante_vosk()
        self.cara.ocultar()

    def al_escribir(self):
        def al_enviar(txt):
            if not txt:
                return
            if self._modo_actual == "live" and self.sesion and self.loop_async:
                if getattr(self.sesion, "_session", None):
                    asyncio.run_coroutine_threadsafe(
                        self.sesion._session.send(input=txt, end_of_turn=True),
                        self.loop_async,
                    )
            elif self._modo_actual in ("reposo_vosk", "clasico"):
                if hasattr(self.app, "enviar"):
                    self.app.enviar(txt)
        self.cara.abrir_entrada("Hablar con Kaya", al_enviar)

    def _detener_sesion_live_interna(self):
        if self.sesion:
            try:
                self.sesion.detener()
            except Exception:
                pass
            self.sesion = None
        self.loop_async = None
        self.hilo_async = None

    def cerrar(self):
        self._cerrando = True
        self._detener_vigilante_vosk()
        self._detener_sesion_live_interna()
