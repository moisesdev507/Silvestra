"""Diario personal de Silvestra y mensajes matutinos por Telegram."""
import atexit
import datetime
import os
import re
import threading
import time
import unicodedata

from PySide6.QtWidgets import QApplication

import acciones
import estado
import hilos
import ideas
import proveedores
from telegram_puente import sanitizar_privacidad

try:
    from escenario_escenas import PALABRAS_SENSIBLES, _es_seguro
except Exception:
    PALABRAS_SENSIBLES = ("clave", "token", "password", "secreto", "contraseña", "gsk_", "sk-", "tarjeta", "dinero", "saldo", "banco", "salud")
    def _es_seguro(t):
        return not any(p in str(t).lower() for p in PALABRAS_SENSIBLES) if t else False

RUTA_DIARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diario.md")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_instancia = None
_bloqueo_instancia = threading.RLock()


def _normal(texto):
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def obtener_instancia():
    with _bloqueo_instancia:
        return _instancia


def fecha_texto(dt=None):
    dt = dt or datetime.datetime.now()
    return f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"


def filtro_privacidad_diario(texto):
    if not texto:
        return ""
    limpio = sanitizar_privacidad(texto)
    for p in [r"\b(dinero|dólares|dolares|saldo|banco|tarjeta|salud|enfermedad|médico|medico|hospital)\b"]:
        limpio = re.sub(p, "[privado]", limpio, flags=re.I)
    return limpio


