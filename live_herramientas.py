"""Herramientas y puente delgado Function Calling para Gemini Live en Silvestra.

Delega el 100% de las acciones a los módulos existentes del proyecto:
- acciones.py
- google_workspace.py
- diario.py
- ideas.py
- hilos.py
- recordatorios.py
- telemetria.py
Garantiza ejecución silenciosa sin disparar voz duplicada.
"""
import asyncio
import concurrent.futures
import datetime
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from google.genai import types

import acciones

_OJOS_ACTIVOS = True
_LOCK_OJOS = threading.RLock()
_CALLBACK_REPOSO: Optional[Callable[[], None]] = None
_LOCK_REPOSO = threading.RLock()


def registrar_callback_reposo(cb: Optional[Callable[[], None]]):
    """Registra callback que se invoca cuando Kaya entra en reposo por Function Calling."""
    global _CALLBACK_REPOSO
    with _LOCK_REPOSO:
        _CALLBACK_REPOSO = cb


def solicitar_reposo_desde_live(motivo: str = "orden_voz") -> str:
    """Dispara el callback de reposo tras la despedida."""
    with _LOCK_REPOSO:
        cb = _CALLBACK_REPOSO
    if callable(cb):
        try:
            threading.Thread(target=cb, name="live-solicitar-reposo", daemon=True).start()
        except Exception:
            pass
    return "Entrando en modo reposo. Te escucharé cuando me llames por mi nombre."


class AdaptadorVozMuda:
    """Captura cualquier texto que los módulos intenten hablar en vez de emitirlo a los parlantes."""

    def __init__(self):
        self.mensajes_capturados: List[str] = []
        self._bloqueo = threading.RLock()
        self.nivel_volumen = 0.0

    def hablar(self, texto, callback=None, emocion=None):
        t = str(texto or "").strip()
        if t:
            with self._bloqueo:
                self.mensajes_capturados.append(t)
        if callable(callback):
            try:
                callback()
            except Exception:
                pass

    def ocupada(self):
        return False

    def deducir_emocion(self, texto):
        return "neutral"

    def obtener_captura(self) -> str:
        with self._bloqueo:
            return " ".join(self.mensajes_capturados).strip()


class AdaptadorAppMuda:
    """Simula el contexto app de Silvestra para módulos que requieren app.cola o app.voz."""

    def __init__(self, voz_muda: AdaptadorVozMuda):
        self.voz = voz_muda
        self.ultimo_dicho = ""
        self.origen_entrada_actual = "live"
        self.cola_mensajes: List[str] = []

    class _Cola:
        def __init__(self, padre):
            self._padre = padre

        def put(self, item):
            if isinstance(item, tuple) and len(item) == 2:
                tipo, dato = item
                if tipo == "frase":
                    txt = dato[0] if isinstance(dato, (tuple, list)) else str(dato)
                    self._padre.cola_mensajes.append(txt)
            elif isinstance(item, str):
                self._padre.cola_mensajes.append(item)

    @property
    def cola(self):
        return self._Cola(self)

    def puede_hablar_sola(self):
        return True

    def decir(self, texto, ms=None, con_voz=True, emocion=None):
        t = str(texto or "").strip()
        if t:
            self.cola_mensajes.append(t)


