"""Puente universal entre Kaya Live, poderes locales de Silvestra y memoria persistente.

Ejecuta acciones del ecosistema Silvestra (apps, multimedia, recordatorios, archivos, etc.)
en un contexto silencioso (sin doble voz TTS) y gestiona la persistencia de memoria.
"""
import concurrent.futures
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import acciones


class AdaptadorVozMuda:
    """Captura cualquier texto que los módulos intenten emitir en vez de hablar."""

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
    """Ejecuta una acción local del sistema en modo silencioso y devuelve el resultado limpio."""
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

        # 5. Correo (Gmail) y Calendario (Google Workspace)
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

        # 6. Diario personal de Kaya (leer / forzar escritura)
        if "diario" in t_min:
            try:
                import diario
                d = diario.Diario(app_muda)
                if any(w in t_min for w in ("escribe", "anota", "escribir", "guardar", "redacta")):
                    threading.Thread(target=d.escribir_entrada, kwargs={"forzar": True}, daemon=True).start()
                    return "Anotando una nueva entrada en mi diario personal."
                else:
                    ent = d.obtener_ultima_entrada()
                    if ent:
                        return f"Mi última entrada del diario dice: {ent}"
                    return "Todavía no he escrito entradas en mi diario personal."
            except Exception as e:
                return f"Error con el diario: {e}"

        # 7. Ideas y notas pendientes (ideas.py / hilos.py)
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

        # 8. Detectar apertura de aplicación
        app_detectada = acciones.extraer_app_abrir(texto)
        if app_detectada:
            try:
                import control_laptop
                control_laptop.abrir_app(app_muda, app_detectada)
                time.sleep(0.05)
                if app_muda.cola_mensajes:
                    return app_muda.cola_mensajes[-1]
                return f"Abriendo {app_detectada}."
            except Exception as e:
                return f"Error abriendo {app_detectada}: {e}"

        # 6. Minimizar ventanas
        if acciones.es_minimizar(texto):
            try:
                import control_laptop
                control_laptop.minimizar_todo()
                return "Ventanas minimizadas."
            except Exception as e:
                return f"Error minimizando: {e}"

        # 7. Control de volumen y multimedia
        t_norm = texto.lower()
        if "subir volumen" in t_norm or "sube el volumen" in t_norm:
            ok, msg = acciones.ejecutar("subir_volumen")
            return "Volumen subido." if ok else str(msg)
        if "bajar volumen" in t_norm or "baja el volumen" in t_norm:
            ok, msg = acciones.ejecutar("bajar_volumen")
            return "Volumen bajado." if ok else str(msg)
        if "silenciar" in t_norm or "silencia el volumen" in t_norm or "mute" in t_norm:
            ok, msg = acciones.ejecutar("silenciar")
            return "Sonido silenciado/alternado." if ok else str(msg)

        # 8. Intento de interpretación de comando estructurado ("nombre | arg" o sólo "nombre")
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


def cargar_contexto_memoria_live() -> str:
    """Recupera recuerdos duraderos y temas abiertos para inyectar en el prompt Live."""
    bloques = []

    # 1. Hechos relevantes de la memoria SQLite / JSON
    try:
        import memoria
        mem = memoria.Memoria()
        creador = mem.creador or "Moisés"
        bloques.append(f"Usuario: {creador}")
        if mem.hechos:
            hechos_limpios = [re.sub(r"^\[[^\]]+\]\s*", "", h).strip() for h in mem.hechos[-6:]]
            if hechos_limpios:
                bloques.append("Recuerdos clave:\n- " + "\n- ".join(hechos_limpios))
    except Exception:
        pass

    # 2. Temas abiertos persistentes de Kaya
    try:
        import iniciativa_kaya
        temas = iniciativa_kaya.obtener_temas_abiertos()
        if temas:
            t_str = []
            for t in temas[:4]:
                nom = t.get("tema") or t.get("texto") or str(t)
                t_str.append(f"- {nom}")
            if t_str:
                bloques.append("Temas abiertos pendientes:\n" + "\n".join(t_str))
    except Exception:
        pass

    resultado = "\n\n[Memoria y contexto persistente]:\n" + "\n".join(bloques) if bloques else ""
    if len(resultado) > 1500:
        resultado = resultado[:1490].rsplit("\n", 1)[0] + "\n..."
    return resultado


def guardar_turno_o_resumen_memoria(turnos: List[Dict[str, str]]):
    """Extrae y guarda en segundo plano hechos o temas relevantes conversados en la sesión Live."""
    if not turnos or len(turnos) < 2:
        return

    def _tarea_fondo():
        try:
            # 1. Guardar en iniciativa_kaya si hay proyectos o compromisos mencionados
            import iniciativa_kaya
            for t in turnos:
                rol = t.get("role") or t.get("rol", "")
                txt = t.get("content") or t.get("texto", "")
                if rol in ("usuario", "user") and txt:
                    for pat in iniciativa_kaya.PATRONES_TEMA_ABIERTO:
                        m = pat.search(txt)
                        if m:
                            tema_nom = m.group(1).strip()
                            iniciativa_kaya.registrar_tema_abierto(tema_nom, contexto=f"Mencionado en Live: {txt}")
                            break

            # 2. Guardar en memoria central hechos claros
            import memoria
            mem = memoria.Memoria()
            charla_reciente = [
                {"role": t.get("role") or t.get("rol", ""), "content": t.get("content") or t.get("texto", "")}
                for t in turnos[-10:]
            ]
            # Si hay función de extracción disponible
            if hasattr(mem, "extraer_hechos_conversacion"):
                mem.extraer_hechos_conversacion(charla_reciente)
        except Exception as e:
            print(f"[LIVE Puente] Error guardando memoria persistente: {e}", flush=True)

    t = threading.Thread(target=_tarea_fondo, name="kaya-live-memoria-save", daemon=True)
    t.start()
