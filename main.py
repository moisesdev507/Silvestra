import faulthandler
import os
import queue
import sys
import threading
import traceback

import rutas_app

_DIR_USUARIO = rutas_app.dir_usuario()
if getattr(sys, "frozen", False):
    os.chdir(_DIR_USUARIO)

# Diario de errores: como corre sin ventana, todo se guarda en silvestra.log
_ruta = os.path.join(_DIR_USUARIO, "silvestra.log")
try:
    import logging
    _diario = open(_ruta, "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = _diario
    sys.stderr = _diario
    faulthandler.enable(file=_diario, all_threads=True)
    logging.basicConfig(filename=_ruta, encoding="utf-8", level=logging.INFO, force=True)
except Exception:
    _diario = sys.stderr


def _excepthook_sys(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        return
    try:
        hilo_nombre = threading.current_thread().name
        print(f"\n[FATAL_CAPTURADO] Excepción no capturada en hilo '{hilo_nombre}':", file=_diario, flush=True)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_diario)
        _diario.flush()
    except Exception:
        pass


def _excepthook_thread(args):
    if issubclass(args.exc_type, KeyboardInterrupt):
        return
    try:
        hilo_nombre = getattr(args.thread, "name", "Desconocido") if args.thread else "Desconocido"
        print(f"\n[FATAL_CAPTURADO] Excepción no capturada en hilo '{hilo_nombre}':", file=_diario, flush=True)
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=_diario)
        _diario.flush()
    except Exception:
        pass


sys.excepthook = _excepthook_sys
threading.excepthook = _excepthook_thread

from groq import Groq
import httpx

import acciones
import aprendizaje
import camara
import casa
import config
import control_laptop
import control_pc
import conversacion
import correcciones
import cuidado
import diario
import escenario
import estudio
import eventos
import habilidades
import hilos
import hud
import ideas
import iniciativa
import invocacion_lyris
import nacimiento
import palabra_clave
import pantalla
import pantalla_remota
import presencia
import presentacion
import propuestas
import proveedores
import recordatorios
import respaldo
import resumen
import telegram_puente
import voz_dueno
from cara_qt import Cara
from cerebro import Cerebro
import memoria
from memoria import Memoria
import modos_sistema
from oido import Oido
from voz import Voz