def ejecutar_accion_local(instruccion: str, timeout: float = 8.0) -> str:
    """Ejecuta una acción local delegando a los motores existentes de Silvestra."""
    if not instruccion or not str(instruccion).strip():
        return "No se especificó ninguna acción."
    texto = str(instruccion).strip()

    def _tarea():
        voz_muda = AdaptadorVozMuda()
        app_muda = AdaptadorAppMuda(voz_muda)

        # 1. Telemetría directa
        res_tele = acciones.telemetria_local(texto)
        if res_tele:
            return str(res_tele)

        # 2. Modos locales
        res_modo = acciones.modo_local(texto, app=app_muda)
        if res_modo:
            return str(res_modo)

        # 3. Atajos de archivos locales
        res_arch = acciones.atajo_archivos_locales(texto)
        if res_arch:
            resp, _, _ = res_arch
            return str(resp)

        # 4. Recordatorios
        try:
            import recordatorios
            if recordatorios.es_recordatorio_temporal(texto):
                return str(recordatorios.procesar_orden_recordatorio(texto))
        except Exception:
            pass

        # 5. Correo y Calendario (Google Workspace)
        t_min = texto.lower()
        if any(w in t_min for w in ("correo", "correos", "email", "gmail", "inbox")):
            try:
                import google_workspace
                res_c = google_workspace.resumen_correos()
                return str(res_c.get("texto") or "No se pudo obtener información del correo.")
            except Exception as e:
                return f"Error consultando correos: {e}"

        if any(w in t_min for w in ("calendario", "agenda", "eventos", "citas", "reuniones")):
            try:
                import google_workspace
                res_a = google_workspace.agenda_hoy()
                return str(res_a.get("texto") or "No se pudo obtener información de la agenda.")
            except Exception as e:
                return f"Error consultando agenda: {e}"

        # 6. Diario personal
        if "diario" in t_min:
            try:
                import diario
                d = diario.Diario(app_muda)
                if any(w in t_min for w in ("escribe", "anota", "escribir", "guardar", "redacta")):
                    threading.Thread(target=d.escribir_entrada, kwargs={"forzar": True}, daemon=True).start()
                    return "Anotando una nueva entrada en mi diario personal."
                else:
                    ent = d.obtener_ultima_entrada()
                    return f"Mi última entrada del diario dice: {ent}" if ent else "Todavía no he escrito entradas en mi diario personal."
            except Exception as e:
                return f"Error con el diario: {e}"

        # 7. Ideas e Hilos
        if any(w in t_min for w in ("mis ideas", "que ideas tienes", "ideas pendientes", "lista de ideas")):
            try:
                import ideas
                res_i = ideas.resumen()
                return f"Ideas registradas: {res_i}" if res_i else "No hay ideas anotadas por ahora."
            except Exception as e:
                return f"Error leyendo ideas: {e}"

        if any(w in t_min for w in ("pendientes", "hilos abiertos", "que tenemos pendiente")):
            try:
                import hilos
                res_h = hilos.resumen()
                return f"Temas e hilos pendientes: {res_h}" if res_h else "No hay pendientes registrados."
            except Exception as e:
                return f"Error leyendo pendientes: {e}"

        # 8. Apertura de apps permitidas
        app_detectada = acciones.extraer_app_abrir(texto)
        if app_detectada:
            try:
                import control_laptop
                control_laptop.abrir_app(app_muda, app_detectada)
                time.sleep(0.05)
                return app_muda.cola_mensajes[-1] if app_muda.cola_mensajes else f"Abriendo {app_detectada}."
            except Exception as e:
                return f"Error abriendo {app_detectada}: {e}"

        # 9. Minimizar
        if acciones.es_minimizar(texto):
            try:
                import control_laptop
                control_laptop.minimizar_todo()
                return "Ventanas minimizadas."
            except Exception as e:
                return f"Error minimizando: {e}"

        # 10. Volumen / silencio
        t_norm = texto.lower()
        if any(v in t_norm for v in ("subir volumen", "sube el volumen")):
            ok, msg = acciones.ejecutar("subir_volumen")
            return "Volumen subido." if ok else str(msg)
        if any(v in t_norm for v in ("bajar volumen", "baja el volumen")):
            ok, msg = acciones.ejecutar("bajar_volumen")
            return "Volumen bajado." if ok else str(msg)
        if any(v in t_norm for v in ("silenciar", "mute", "silencia el volumen")):
            ok, msg = acciones.ejecutar("silenciar")
            return "Sonido silenciado/alternado." if ok else str(msg)

        # 11. Intento de interpretación de comando estructurado
        nom, arg = acciones.interpretar(texto)
        if nom and (nom in acciones.ACCIONES or nom in acciones.VIVAS):
            try:
                ok, msg = acciones.ejecutar(nom, arg)
                capturado = app_muda.cola_mensajes[-1] if app_muda.cola_mensajes else ""
                return capturado or (msg if ok else f"No se pudo completar: {msg}")
            except Exception as e:
                return f"Error ejecutando acción '{nom}': {e}"

        return f"Orden '{texto}' procesada en la PC."

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_tarea)
            return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return "La acción tardó demasiado tiempo en responder."
    except Exception as e:
        return f"Error ejecutando acción local: {e}"