class Diario:
    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.RLock()
        self._detener = threading.Event()
        self.cargar_estado()

        app_qt = QApplication.instance()
        if app_qt:
            try:
                app_qt.aboutToQuit.connect(self.al_cerrar)
            except Exception:
                pass
        atexit.register(self.al_cerrar)
        self._hilo = threading.Thread(target=self._bucle_horario, daemon=True, name="DiarioHorario")
        self._hilo.start()

    def cargar_estado(self):
        d = estado.cargar()
        self.ultima_fecha = d.get("diario_ultima_fecha")
        self.ultimo_mensaje_manana = d.get("diario_ultimo_mensaje_manana")

    def guardar_estado(self):
        d = estado.cargar()
        d["diario_ultima_fecha"] = self.ultima_fecha
        d["diario_ultimo_mensaje_manana"] = self.ultimo_mensaje_manana
        estado.guardar(d)

    def _recopilar_contexto(self):
        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        hechos = getattr(self.app.memoria, "hechos", [])[-5:]
        hechos_txt = "; ".join(hechos) if hechos else "estudio y programación"
        hilos_txt = hilos.resumen() or "ninguno"
        ideas_txt = ideas.resumen() or "ninguna"
        historial = getattr(self.app.cerebro, "historial", [])[-4:]
        charla = "\n".join(f"{m.get('role', '').upper()}: {m.get('content', '')}" for m in historial if m.get("content"))
        return creador, hechos_txt, hilos_txt, ideas_txt, charla[-350:] if len(charla) > 350 else charla

    def escribir_entrada(self, forzar=False):
        with self._bloqueo:
            hoy_str = datetime.datetime.now().strftime("%Y-%m-%d")
            if not forzar and self.ultima_fecha == hoy_str:
                return False
            creador, hechos, hilos_txt, ideas_txt, charla = self._recopilar_contexto()

            sistema = (
                f"Eres Silvestra, IA de {creador}. Escribe una entrada personal de 3 a 5 frases sobre lo que hiciste o aprendiste con él hoy. "
                "Primera persona, cálida y reflexiva en español de Panamá. Eres una IA: no digas que soñaste ni dormiste; usa 'estuve pensando', 'me quedé reflexionando'. "
                "Cero claves, rutas, salud ni dinero. Un solo párrafo sin títulos ni viñetas."
            )
            prompt = f"Datos reales: Hechos: {hechos}. Hilos: {hilos_txt}. Ideas: {ideas_txt}." + (f" Charla: {charla}" if charla else "")
            try:
                entrada = proveedores.completar([{"role": "system", "content": sistema}, {"role": "user", "content": prompt}], tarea="fondo")
            except Exception as e:
                print(f"[diario] Fallo en proveedores: {e}", flush=True)
                return False

            if not entrada or not entrada.strip():
                return False
            texto = filtro_privacidad_diario(entrada.replace("*", "").replace("\n", " ").strip(" \"'"))
            if not _es_seguro(texto):
                return False

            try:
                existe = os.path.exists(RUTA_DIARIO)
                with open(RUTA_DIARIO, "a", encoding="utf-8") as f:
                    if not existe:
                        f.write("# Diario de Silvestra\n\n")
                    f.write(f"## {fecha_texto()}\n\n{texto}\n\n")
                self.ultima_fecha = hoy_str
                self.guardar_estado()
                print(f"[diario] Entrada guardada para {hoy_str}.", flush=True)
                return True
            except Exception as e:
                print(f"[diario] Error escribiendo diario: {e}", flush=True)
                return False

    def _contexto_reciente(self):
        _, hechos, hilos_txt, ideas_txt, charla = self._recopilar_contexto()
        return f"Hechos: {hechos}. Hilos: {hilos_txt}. Ideas: {ideas_txt}. Charla: {charla}"

    def escribir_sobre(self, tema=""):
        """Redacta y guarda una entrada íntima desde la perspectiva de Kaya."""
        import diario_helpers
        with self._bloqueo:
            ok = diario_helpers.redactar_y_guardar(
                str(tema or ""), self._contexto_reciente()
            )
        if ok:
            self.app.cola.put(("hablar", "Ya lo anoté en mi diario, desde mi perspectiva."))
        else:
            self.app.cola.put(("hablar", "No pude redactar mi entrada ahora mismo."))
        return ok

    def reflexion_automatica(self):
        """Reflexión ligera al cerrar: solo con interacción real y sin entrada de hoy."""
        import diario_helpers
        hoy = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.ultima_fecha == hoy:
            return False
        cerebro = getattr(self.app, "cerebro", None)
        historial = getattr(cerebro, "historial", []) or []
        turnos = sum(
            1 for m in historial
            if m.get("role") == "user" and str(m.get("content") or "").strip()
        )
        if turnos < 2:
            return False
        return diario_helpers.redactar_y_guardar("", self._contexto_reciente())

    def enviar_mensaje_manana(self, forzar=False):
        with self._bloqueo:
            hoy_str = datetime.datetime.now().strftime("%Y-%m-%d")
            if not forzar and self.ultimo_mensaje_manana == hoy_str:
                return False
            puente = getattr(self.app, "telegram", None)
            if not puente or not getattr(puente, "chat_id_autorizado", None):
                return False

            creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
            ultima = self.obtener_ultima_entrada() or ""
            sistema = (
                f"Eres Silvestra, IA de {creador}. Es de mañana y le mandas un mensaje corto (máx 3 frases) a Telegram con algo que 'estuviste pensando' de tu diario o una pregunta curiosa. "
                "Español panameño natural. Eres IA: no digas que soñaste. Si no hay nada interesante responde NINGUNO. Cero claves ni dinero."
            )
            prompt = f"Diario: {ultima}\nTemas: {hilos.resumen() or ''}"
            try:
                mensaje = proveedores.completar([{"role": "system", "content": sistema}, {"role": "user", "content": prompt}], tarea="fondo")
            except Exception as e:
                print(f"[diario] Error mensaje matutino: {e}", flush=True)
                return False

            if not mensaje or not mensaje.strip():
                return False
            texto = filtro_privacidad_diario(mensaje.replace("*", "").replace("\n", " ").strip(" \"'"))
            if texto.upper() in ("NINGUNO", "NINGUNO.") or not _es_seguro(texto):
                self.ultimo_mensaje_manana = hoy_str
                self.guardar_estado()
                return False

            ok = puente.avisar_celular(texto, forzar=True)
            if ok:
                self.ultimo_mensaje_manana = hoy_str
                self.guardar_estado()
                print("[diario] Mensaje matutino enviado a Telegram.", flush=True)
                return True
            return False

    def obtener_ultima_entrada(self):
        if not os.path.exists(RUTA_DIARIO):
            return None
        try:
            with open(RUTA_DIARIO, "r", encoding="utf-8") as f:
                c = f.read().strip()
            if not c:
                return None
            partes = re.split(r"(?m)^##\s+", c)
            if len(partes) > 1:
                lineas = [l.strip() for l in partes[-1].splitlines() if l.strip()]
                return " ".join(lineas[1:]) if len(lineas) > 1 else " ".join(lineas)
            return c
        except Exception:
            return None

    def leer_diario(self):
        ultima = self.obtener_ultima_entrada()
        if not ultima:
            self.app.cola.put(("hablar", "Todavía no he escrito nada en mi diario. Al final del día anotaré mi primera entrada."))
            return
        self.app.cola.put(("hablar", f"Te leo mi última entrada del diario: {ultima}"))

    def borrar_diario(self):
        with self._bloqueo:
            try:
                if os.path.exists(RUTA_DIARIO):
                    os.remove(RUTA_DIARIO)
                self.ultima_fecha = None
                self.guardar_estado()
                self.app.cola.put(("hablar", "Listo, borré mi diario."))
            except Exception as e:
                self.app.cola.put(("hablar", "Tuve un problema para borrar el diario."))

    def al_cerrar(self):
        hoy_str = datetime.datetime.now().strftime("%Y-%m-%d")
        if self.ultima_fecha != hoy_str:
            if not self.reflexion_automatica():
                self.escribir_entrada(forzar=False)

    def _bucle_horario(self):
        while not self._detener.is_set():
            try:
                ahora = datetime.datetime.now()
                hoy_str = ahora.strftime("%Y-%m-%d")
                if ahora.hour >= 21 and self.ultima_fecha != hoy_str:
                    self.escribir_entrada(forzar=False)
                if 7 <= ahora.hour < 12 and self.ultimo_mensaje_manana != hoy_str:
                    self.enviar_mensaje_manana(forzar=False)
            except Exception as e:
                print(f"[diario] Error horario: {e}", flush=True)
            time.sleep(60)


def instalar(app):
    global _instancia
    d = Diario(app)
    with _bloqueo_instancia:
        _instancia = d
    acciones.registrar("leer_diario", lambda arg=None: d.leer_diario(), "lee en voz alta la última entrada del diario personal de Kaya")
    acciones.registrar("borrar_diario", lambda arg=None: d.borrar_diario(), "borra por completo el diario personal de Kaya")
    acciones.registrar(
        "escribir_diario",
        d.escribir_sobre,
        "escribe en el diario de Kaya una entrada en primera persona sobre el tema indicado",
        con_texto=True,
    )
    acciones.registrar(
        "probar_mensaje_manana",
        lambda arg=None: threading.Thread(target=d.enviar_mensaje_manana, kwargs={"forzar": True}, daemon=True).start(),
        "fuerza el envío del mensaje matutino a Telegram",
    )
    return d