class Silvestra:
    ultimo_dicho = ""

    def __init__(self):
        self.memoria = Memoria()
        self.integracion_cognitiva = None
        try:
            from integracion_cognitiva_fase5 import IntegracionCognitivaFase5
            self.integracion_cognitiva = IntegracionCognitivaFase5(self.memoria, self)
        except Exception as e:
            print(f"[cognicion] Integración global no disponible: {type(e).__name__}", flush=True)
        http_client = httpx.Client(limits=httpx.Limits(max_keepalive_connections=10, max_connections=20))
        self.cliente = Groq(api_key=(os.environ.get("GROQ_API_KEY") or config.CLAVE),
                            http_client=http_client)
        self.cerebro = Cerebro(self.cliente, self.memoria, app=self)
        self.voz = Voz()
        self.oido = Oido(self.cliente, self.memoria.vocabulario)
        self.cola = queue.Queue()

        self.conversacion = False
        self.escuchando = False
        self.voz_silenciada = False
        self.silencios = 0
        self.descansando = False
        self.pendiente_descanso = False
        self.flujo = None
        self.texto_flujo = ""

        self.cara = Cara(
            self.abrir_chat,
            self.alternar_silencio,
            self.renacer,
            self.pedir_descanso,
        )
        self.cara.silvestra_app = self
        self.cara._ref_app = self
        try:
            import tecla_kaya
            tecla_kaya.instalar(self)
        except Exception:
            pass
        try:
            import modos_sistema
            self.modo_activo = modos_sistema.obtener_modo_activo(self)
        except Exception:
            self.modo_activo = "normal"
        self.cara.modo_activo = self.modo_activo
        self.cara._ref_voz = self.voz
        self.cara.poner_viva(bool(self.memoria.nombre))
        memoria.instalar(self)
        try:
            import cerebro_unico
            cerebro_unico.inicializar_cerebro()
        except Exception:
            pass
        presentacion.instalar(self)
        self.casa = casa.instalar(self)
        self.camara = camara.instalar(self)
        self.cara._ref_camara = self.camara
        self.habilidades = habilidades.instalar(self)
        ideas.instalar(self)
        hilos.instalar(self)
        estudio.instalar(self)
        self.iniciativa = iniciativa.instalar(self)
        self.palabra_clave = palabra_clave.instalar(self)
        pantalla.instalar(self)
        self.hud = hud.instalar(self)
        escenario.instalar(self)
        self.telegram = telegram_puente.instalar(self)
        self.diario = diario.instalar(self)
        self.recordatorios = recordatorios.instalar(self)
        self.cuidado = cuidado.instalar(self)
        self.propuestas = propuestas.instalar(self)
        self.origen_entrada_actual = "chat"
        voz_dueno.instalar(self)
        control_pc.instalar(self)
        control_laptop.instalar(self)
        correcciones.instalar(self)
        self.resumen = resumen.instalar(self)
        self.aprendizaje = aprendizaje.instalar(self)
        modos_sistema.instalar(self)
        self.pantalla_remota = pantalla_remota.instalar(self)
        self.presencia = presencia.instalar(self)
        proveedores.instalar(self)
        respaldo.instalar(self)
        conversacion.instalar(self)
        self.invocacion = invocacion_lyris.instalar(self)
        try:
            import aprendiz_habilidades
            aprendiz_habilidades.cargar_habilidades_aprendidas(self)
        except Exception as e:
            print(f"[aprendiz] Error cargando habilidades: {e}", flush=True)
        try:
            import contexto_motor
            self.contexto_motor = contexto_motor.obtener_motor_contexto(self)
            self.contexto_motor.iniciar()
        except Exception as e:
            print(f"[contexto] Error al iniciar motor: {e}", flush=True)
            self.contexto_motor = None
        try:
            from multimodal_puente_app import SistemaMultimodalSilvestra
            self.sistema_multimodal = SistemaMultimodalSilvestra(self, self.contexto_motor)
            self.sistema_multimodal.iniciar()
        except Exception as e:
            print(f"[multimodal] Integracion no disponible: {e}", flush=True)
            self.sistema_multimodal = None

        self.cara.root.after(100, self.revisar_cola)

        # Coordinador Gemini Live unificado dentro de la aplicación principal
        self.coordinador_live = None
        try:
            import live_orquestador
            self.coordinador_live = live_orquestador.CoordinadorLiveSilvestra(self)
            # Aísla Celeste/Deepgram antes del precalentamiento: un solo saludo.
            if self.coordinador_live.es_modo_principal():
                self.coordinador_live.aislar_motores_locales()
                self.cara.root.after(50, self.coordinador_live.precalentar_en_paralelo)
        except Exception as e:
            print(f"[main] Coordinador Live no disponible: {e}", flush=True)

        if self.memoria.nombre:
            self.cara.root.after(500, self.saludar)
        else:
            self.cara.root.after(800, self.nacer)

    # ---------- Hablar y acciones ----------
    def puede_hablar_sola(self):
        """True solo si Silvestra no está hablando ni escuchando al usuario."""
        return not self.voz.ocupada() and not self.escuchando

    def decir(self, texto, ms=None, con_voz=True, emocion=None):
        if texto is False or texto is True or texto is None:
            return
        if not isinstance(texto, str) or not texto.strip():
            return
        emo = emocion or getattr(self.voz, "deducir_emocion", lambda t: "neutral")(texto)
        if hasattr(self.cara, "fijar_emocion"):
            self.cara.fijar_emocion(emo)
        self.cara.decir(texto, ms, emocion=emo)
        if con_voz:
            cl = getattr(self, "coordinador_live", None)
            if cl and (cl.esta_live_activo() or (hasattr(cl, "es_modo_principal") and cl.es_modo_principal())):
                # En modo Live o con Live activo, el audio sale por Gemini Live (voz Kaya)
                return
            self.ultimo_dicho = texto
            try:
                import naturalidad
                naturalidad.registrar_turno_asistente(texto)
            except Exception:
                pass
            self.voz.hablar(texto, lambda: self.cola.put(("fin_voz", None)), emocion=emo)
            if getattr(config, "BARGE_IN_ACTIVO", False) and self.conversacion and not self.escuchando:
                self.cara.root.after(300, self.escuchar)

    def ejecutar(self, linea):
        if not self.puede_hablar_sola():
            self.cara.root.after(300, lambda: self.ejecutar(linea))
            return
        nombre, arg = acciones.interpretar(linea)
        if nombre is None:
            return
        if nombre == "descansar":
            self.pedir_descanso()
            return
        try:
            ok, mensaje = acciones.ejecutar(nombre, arg)
            if not ok:
                self.cara.decir(mensaje, 4000)
                if hasattr(self, "propuestas") and self.propuestas:
                    self.propuestas.detectar_carencia_accion(nombre)
        except Exception as e:
            print(f"[main] Excepción ejecutando acción '{nombre}': {e}", flush=True)
            self.cara.decir("Hubo un fallo al ejecutar esa orden.", 3500)

    # ---------- Descansar y despertar ----------
    def pedir_descanso(self):
        if self.descansando or self.pendiente_descanso:
            return
        self.pendiente_descanso = True
        self.conversacion = False
        self._dejar_de_escuchar()
        self._iniciar_reflexion()
        self.cara.root.after(7000, self.descansar)

    def descansar(self):
        if self.descansando or not self.pendiente_descanso:
            return
        self.pendiente_descanso = False
        self.descansando = True
        self.conversacion = False
        self.cara.ocultar()

    def despertar(self):
        conversacion.despertar(self)

    def _iniciar_reflexion(self):
        threading.Thread(target=self.cerebro.reflexionar, args=(hilos,), daemon=True).start()

    # ---------- Delegación de conversación ----------
    def abrir_chat(self):
        conversacion.abrir_chat(self)

    def enviar(self, texto):
        cl = getattr(self, "coordinador_live", None)
        if cl:
            if cl.esta_live_activo():
                cl.enviar_orden(texto)
                return
            elif getattr(cl, "modo_live_habilitado", False):
                try:
                    import live_motor
                    if not live_motor.esta_en_enfriamiento_cuota():
                        if cl.intentar_activar_live(texto):
                            return
                except Exception:
                    pass

        if hasattr(self, "propuestas") and self.propuestas:
            try:
                self.propuestas.detectar_desde_correccion(texto)
            except Exception:
                pass
        conversacion.enviar(self, texto)

    def alternar_conversacion(self, motivo="interfaz"):
        conversacion.alternar_conversacion(self, motivo=motivo)

    def alternar_silencio(self):
        conversacion.alternar_silencio(self)

    def escuchar(self):
        conversacion.escuchar(self)

    def _grabar(self):
        conversacion.grabar(self)

    def _es_eco(self, texto):
        return conversacion.es_eco(self, texto)

    def _dejar_de_escuchar(self):
        conversacion.dejar_de_escuchar(self)

    # ---------- Delegación de nacimiento ----------
    def nacer(self):
        nacimiento.nacer(self)

    def saludar(self):
        cl = getattr(self, "coordinador_live", None)
        if cl is not None and (getattr(cl, "_saludo_inicial_enviado", False)
                               or cl.esta_live_activo()):
            return  # Gemini Live ya envió la única instrucción de saludo.
        nacimiento.saludar(self)

    def renacer(self):
        nacimiento.renacer(self)

    # ---------- Bucle de eventos ----------
    def revisar_cola(self):
        cl = getattr(self, "coordinador_live", None)
        if cl is not None and hasattr(cl, "sincronizar_por_cuota"):
            try:
                cl.sincronizar_por_cuota()
            except Exception:
                pass
        try:
            import qt_estabilidad_ui
            procesados, queda = qt_estabilidad_ui.drenar_cola_acotada(
                self.cola,
                lambda tipo, texto: eventos.atender_evento(self, tipo, texto),
                max_eventos=8,
                presupuesto_ms=12.0,
            )
        finally:
            try:
                demora = 1 if 'queda' in locals() and queda else 100
                self.cara.root.after(demora, self.revisar_cola)
            except Exception as e:
                print(f"[eventos] Error reprogramando revisar_cola: {e}", flush=True)

    def iniciar(self):
        try:
            self.cara.iniciar()
        except KeyboardInterrupt:
            pass
        finally:
            self.detener()

    def detener(self):
        """Detiene de forma limpia los motores y subprocesos al cerrar la aplicación."""
        try:
            self.casa.reloj.stop()
        except Exception:
            pass
        if getattr(self, "coordinador_live", None):
            try:
                self.coordinador_live.cerrar()
            except Exception:
                pass
        for objeto, metodo, args in (
            (getattr(self, "palabra_clave", None), "detener", ()),
            (getattr(self, "invocacion", None), "detener", ()),
            (getattr(self, "camara", None), "apagar", ()),
            (getattr(self, "oido", None), "cerrar", ()),
            (getattr(self, "voz", None), "detener", ("cierre_aplicacion",)),
        ):
            try:
                getattr(objeto, metodo)(*args)
            except Exception:
                pass
        if getattr(self, "sistema_multimodal", None):
            try:
                self.sistema_multimodal.detener()
            except Exception:
                pass
        if hasattr(self, "contexto_motor") and self.contexto_motor:
            try:
                self.contexto_motor.detener()
            except Exception:
                pass
        try:
            if self.integracion_cognitiva:
                self.integracion_cognitiva.cerrar()
        except Exception:
            pass
        try:
            self.memoria.cerrar()
        except Exception:
            pass


if __name__ == "__main__":
    import onboarding_qt

    rutas_app.preparar_dir_usuario()
    onboarding_qt.migrar_config_local()
    if not onboarding_qt.asegurar_configuracion():
        print("[main] Configuración inicial cancelada; no se iniciaron motores.", flush=True)
        sys.exit(0)
    Silvestra().iniciar()