def consultar_sistema() -> str:
    """Consulta la telemetría real del equipo (CPU, RAM, batería)."""
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info = [f"Fecha y hora: {ahora}"]
    try:
        import telemetria
        estado = telemetria.estado_sistema()
        txt = estado.get("texto") or str(estado)
        info.append(f"Estado del equipo: {txt}")
    except Exception as e:
        info.append(f"Telemetría no disponible ({e})")
    return "\n".join(info)


def declarar_declaraciones_herramientas() -> List[types.Tool]:
    """Genera declaraciones de herramientas para Function Calling en Gemini Live."""
    herramientas = [
        types.FunctionDeclaration(
            name="ejecutar_accion_pc",
            description=(
                "Ejecuta cualquier acción local en la PC de Moisés: abrir o cerrar programas, "
                "subir/bajar volumen, reproducir música en YouTube, revisar correos, consultar o crear recordatorios, "
                "consultar agenda de Google Calendar, leer o redactar en el diario personal, o revisar ideas pendientes."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "instruccion": types.Schema(
                        type="STRING",
                        description="Orden o acción en lenguaje natural (ej. 'revisa mis correos', 'sube el volumen', 'pon música de rock en youtube').",
                    ),
                },
                required=["instruccion"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_clima",
            description="Consulta el clima en tiempo real (temperatura actual, sensación térmica, estado del cielo y pronóstico) para cualquier ciudad (por defecto Panamá).",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "ciudad": types.Schema(type="STRING", description="Nombre de la ciudad (ej. 'Panamá', 'Chiriquí', 'Madrid')."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="buscar_en_internet",
            description="Busca información actualizada en la web en tiempo real para preguntas de actualidad, datos en vivo, noticias o consultas externas.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "consulta": types.Schema(type="STRING", description="Tema o pregunta a buscar en la web."),
                },
                required=["consulta"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_estado_pc",
            description="Consulta la telemetría del equipo (batería, memoria RAM, CPU y hora actual).",
            parameters=types.Schema(type="OBJECT", properties={}),
        ),
        types.FunctionDeclaration(
            name="entrar_en_reposo",
            description="Pone a Kaya en modo reposo cuando el usuario se despide o pide descansar.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "motivo": types.Schema(type="STRING", description="Razón del reposo (ej. despedida, silencio)."),
                },
            ),
        ),
    ]
    return [types.Tool(function_declarations=herramientas)]


async def despachar_herramienta_asincrona(nombre: str, args: Dict[str, Any]) -> str:
    """Ejecuta una herramienta en hilo secundario para no bloquear el streaming."""
    loop = asyncio.get_running_loop()
    if nombre == "ejecutar_accion_pc":
        instruccion = args.get("instruccion", "")
        return await loop.run_in_executor(None, ejecutar_accion_local, instruccion)
    elif nombre == "consultar_clima":
        ciudad = args.get("ciudad") or "Panamá"
        import consulta_web
        return await loop.run_in_executor(None, consulta_web.consultar_clima, ciudad)
    elif nombre == "buscar_en_internet":
        consulta = args.get("consulta", "")
        import consulta_web
        return await loop.run_in_executor(None, consulta_web.buscar_web, consulta)
    elif nombre == "consultar_estado_pc":
        return await loop.run_in_executor(None, consultar_sistema)
    elif nombre == "entrar_en_reposo":
        motivo = args.get("motivo", "orden_usuario")
        return await loop.run_in_executor(None, solicitar_reposo_desde_live, motivo)
    return f"Herramienta '{nombre}' no reconocida."
